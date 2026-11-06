@echo off
setlocal
cd /d "%~dp0"
call setup.bat
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --specpath build --name ADB_APK_Installer adb_apk_installer.py
if errorlevel 1 goto failed
echo.
echo Build complete: dist\ADB_APK_Installer.exe
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
