"""Lodestar Agent — 논문 요청 큐를 폴링해 다운로드 → Drive 업로드.

실행 모드:
  main.py             설정 없으면 마법사 → 트레이(가능하면) 상주
  main.py --setup     설정 마법사 강제
  main.py --admin     트레이에 관리 메뉴 표시(저장 모드·로그·자동시작)
  main.py --console   트레이 없이 콘솔 모드
  main.py --minimized 부팅 자동시작용(마법사 생략, 조용히 시작)

PC 사용자 무간섭 원칙: 알림·팝업 없음. 기본 트레이 메뉴는 설명·상태·
업데이트 확인·종료.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

import autostart
import config as C
import updater
from downloader import DownloadError, fetch_pdf
from gdrive import DriveError, upload_pdf
from lodestar_api import Lodestar, LodestarError
from version import VERSION

UPDATE_EVERY = 6 * 3600
_last_status = "시작 중"
_stop = threading.Event()


def save_local(src: Path, name: str, dest_dir: Path | None = None) -> Path:
    """PDF를 exe 폴더에 저장(기본 모드). exe를 구글 드라이브 동기 폴더에 두면
    데스크톱 클라이언트가 알아서 업로드한다 — Drive API·자격증명 불필요."""
    dest_dir = dest_dir or C.exe_path().parent
    dest, n = dest_dir / name, 2
    while dest.exists():  # 같은 논문 재요청 등 이름 충돌 시 (2), (3)…
        dest = dest_dir / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    shutil.move(str(src), str(dest))
    return dest


def process_one(api: Lodestar, cfg: dict, item: dict) -> None:
    global _last_status
    rid, text = item["id"], (item.get("doi") or item.get("input") or "")
    if not api.claim(rid):
        return  # 다른 에이전트(집 PC 등)가 선점
    C.log(f"처리 시작 [{rid}] {text}")
    _last_status = f"다운로드 중: {text[:40]}"
    try:
        with tempfile.TemporaryDirectory(prefix="lodestar_") as td:
            got = fetch_pdf(item.get("input", text), Path(td),
                            cfg.get("unpaywall_email", ""))
            file_name = got["file_name"]
            if cfg.get("gdrive_folder_id"):  # 직접 Drive API 모드(고급, 자체 자격증명)
                _last_status = f"업로드 중: {file_name[:40]}"
                link = upload_pdf(got["path"], file_name,
                                  cfg["gdrive_folder_id"],
                                  bool(cfg.get("share_anyone", True)))
            elif cfg.get("server_upload", True):  # 기본: 서버 업로드(링크 자동)
                _last_status = f"업로드 중: {file_name[:40]}"
                try:
                    link = api.upload_pdf_via_server(got["path"], file_name)
                except Exception as e:
                    # 서버 미설정·일시 장애 — 받은 PDF는 살리고 로컬 저장 폴백
                    C.log(f"서버 업로드 실패 → exe 폴더 저장 폴백: {e}")
                    dest = save_local(got["path"], file_name)
                    file_name, link = dest.name, ""
            else:  # exe 폴더 저장 (동기 폴더면 자동 업로드)
                dest = save_local(got["path"], file_name)
                file_name, link = dest.name, ""
        api.report_done(rid, got["title"], link, file_name)
        C.log(f"완료 [{rid}] → {link or file_name}")
        _last_status = f"완료: {file_name[:40]}"
    except (DownloadError, DriveError) as e:
        api.report_failed(rid, str(e))
        C.log(f"실패 [{rid}] {e}")
        _last_status = f"실패: {e}"[:60]
    except Exception as e:  # 예상 밖 오류도 큐를 막지 않게 failed 처리
        api.report_failed(rid, f"{type(e).__name__}: {e}")
        C.log(f"실패(예외) [{rid}] {e}")


def loop(cfg: dict) -> None:
    # cfg는 트레이와 공유하는 dict — 트레이 "저장 모드" 전환이 다음 건부터 반영된다.
    global _last_status
    api = Lodestar(cfg["lodestar_url"], cfg["api_token"], cfg["agent_id"])
    last_update = 0.0
    try:
        interval = int(cfg.get("poll_interval_sec", 60))
    except (TypeError, ValueError):
        interval = 60  # config.json을 손으로 고치다 잘못된 값을 넣어도 죽지 않게
    C.log(f"Lodestar Agent v{VERSION} 시작 (agent_id={cfg['agent_id']})")
    while not _stop.is_set():
        now = time.time()
        if now - last_update > UPDATE_EVERY:
            last_update = now
            if updater.check_and_apply(cfg.get("github_repo", "")):
                # 트레이 모드에서 loop()는 데몬 스레드 — sys.exit는 이 스레드만
                # 죽여 exe 잠금이 안 풀리고, 교체 배치의 move가 실패한다.
                # 프로세스를 통째로 내려야 배치가 exe를 바꿔치기할 수 있다.
                os._exit(0)
        try:
            items = api.pending()
            if items:
                for it in items:
                    process_one(api, cfg, it)
            else:
                _last_status = "대기 중 (큐 비어 있음)"
        except LodestarError as e:
            _last_status = str(e)
            C.log(str(e))
        except Exception as e:
            _last_status = f"연결 오류: {e}"[:60]
            C.log(f"폴링 오류: {e}")
        _stop.wait(interval)


def run_tray(cfg: dict, admin: bool = False) -> None:
    """pystray 트레이 아이콘(우하단 알림 영역 상주). 미설치면 콘솔 모드로 폴백.

    PC 사용자를 신경 쓰이게 하지 않는 게 원칙 — 알림·팝업은 일절 없다.
    기본 우클릭 메뉴는 설명 + 상태 + 업데이트 확인 + 종료.
    나머지 관리 항목(저장 모드 전환·로그·자동시작 토글)은
    설치자가 --admin으로 실행했을 때만 보인다.
    """
    try:
        import pystray
        from robot_icon import draw_humanoid
    except Exception:
        C.log("pystray/Pillow 없음 → 콘솔 모드")
        loop(cfg)
        return

    img = draw_humanoid(64)  # 휴머노이드 로봇 — exe 아이콘(.ico)과 같은 그림

    t = threading.Thread(target=loop, args=(cfg,), daemon=True)
    t.start()

    def status_text(_):
        return f"v{VERSION} — {_last_status}"

    def open_log(_i, _m):
        webbrowser.open(str(C.log_path()))

    def toggle_auto(_i, _m):
        (autostart.disable if autostart.is_enabled() else autostart.enable)()

    def set_mode(server: bool):
        # loop()와 같은 cfg dict를 고치므로 다음 논문부터 즉시 적용 + 저장.
        def handler(_i, _m):
            cfg["server_upload"] = server
            C.save(cfg)
            C.log(f"저장 모드 변경: {'팀 Drive 업로드' if server else 'exe 폴더 저장'}")
        return handler

    def check_update(_i, _m):
        # 사용자가 직접 누른 확인이라 결과를 상태줄에 남긴다(팝업 없음 원칙 유지).
        global _last_status
        _last_status = "업데이트 확인 중…"
        if updater.check_and_apply(cfg.get("github_repo", "")):
            icon.stop()
            os._exit(0)  # 교체 배치가 move하기 전에 exe 잠금을 확실히 해제
        _last_status = f"최신 버전입니다 (v{VERSION})"

    def quit_(icon_, _m):
        _stop.set()
        icon_.stop()

    # 기본 우클릭 메뉴: 설명 + 상태(둘 다 비활성 표시) + 업데이트 확인 + 종료
    items = [
        pystray.MenuItem("Seobuk 공동연구를 위한 논문전달 에이전트 프로그램",
                         None, enabled=False),
        pystray.MenuItem(status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("업데이트 확인", check_update),
    ]
    if admin:  # 관리 메뉴 — --admin 실행 시에만 (평소엔 PC 사용자에게 비노출)
        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("저장 모드", pystray.Menu(
                pystray.MenuItem(
                    "팀 Drive 업로드 (링크 자동)", set_mode(True),
                    checked=lambda _: bool(cfg.get("server_upload", True)),
                    radio=True),
                pystray.MenuItem(
                    "exe 폴더 저장", set_mode(False),
                    checked=lambda _: not cfg.get("server_upload", True),
                    radio=True),
                # 고급 직접 Drive API 모드(폴더 지정)는 위 선택보다 우선한다
                pystray.MenuItem(
                    "⚠ 직접 Drive API 모드(폴더 지정)가 우선 적용 중",
                    None, enabled=False,
                    visible=lambda _: bool(cfg.get("gdrive_folder_id"))),
            )),
            pystray.MenuItem("로그 보기", open_log),
            pystray.MenuItem(
                lambda _: f"부팅 자동시작 {'✓' if autostart.is_enabled() else '✗'}",
                toggle_auto),
        ]
    items.append(pystray.MenuItem("종료", quit_))
    icon = pystray.Icon(
        "LodestarAgent", img, "Lodestar Agent — 논문 자동 다운로드",
        menu=pystray.Menu(*items),
    )
    icon.run()


def main() -> None:
    args = set(sys.argv[1:])
    cfg = C.load()

    if "--setup" in args or (not C.is_configured(cfg) and "--minimized" not in args):
        from setup_gui import run_wizard
        cfg = run_wizard()
        if not C.is_configured(cfg):
            C.log("설정 미완료 — 종료")
            return

    if not C.is_configured(cfg):
        C.log("설정이 없어 시작할 수 없습니다. --setup으로 실행하세요.")
        return

    if cfg.get("autostart") and not autostart.is_enabled():
        try:
            autostart.enable()
        except Exception:
            pass

    if "--console" in args:
        loop(cfg)
    else:
        run_tray(cfg, admin="--admin" in args)


if __name__ == "__main__":
    main()
