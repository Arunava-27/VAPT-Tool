@echo off
:: VAPT Platform - Native Worker Launcher
:: Double-click this to start nmap, ZAP, and Metasploit workers natively on Windows
:: Workers connect to Docker infra (RabbitMQ, Redis, PostgreSQL) via localhost

title VAPT Native Workers

echo.
echo  VAPT Platform - Native Worker Launcher
echo  ========================================
echo  Starting nmap, ZAP, and Metasploit workers natively...
echo  Workers will connect to Docker infra on localhost.
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [XX] Python not found in PATH.
    echo       Install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Launch PowerShell script
powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0start-native.ps1" %*

:: Keep window open if launched via double-click (not from terminal)
if "%TERM_PROGRAM%"=="" pause
