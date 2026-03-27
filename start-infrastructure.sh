#!/bin/bash
# VAPT Platform - Infrastructure Startup Script

set -e

echo "=========================================="
echo "VAPT Platform - Starting Infrastructure"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found. Using default configuration.${NC}"
    echo "For production, copy .env.template to .env and customize."
    echo ""
fi

# Function to check if service is healthy
check_service() {
    local service=$1
    local max_attempts=30
    local attempt=1
    
    echo -n "Waiting for $service to be healthy..."
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose ps | grep $service | grep -q "healthy"; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo -e " ${RED}✗ (timeout)${NC}"
    return 1
}

echo "Step 1: Starting Data Layer Services"
echo "--------------------------------------"
docker-compose up -d postgres redis rabbitmq elasticsearch minio

echo ""
echo "Step 2: Waiting for services to be healthy..."
echo "--------------------------------------"

check_service "postgres" || echo -e "${RED}PostgreSQL failed to start${NC}"
check_service "redis" || echo -e "${RED}Redis failed to start${NC}"
check_service "rabbitmq" || echo -e "${RED}RabbitMQ failed to start${NC}"
check_service "elasticsearch" || echo -e "${RED}Elasticsearch failed to start${NC}"
check_service "minio" || echo -e "${RED}MinIO failed to start${NC}"

echo ""
echo "=========================================="
echo "Infrastructure Status"
echo "=========================================="
docker-compose ps

echo ""
echo "=========================================="
echo "Access Points"
echo "=========================================="
echo -e "${GREEN}✓${NC} PostgreSQL:        localhost:5432"
echo -e "${GREEN}✓${NC} Redis:             localhost:6379"
echo -e "${GREEN}✓${NC} RabbitMQ UI:       http://localhost:15672 (guest/guest)"
echo -e "${GREEN}✓${NC} Elasticsearch:     http://localhost:9200"
echo -e "${GREEN}✓${NC} MinIO Console:     http://localhost:9001 (minioadmin/minioadmin123)"

echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo "1. Start Nmap worker:"
echo "   docker-compose --profile workers up -d worker-nmap"
echo ""
echo "2. Test with existing test script:"
echo "   python test_task.py"
echo ""
echo "3. When ready, start other services:"
echo "   docker-compose --profile api up -d"
echo "   docker-compose --profile workers up -d"
echo ""
echo "4. View logs:"
echo "   docker-compose logs -f"
echo ""
echo "=========================================="
echo -e "${GREEN}Infrastructure is ready!${NC}"
echo "=========================================="
