@echo off
cd /d "%~dp0backend"
"..\.venv\Scripts\python.exe" -m app.tools.backup
pause
