# VAPT Platform - Quick Start Guide

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum (16GB recommended)
- 50GB free disk space

## Quick Start

### 1. Clone and Configure

```bash
cd E:\personal\VAPT-Tool

# Environment is already created with default values
# Edit .env if you need to customize settings
```

### 2. Start Infrastructure Services

Start only the data layer services first:

```bash
docker-compose up -d postgres redis rabbitmq elasticsearch minio
```

Wait for services to be healthy (check with `docker-compose ps`).

### 3. Start Core Services (when ready)

```bash
# Start API Gateway and Orchestrator
docker-compose --profile api up -d

# Start Workers
docker-compose --profile workers up -d

# Start AI Engine (optional, requires LLM)
docker-compose --profile ai up -d

# Start Frontend (optional, not yet implemented)
docker-compose --profile frontend up -d
```

### 4. Start Monitoring (optional)

```bash
docker-compose --profile monitoring up -d
```

## Current Development Status

✅ **Phase 1 - Infrastructure**: COMPLETED
- Docker Compose configuration
- Network isolation setup
- Persistent volumes
- Environment configuration
- Health checks

⏳ **Phase 2 - API Gateway**: NOT STARTED
⏳ **Phase 3 - Orchestrator**: NOT STARTED
🔄 **Phase 4 - Workers**: PARTIALLY DONE (Nmap only)
⏳ **Phase 5 - AI Engine**: NOT STARTED
⏳ **Phase 6 - Data Layer**: NOT STARTED
⏳ **Phase 7 - Frontend**: NOT STARTED

## Testing Infrastructure Only

To test the current infrastructure setup:

```bash
# Start only data services
docker-compose up -d postgres redis rabbitmq elasticsearch minio

# Check health status
docker-compose ps

# View logs
docker-compose logs -f

# Test Nmap worker (existing implementation)
docker-compose --profile workers up -d worker-nmap

# Run test script
python test_task.py
```

## Access Points

- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)
- **Elasticsearch**: http://localhost:9200
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin123)
- **API Gateway**: http://localhost:8000 (not yet implemented)
- **Frontend**: http://localhost:3000 (not yet implemented)
- **Grafana**: http://localhost:3001 (admin/admin123)

## Next Steps

1. Implement API Gateway (Phase 2)
2. Implement Scan Orchestrator (Phase 3)
3. Expand Workers (ZAP, Trivy, Prowler, Metasploit)
4. Build AI Agent Engine (Phase 5)

## Troubleshooting

### Services not starting

```bash
# Check logs
docker-compose logs [service-name]

# Restart services
docker-compose restart [service-name]
```

### Port conflicts

Edit `.env` file to change exposed ports if needed.

### Permission issues on Linux

```bash
# Fix volume permissions
sudo chown -R $USER:$USER data/
```

## Cleanup

```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove images
docker-compose down --rmi all
```

## Networks

The platform uses isolated networks for security:

- **frontend-network**: Public-facing services (API, Frontend)
- **backend-network**: Internal services communication
- **data-network**: Database access (isolated from internet)
- **scan-network**: Workers performing scans (internet access)

## Profiles

Use profiles to start only needed components:

- `api`: API Gateway and Orchestrator
- `workers`: All security tool workers
- `ai`: AI Engine with Ollama
- `frontend`: React dashboard
- `monitoring`: Prometheus and Grafana
- `local-llm`: Local LLM server

Example:
```bash
docker-compose --profile api --profile workers up -d
```
