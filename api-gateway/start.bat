@echo off
:: ─── VAPT Platform API Gateway — Native Host Start ────────────────────────────
:: Runs FastAPI api-gateway directly on the host machine (no Docker).
:: Prerequisites: Python 3.11+, data layer Docker containers running.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo  VAPT Platform API Gateway
echo  Native mode — connecting to Docker data layer
echo ============================================================

:: ── Step 1: Create virtual environment if needed ────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [!] Failed to create virtual environment. Is Python installed?
        pause & exit /b 1
    )
)

:: ── Step 2: Install / upgrade dependencies ──────────────────────────────────
echo [*] Installing dependencies...
.venv\Scripts\pip.exe install -r requirements.txt -q --no-warn-script-location
if errorlevel 1 (
    echo [!] pip install failed.
    pause & exit /b 1
)

:: ── Step 3: Run DB migrations ────────────────────────────────────────────────
echo [*] Running database migrations...
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 (
    echo [!] Alembic migration failed. Is PostgreSQL running on port 5433?
    pause & exit /b 1
)

:: ── Step 4: Create superuser if needed ──────────────────────────────────────
.venv\Scripts\python.exe init_db.py 2>nul

:: ── Step 5: Start uvicorn ────────────────────────────────────────────────────
echo.
echo [*] Starting API Gateway on http://localhost:8000
echo [*] Press Ctrl+C to stop
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
