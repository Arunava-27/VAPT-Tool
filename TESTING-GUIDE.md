# VAPT Platform - Testing Guide & Current Status

**Date:** 2026-03-27  
**Phase:** 3 Complete - Ready for Testing  
**Status:** Infrastructure Running, Database Initialization Required

---

## 🎯 Current Status

### ✅ What's Running
```
CONTAINER          STATUS            PORTS
vapt-postgres      Up 51min (healthy)  5432/tcp
vapt-redis         Up 51min (healthy)  6379/tcp
vapt-rabbitmq      Up 51min (healthy)  5672/tcp, 15672/tcp (management UI)
vapt-elasticsearch Up 51min (healthy)  9200/tcp
vapt-minio         Up 51min (healthy)  9000-9001/tcp
vapt-worker-nmap   Up 48min           (worker process)
```

### ⏳ Needs Setup
- Database schema initialization
- API Gateway service startup
- Orchestrator service startup
- Additional workers (ZAP, Trivy, Prowler, Metasploit)

---

## 📋 Testing Checklist

### Phase 1: Database Initialization

**Option A: Using Docker Exec (Recommended)**

```bash
# Access PostgreSQL container
docker exec -it vapt-postgres psql -U vapt_user -d vapt_platform

# Create tables (SQL commands)
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    contact_email VARCHAR(255),
    schema_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE,
    tenant_id UUID REFERENCES tenants(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    scan_type VARCHAR(50) NOT NULL,
    target VARCHAR(500) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    scan_config JSONB,
    result_summary JSONB,
    error TEXT,
    tenant_id UUID REFERENCES tenants(id),
    created_by_id UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

# Insert default tenant
INSERT INTO tenants (name, slug, contact_email, schema_name, is_active)
VALUES ('Default Organization', 'default', 'admin@vapt-platform.local', 'default', TRUE)
RETURNING id;

# Note the tenant_id returned, then create superuser (replace <tenant-id>)
# Password hash for 'changeme123' (bcrypt)
INSERT INTO users (email, hashed_password, full_name, is_superuser, is_verified, is_active, tenant_id)
VALUES (
    'admin@vapt-platform.local', 
    '$2b$12$abcdefghijklmnopqrstuv', -- Replace with actual hash
    'Super Administrator', 
    TRUE, 
    TRUE, 
    TRUE, 
    '<tenant-id>'  -- Replace with actual UUID
);
```

**Option B: Using init_db.py (Requires Python + Dependencies)**

```bash
cd api-gateway
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
# or
source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
python init_db.py
```

---

### Phase 2: Start API Gateway

**Option A: Docker Compose**

```bash
# Start API Gateway service
docker-compose --profile api up -d

# Check logs
docker logs vapt-api-gateway

# Test health endpoint
curl http://localhost:8000/health
```

**Option B: Local Development**

```bash
cd api-gateway
.\venv\Scripts\Activate.ps1

# Set environment variables
$env:DATABASE_URL="postgresql://vapt_user:vapt_password@localhost:5432/vapt_platform"
$env:JWT_SECRET_KEY="your-secret-key-here"
$env:REDIS_HOST="localhost"
$env:RABBITMQ_HOST="localhost"

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Phase 3: Test Authentication

**1. Login**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@vapt-platform.local",
    "password": "changeme123"
  }'
```

**Expected Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**2. Get Current User**

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

### Phase 4: Test Scan Creation

**1. Create a Scan**

```bash
curl -X POST http://localhost:8000/api/v1/scans \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Network Scan",
    "description": "Testing scan orchestration",
    "scan_type": "network",
    "targets": [
      {
        "type": "ip",
        "value": "192.168.1.1",
        "ports": [80, 443, 22]
      }
    ],
    "options": {
      "profile": "quick",
      "timeout": 1800,
      "max_parallel_workers": 3
    },
    "priority": "normal"
  }'
```

**Expected Response:**
```json
{
  "id": "uuid-here",
  "name": "Test Network Scan",
  "status": "queued",
  "scan_type": "network",
  "target": "192.168.1.1",
  "created_at": "2026-03-27T20:00:00Z",
  ...
}
```

**2. Check Scan Status**

```bash
curl http://localhost:8000/api/v1/scans/<scan-id>/status \
  -H "Authorization: Bearer <access_token>"
```

**Expected Response:**
```json
{
  "id": "uuid",
  "status": "scanning",
  "progress_percentage": 45,
  "current_phase": "scanning",
  "vulnerabilities_found": 3,
  "started_at": "2026-03-27T20:00:00Z",
  "completed_at": null,
  "error": null
}
```

**3. List Scans**

```bash
curl http://localhost:8000/api/v1/scans \
  -H "Authorization: Bearer <access_token>"
```

---

### Phase 5: Start All Workers

```bash
# Start all workers
docker-compose --profile workers up -d

# Check worker status
docker ps | grep worker

# View worker logs
docker logs vapt-worker-nmap
docker logs vapt-worker-zap
docker logs vapt-worker-trivy
docker logs vapt-worker-prowler
docker logs vapt-worker-metasploit
```

---

### Phase 6: Monitor RabbitMQ

**Access RabbitMQ Management UI:**
- URL: http://localhost:15672
- Username: `admin`
- Password: `admin123`

**Check:**
- Queues: `nmap`, `zap`, `trivy`, `prowler`, `metasploit`
- Connections: Workers should be connected
- Messages: Tasks should appear when scans are created

---

## 🔍 Verification Tests

### Test 1: Infrastructure Health

```bash
# PostgreSQL
docker exec vapt-postgres pg_isready -U vapt_user -d vapt_platform

# Redis
docker exec vapt-redis redis-cli ping

# RabbitMQ
docker exec vapt-rabbitmq rabbitmqctl status

# Expected: All should return success
```

### Test 2: Database Connectivity

```bash
docker exec -it vapt-postgres psql -U vapt_user -d vapt_platform -c "\dt"

# Expected: List of tables (tenants, users, scans)
```

### Test 3: API Gateway Endpoints

```bash
# Health check
curl http://localhost:8000/health

# API docs (if DEBUG=true)
curl http://localhost:8000/docs

# OpenAPI spec
curl http://localhost:8000/api/v1/openapi.json
```

### Test 4: Worker Connectivity

```bash
# Check RabbitMQ queues
docker exec vapt-rabbitmq rabbitmqctl list_queues name messages consumers

# Expected: Queues exist with consumers connected
```

---

## 🐛 Common Issues & Solutions

### Issue 1: Database Not Initialized

**Symptom:** API returns "relation does not exist" errors

**Solution:**
```bash
# Run init script manually or create tables via psql
docker exec -it vapt-postgres psql -U vapt_user -d vapt_platform
# Then run CREATE TABLE commands from above
```

### Issue 2: Workers Not Connecting

**Symptom:** No consumers in RabbitMQ queues

**Solution:**
```bash
# Check worker logs
docker logs vapt-worker-nmap

# Restart workers
docker-compose --profile workers restart
```

### Issue 3: Authentication Fails

**Symptom:** 401 Unauthorized errors

**Solution:**
- Verify JWT_SECRET_KEY is set in .env
- Check password hash was created correctly
- Ensure user exists in database: `SELECT * FROM users;`

### Issue 4: Scan Not Starting

**Symptom:** Scan status stays "pending"

**Solution:**
- Check orchestrator logs
- Verify workers are running
- Check RabbitMQ for task messages
- Ensure database connection is working

---

## 📊 Expected Results

### Successful Test Run

1. **Database Initialized**
   - 3 tables created (tenants, users, scans)
   - Default tenant created
   - Superuser created

2. **API Gateway Running**
   - Health endpoint responds: `{"status": "healthy"}`
   - Login successful with JWT tokens
   - Protected endpoints require authentication

3. **Scan Workflow**
   - Scan creation returns queued status
   - Status progresses: pending → queued → preparing → scanning → analyzing → completed
   - Progress percentage increases (0% → 100%)
   - Vulnerabilities found and aggregated

4. **Workers Active**
   - All 5 workers running
   - Connected to RabbitMQ
   - Processing tasks from queues
   - Returning results to orchestrator

---

## 🎯 Next Steps After Successful Testing

1. **Phase 5: AI Agent Engine**
   - Build LLM-powered security agents
   - Implement recon, strategy, exploitation, triage, reporting agents
   - Add AI-enhanced scan analysis

2. **Phase 6: Data Layer**
   - Complete Elasticsearch integration
   - Set up MinIO buckets
   - Implement backup strategy

3. **Phase 7: Frontend Dashboard**
   - Build React UI
   - Real-time scan monitoring
   - Vulnerability management interface

4. **Phase 8: Private Network Features**
   - Air-gap mode
   - Proxy support
   - Offline updates

---

## 📝 Quick Start Commands

```bash
# 1. Verify infrastructure
docker ps

# 2. Initialize database (choose one method above)

# 3. Start API Gateway
docker-compose --profile api up -d

# 4. Test login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vapt-platform.local","password":"changeme123"}'

# 5. Create test scan (use token from step 4)
curl -X POST http://localhost:8000/api/v1/scans \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Scan","scan_type":"network","targets":[{"type":"ip","value":"8.8.8.8"}]}'

# 6. Start workers
docker-compose --profile workers up -d

# 7. Monitor progress
curl http://localhost:8000/api/v1/scans/<scan-id>/status \
  -H "Authorization: Bearer <token>"
```

---

## 🔗 Useful URLs

- **API Gateway:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **RabbitMQ Management:** http://localhost:15672
- **Elasticsearch:** http://localhost:9200
- **MinIO Console:** http://localhost:9001

---

## 📚 Documentation

- **Phase 1:** INFRASTRUCTURE-TEST-RESULTS.md
- **Phase 2:** PHASE2-API-GATEWAY-COMPLETE.md
- **Phase 3:** PHASE3-ORCHESTRATOR-COMPLETE.md
- **Phase 4:** PHASE4-WORKERS-COMPLETE.md

---

**Ready to test! Start with database initialization and work through the phases above.**
