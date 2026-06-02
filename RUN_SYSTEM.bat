@echo off
REM bilsem_beyin System Launcher
REM Windows batch script to run the CFD/FEA/ML GUI

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ================================================================================
echo   bilsem_beyin CFD/FEA/ML Parametric Analysis System
echo ================================================================================
echo.

REM Check Python
python --version >NUL 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ first.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

REM Check key packages
echo [INFO] Verifying system...
python verify_system.py

echo.
echo [INFO] Starting GUI application...
echo.

REM Launch GUI
python app_parametric.py

pause
