#!/bin/bash
set -e

echo '=========================================='
echo ' VAPT API Gateway - starting up'
echo '=========================================='

echo '-> Running database initialisation...'
python init_db.py

echo '-> Running Alembic migrations...'
alembic upgrade head || echo 'Alembic warning - continuing'

echo '-> Starting API server...'
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
