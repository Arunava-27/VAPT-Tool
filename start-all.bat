@echo off
:: ─── VAPT Platform — Start All Native Services ────────────────────────────────
:: Starts Docker data layer + ai-engine/ollama, then runs api-gateway and
:: frontend natively on the host machine.
::
:: Usage: Double-click or run from cmd.
:: Stop: Close the terminal windows, or run stop-all.bat

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  ██╗   ██╗ █████╗ ██████╗ ████████╗
echo  ██║   ██║██╔══██╗██╔══██╗╚══██╔══╝
echo  ██║   ██║███████║██████╔╝   ██║
echo  ╚██╗ ██╔╝██╔══██║██╔═══╝    ██║
echo   ╚████╔╝ ██║  ██║██║        ██║
echo    ╚═══╝  ╚═╝  ╚═╝╚═╝        ╚═╝
echo.
echo  VAPT Platform — Starting services...
echo  =========================================
echo.

:: ── Step 1: Start Docker data layer ─────────────────────────────────────────
echo [1/5] Starting Docker data layer (postgres, redis, rabbitmq, minio)...
docker compose up -d postgres redis rabbitmq minio vault ai-engine ollama >nul 2>&1
if errorlevel 1 (
    echo [!] Docker compose failed. Is Docker Desktop running?
    pause & exit /b 1
)
echo      Done.

:: ── Step 2: Wait for postgres to be healthy ──────────────────────────────────
echo [2/5] Waiting for PostgreSQL to be ready...
set attempts=0
:wait_pg
docker exec vapt-postgres pg_isready -U vapt_user -d vapt_platform >nul 2>&1
if not errorlevel 1 goto pg_ready
set /a attempts+=1
if %attempts% geq 20 (
    echo [!] PostgreSQL not ready after 20s. Check Docker Desktop.
    pause & exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_pg
:pg_ready
echo      PostgreSQL ready.

:: ── Step 3: Start Host Agent ─────────────────────────────────────────────────
echo [3/5] Starting Host Agent (port 9999)...
cd host-agent
start "VAPT Host Agent" /min cmd /c ".venv\Scripts\python.exe -m uvicorn agent:app --host 0.0.0.0 --port 9999 > logs\agent.log 2>&1"
cd ..
timeout /t 2 /nobreak >nul
echo      Host Agent started.

:: ── Step 4: Start API Gateway ────────────────────────────────────────────────
echo [4/5] Starting API Gateway (port 8000)...
cd api-gateway
set DATABASE_URL=postgresql://vapt_user:changeme123@localhost:5433/vapt_platform
set REDIS_URL=redis://:redis123@localhost:6379/0
set RABBITMQ_URL=amqp://guest:guest@localhost:5672/
set CELERY_BROKER_URL=amqp://guest:guest@localhost:5672/
set CELERY_RESULT_BACKEND=rpc://
set ELASTICSEARCH_URL=http://localhost:9200
set MINIO_ENDPOINT=localhost:9000
set MINIO_ACCESS_KEY=minioadmin
set MINIO_SECRET_KEY=minioadmin123
set SECRET_KEY=supersecretkey-changeme
set JWT_SECRET_KEY=supersecretkey-changeme
set CORS_ORIGINS=http://localhost:3000,http://localhost:5173
set OLLAMA_BASE_URL=http://localhost:11434
start "VAPT API Gateway" cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | tee logs\api-gateway.log"
cd ..
timeout /t 3 /nobreak >nul
echo      API Gateway started.

:: ── Step 5: Start Frontend ───────────────────────────────────────────────────
echo [5/5] Starting Frontend dev server (port 3000)...
cd frontend
start "VAPT Frontend" cmd /c "npm run dev 2>&1"
cd ..
timeout /t 3 /nobreak >nul
echo      Frontend started.

:: ── Step 6: Start Workers ────────────────────────────────────────────────────
echo.
echo [*] Starting native workers (nmap, trivy, prowler)...
echo     To also start ZAP/Metasploit, remove -SkipZap -SkipMsf flags below.
cd workers
start "VAPT Workers" powershell -ExecutionPolicy Bypass -File "start-native.ps1" -SkipZap -SkipMsf
cd ..

echo.
echo =========================================
echo  All services started!
echo.
echo  Frontend:    http://localhost:3000
echo  API Gateway: http://localhost:8000
echo  Host Agent:  http://localhost:9999
echo  RabbitMQ:    http://localhost:15672
echo.
echo  Login: admin@vapt-platform.local / Admin@123
echo =========================================
echo.
pause
