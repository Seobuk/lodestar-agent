"""Lodestar Agent — 논문 요청 큐를 폴링해 다운로드 → Drive 업로드.

실행 모드:
  main.py             설정 없으면 마법사 → 트레이(가능하면) 상주
  main.py --setup     설정 마법사 강제
  main.py --console   트레이 없이 콘솔 모드
  main.py --minimized 부팅 자동시작용(마법사 생략, 조용히 시작)
"""

import os
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
            _last_status = f"업로드 중: {got['file_name'][:40]}"
            link = upload_pdf(got["path"], got["file_name"],
                              cfg["gdrive_folder_id"],
                              bool(cfg.get("share_anyone", True)))
        api.report_done(rid, got["title"], link, got["file_name"])
        C.log(f"완료 [{rid}] → {link}")
        _last_status = f"완료: {got['file_name'][:40]}"
    except (DownloadError, DriveError) as e:
        api.report_failed(rid, str(e))
        C.log(f"실패 [{rid}] {e}")
        _last_status = f"실패: {e}"[:60]
    except Exception as e:  # 예상 밖 오류도 큐를 막지 않게 failed 처리
        api.report_failed(rid, f"{type(e).__name__}: {e}")
        C.log(f"실패(예외) [{rid}] {e}")


def loop() -> None:
    global _last_status
    cfg = C.load()
    api = Lodestar(cfg["lodestar_url"], cfg["api_token"], cfg["agent_id"])
    last_update = 0.0
    try:
        interval = int(cfg.get("poll_interval_sec", 20))
    except (TypeError, ValueError):
        interval = 20  # config.json을 손으로 고치다 잘못된 값을 넣어도 죽지 않게
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


def run_tray(cfg: dict) -> None:
    """pystray 트레이 아이콘. 미설치면 콘솔 모드로 폴백."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        C.log("pystray/Pillow 없음 → 콘솔 모드")
        loop()
        return

    img = Image.new("RGB", (64, 64), "#1e3a8a")
    d = ImageDraw.Draw(img)
    d.polygon([(32, 8), (40, 26), (58, 26), (44, 38), (50, 56),
               (32, 45), (14, 56), (20, 38), (6, 26), (24, 26)],
              fill="#facc15")  # lodestar = 길잡이 별

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    def status_text(_):
        return f"v{VERSION} — {_last_status}"

    def open_web(_i, _m):
        webbrowser.open(cfg["lodestar_url"] + "/papers")

    def open_log(_i, _m):
        webbrowser.open(str(C.log_path()))

    def toggle_auto(_i, _m):
        (autostart.disable if autostart.is_enabled() else autostart.enable)()

    def check_update(_i, _m):
        if updater.check_and_apply(cfg.get("github_repo", "")):
            icon.stop()
            os._exit(0)  # 교체 배치가 move하기 전에 exe 잠금을 확실히 해제

    def quit_(icon_, _m):
        _stop.set()
        icon_.stop()

    icon = pystray.Icon(
        "LodestarAgent", img, "Lodestar Agent",
        menu=pystray.Menu(
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.MenuItem("논문 페이지 열기", open_web),
            pystray.MenuItem("로그 보기", open_log),
            pystray.MenuItem("업데이트 확인", check_update),
            pystray.MenuItem(
                lambda _: f"부팅 자동시작 {'✓' if autostart.is_enabled() else '✗'}",
                toggle_auto),
            pystray.MenuItem("종료", quit_),
        ),
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
        loop()
    else:
        run_tray(cfg)


if __name__ == "__main__":
    main()
