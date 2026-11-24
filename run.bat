@echo off
rem Double-click to start the MiniTube server. yt-dlp is updated first, because YouTube changes often.
cd /d "%~dp0"
rem Some Python installs ship without pip; bootstrap it if missing.
python -m pip --version >nul 2>&1 || python -m ensurepip --upgrade
python -m pip install --user -q -U yt-dlp
python server.py
pause
