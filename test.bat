@echo off
setlocal
cd /d "%~dp0"
call setup.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m unittest discover -s tests -v
exit /b %errorlevel%
