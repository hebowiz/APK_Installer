@echo off
setlocal
cd /d "%~dp0"
call setup.bat
if errorlevel 1 goto failed
".venv\Scripts\python.exe" adb_apk_installer.py
if errorlevel 1 goto failed
exit /b 0
:failed
pause
exit /b 1
