"""자동 업데이트 — GitHub Releases 기준.

집에서 새 버전을 배포하는 절차:
  1) version.py의 VERSION 올리고 build.bat으로 exe 빌드
  2) GitHub 저장소(config의 github_repo)에 태그 vX.Y.Z 릴리스 생성,
     자산으로 LodestarAgent.exe(이름에 .exe만 맞으면 됨) 첨부
  3) 학교 PC 에이전트가 6시간 주기(+부팅 시) 확인 → 스스로 교체 후 재시작
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import requests

from config import log
from version import VERSION


def _ver_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3] or [0])


def check_and_apply(github_repo: str) -> bool:
    """새 버전이 있으면 교체를 시작하고 True 반환(호출측은 즉시 종료해야 함)."""
    if not getattr(sys, "frozen", False):
        return False  # 스크립트 실행 중엔 자기교체 생략(개발 모드)
    try:
        r = requests.get(
            f"https://api.github.com/repos/{github_repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json"}, timeout=30,
        )
        if not r.ok:
            return False
        rel = r.json()
        latest = rel.get("tag_name", "")
        if _ver_tuple(latest) <= _ver_tuple(VERSION):
            return False
        asset = next(
            (a for a in rel.get("assets", [])
             if a.get("name", "").lower().endswith(".exe")),
            None,
        )
        if not asset:
            return False
        log(f"업데이트 발견 {VERSION} → {latest}, 다운로드 중…")
        exe = Path(sys.executable)
        new = exe.with_suffix(".exe.new")
        with requests.get(asset["browser_download_url"], stream=True,
                          timeout=600) as dl:
            dl.raise_for_status()
            with new.open("wb") as f:
                for chunk in dl.iter_content(1 << 16):
                    f.write(chunk)
        if new.stat().st_size < 1_000_000:  # 최소 sanity 체크
            new.unlink(missing_ok=True)
            return False

        bat = exe.parent / "ls_update.bat"
        bat.write_text(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'move /Y "{new}" "{exe}" >nul\r\n'
            f'start "" "{exe}" --minimized\r\n'
            'del "%~f0"\r\n',
            # cmd는 배치를 시스템 코드페이지로 읽는다(한국어 Windows=cp949).
            # utf-8로 쓰면 한글 경로(사용자명 등)가 mojibake로 깨져 move가 실패.
            encoding="mbcs",
        )
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True, cwd=str(exe.parent),
        )
        log(f"{latest} 적용을 위해 재시작합니다.")
        return True
    except Exception as e:
        log(f"업데이트 확인 실패: {e}")
        return False
