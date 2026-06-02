@echo off
REM bilsem_beyin Launcher - Windows Quick Start
REM Cift tikla calistir

setlocal
cd /d "%~dp0"

REM Python kontrolu
python --version >NUL 2>&1
if errorlevel 1 (
    echo [ERROR] Python bulunamadi. Once Python 3.11+ kurulmali.
    pause
    exit /b 1
)

REM Launcher GUI'yi baslat
start "" pythonw launcher.py
if errorlevel 1 (
    REM pythonw yoksa normal python ile dene
    python launcher.py
)

endlocal
