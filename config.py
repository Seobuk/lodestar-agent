"""설정/로그. 설정은 %APPDATA%/LodestarAgent/config.json (비Windows는 ~/.lodestar-agent)."""

import json
import os
import socket
import sys
from pathlib import Path

APP_NAME = "LodestarAgent"

DEFAULTS = {
    "lodestar_url": "",          # 예: https://lodestar.example.com (끝 슬래시 없이)
    "api_token": "",             # Lodestar /token 페이지에서 발급한 lsk_ 토큰
    # 기본 — 서버 업로드 모드: lsk_ 토큰만으로 서버가 열어 준 세션에 PDF를 올려
    # 팀 Drive(첨부 폴더)에 저장, /papers 카드에 팀 전용 링크가 자동으로 뜬다.
    # GCP 자격증명 불필요. 서버 미설정·오류 시엔 exe 폴더 저장으로 자동 폴백.
    "server_upload": True,
    # 고급 — 값을 넣으면 자체 자격증명(service_account.json 등)으로 직접
    # Drive API 업로드(서버 업로드보다 우선). 비우고 server_upload도 끄면
    # exe 폴더에 저장 — exe를 구글 드라이브 동기 폴더에 두면 그 자체로 업로드 완성.
    "gdrive_folder_id": "",
    "share_anyone": True,        # (직접 Drive API 모드) '링크가 있는 모든 사용자 보기' 부여
    "poll_interval_sec": 20,
    "agent_id": socket.gethostname(),
    "unpaywall_email": "",       # OA 폴백용(선택). 비우면 Unpaywall 스킵.
    "github_repo": "Seobuk/lodestar-agent",  # 자동 업데이트 릴리스 저장소
    "autostart": True,
}


def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
        d = base / APP_NAME
    else:
        d = Path.home() / ".lodestar-agent"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


# /token 페이지의 "에이전트 exe(토큰 내장)"가 exe 꼬리에 붙이는 설정 overlay 마커.
# PyInstaller 부트로더는 파일 끝 4KB 안에서 아카이브 cookie를 찾으므로
# overlay는 수백 바이트 수준이어야 한다(서버 라우트 주석 참고).
_EXE_MARKER = b"LSAGENTCFG1:"


def _parse_overlay(tail: bytes) -> dict:
    """exe 끝부분 바이트에서 overlay JSON을 파싱. 알려진 키만 받는다."""
    i = tail.rfind(_EXE_MARKER)
    if i < 0:
        return {}
    try:
        emb = json.loads(tail[i + len(_EXE_MARKER):].decode("utf-8"))
        return {k: v for k, v in emb.items() if k in DEFAULTS}
    except Exception:
        return {}


def _embedded_config() -> dict:
    """frozen exe 자신의 꼬리에서 내장 설정(서버 URL·토큰)을 읽는다."""
    if not getattr(sys, "frozen", False):
        return {}
    try:
        with open(sys.executable, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            return _parse_overlay(f.read())
    except Exception:
        return {}


def load() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_embedded_config())  # exe 내장값은 기본값 취급 — 저장된 설정이 우선
    p = config_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save(cfg: dict) -> None:
    config_path().write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_configured(cfg: dict) -> bool:
    # Drive 폴더는 선택(비우면 로컬 저장 모드) — URL·토큰만 필수.
    return bool(cfg.get("lodestar_url") and cfg.get("api_token"))


# ---------- 로그 ----------

_LOG_MAX = 1_000_000  # 1MB 넘으면 .1로 밀고 새로 시작


def log_path() -> Path:
    return config_dir() / "agent.log"


def log(msg: str) -> None:
    import datetime

    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass  # --windowed exe는 stdout이 없고, cp949 콘솔은 일부 문자 인코딩 불가
    try:
        p = log_path()
        if p.exists() and p.stat().st_size > _LOG_MAX:
            p.replace(p.with_suffix(".log.1"))
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def exe_path() -> Path:
    """frozen(PyInstaller)일 때 실행파일 경로, 아니면 main.py 경로."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(__file__).parent / "main.py"
