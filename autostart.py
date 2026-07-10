"""부팅 자동시작 — HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.

관리자 권한 불필요(현재 사용자 로그인 시 실행). 비Windows에서는 no-op.
"""

import os
import sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "LodestarAgent"


def _cmd() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    # 개발 모드: 파이썬으로 main.py 실행
    main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{sys.executable}" "{main}" --minimized'


def enable() -> bool:
    if os.name != "nt":
        return False
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, _cmd())
    return True


def disable() -> None:
    if os.name != "nt":
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
    except FileNotFoundError:
        pass


def is_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            winreg.QueryValueEx(k, NAME)
        return True
    except FileNotFoundError:
        return False
