@echo off
title VAPT Host Discovery Agent
cd /d "%~dp0"

echo ============================================
echo  VAPT Platform - Host Discovery Agent
echo ============================================

:: Check if venv exists, create if not
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [!] Python not found. Please install Python 3.8+ from python.org
        pause
        exit /b 1
    )
    echo [*] Installing dependencies...
    .venv\Scripts\pip install -r requirements.txt --quiet
)

echo [+] Starting host agent on http://localhost:9999
echo [+] Keep this window open while using VAPT Platform
echo.
.venv\Scripts\python agent.py

pause
