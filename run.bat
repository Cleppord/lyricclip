@echo off
REM Double-click to set up (first time) and start lyricclip in your browser.
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ffmpeg not found - installing it with winget...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the project's Python environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)

echo Installing / checking packages (first run downloads a few hundred MB)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e ".[ui]"
if errorlevel 1 (
  echo.
  echo Package install failed - screenshot the red text above and send it to Claude.
  pause
  exit /b 1
)

echo Starting lyricclip - your browser will open. Keep this window open while you use it.
".venv\Scripts\python.exe" app.py
pause
