@echo off
rem Double-click to start the MiniTube server. yt-dlp is updated first, because YouTube changes often.
cd /d "%~dp0"
python -m pip install --user -q -U yt-dlp
python server.py
pause
