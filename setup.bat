@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto check_venv
py -3.11 -c "import sys; sys.exit(0 if sys.version_info[:3] == (3, 11, 9) else 1)"
if errorlevel 1 goto no_python
py -3.11 -m venv .venv
if errorlevel 1 goto failed
:check_venv
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:3] == (3, 11, 9) and sys.prefix != sys.base_prefix else 1)"
if errorlevel 1 goto wrong_version
".venv\Scripts\python.exe" -c "import tkinter; import sys; print('Virtual environment ready: Python ' + sys.version.split()[0])"
if errorlevel 1 goto failed
exit /b 0
:no_python
echo Python 3.11.9 and the Windows Python launcher are required.
exit /b 1
:wrong_version
echo The existing .venv is not a Python 3.11.9 virtual environment.
echo Rename .venv and run setup.bat again.
exit /b 1
:failed
echo Setup failed. See the error above.
exit /b 1
