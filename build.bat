@echo off
REM Windows 배포용 단일 exe 빌드. Python 3.11+ 및 pip 필요.
pip install -r requirements.txt pyinstaller
python robot_icon.py icon.ico
pyinstaller --noconfirm --onefile --windowed --name LodestarAgent ^
  --icon icon.ico --hidden-import pystray._win32 main.py
echo.
echo dist\LodestarAgent.exe 생성 완료 — GitHub Release 자산으로 업로드하세요.
