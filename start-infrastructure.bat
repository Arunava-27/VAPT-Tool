@echo off
REM VAPT Platform - Infrastructure Startup Script for Windows

echo ==========================================
echo VAPT Platform - Starting Infrastructure
echo ==========================================
echo.

REM Check if .env exists
if not exist .env (
    echo [WARNING] .env file not found. Using default configuration.
    echo For production, copy .env.template to .env and customize.
    echo.
)

echo Step 1: Starting Data Layer Services
echo --------------------------------------
docker-compose up -d postgres redis rabbitmq elasticsearch minio

echo.
echo Step 2: Waiting for services to be healthy...
echo --------------------------------------
echo This may take 30-60 seconds...
timeout /t 30 /nobreak >nul

echo.
echo ==========================================
echo Infrastructure Status
echo ==========================================
docker-compose ps

echo.
echo ==========================================
echo Access Points
echo ==========================================
echo [OK] PostgreSQL:        localhost:5432
echo [OK] Redis:             localhost:6379
echo [OK] RabbitMQ UI:       http://localhost:15672 (guest/guest)
echo [OK] Elasticsearch:     http://localhost:9200
echo [OK] MinIO Console:     http://localhost:9001 (minioadmin/minioadmin123)

echo.
echo ==========================================
echo Next Steps
echo ==========================================
echo 1. Start Nmap worker:
echo    docker-compose --profile workers up -d worker-nmap
echo.
echo 2. Test with existing test script:
echo    python test_task.py
echo.
echo 3. When ready, start other services:
echo    docker-compose --profile api up -d
echo    docker-compose --profile workers up -d
echo.
echo 4. View logs:
echo    docker-compose logs -f
echo.
echo ==========================================
echo Infrastructure is ready!
echo ==========================================

pause
