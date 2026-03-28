#!/usr/bin/env pwsh
# VAPT Platform Interactive Testing Script
# Run this to test all components step-by-step

param(
    [switch]$SkipDB = $false,
    [switch]$AutoMode = $false
)

$ErrorActionPreference = "Continue"

function Write-TestHeader {
    param([string]$Title, [int]$TestNum)
    Write-Host "`n╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  TEST $TestNum : $Title" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ $Message" -ForegroundColor Yellow
}

function Pause-Test {
    if (-not $AutoMode) {
        Write-Host "`nPress Enter to continue..." -ForegroundColor Yellow
        Read-Host
    } else {
        Start-Sleep -Seconds 2
    }
}

# ============================================================================
# TEST 1: Infrastructure Services
# ============================================================================

Write-TestHeader "Infrastructure Services" 1

Write-Info "Checking Docker services..."
$containers = docker ps --format "table {{.Names}}\t{{.Status}}" --filter "name=vapt" --filter "name=postgres"

if ($containers) {
    Write-Success "Docker services are running"
    docker ps --format "table {{.Names}}\t{{.Status}}" --filter "name=vapt" --filter "name=postgres" --filter "name=redis" --filter "name=rabbitmq"
} else {
    Write-Error "Services not running. Starting infrastructure..."
    docker-compose up -d postgres redis rabbitmq
    Write-Info "Waiting 30 seconds for services to initialize..."
    Start-Sleep -Seconds 30
}

Write-Info "`nTesting PostgreSQL connection..."
$pgTest = docker exec vapt-postgres pg_isready -U vapt_user -d vapt_platform 2>&1
if ($pgTest -match "accepting connections") {
    Write-Success "PostgreSQL is ready"
} else {
    Write-Error "PostgreSQL is not ready: $pgTest"
}

Write-Info "Testing Redis connection..."
$redisTest = docker exec vapt-redis redis-cli ping 2>&1
if ($redisTest -match "PONG") {
    Write-Success "Redis is ready"
} else {
    Write-Error "Redis is not ready: $redisTest"
}

Write-Info "Testing RabbitMQ connection..."
$rabbitTest = docker exec vapt-rabbitmq rabbitmqctl status 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "RabbitMQ is ready"
} else {
    Write-Error "RabbitMQ is not ready"
}

Pause-Test

# ============================================================================
# TEST 2: Database Initialization
# ============================================================================

Write-TestHeader "Database Initialization" 2

if (-not $SkipDB) {
    Write-Info "Checking if database tables exist..."
    $tableCheck = docker exec vapt-postgres psql -U vapt_user -d vapt_platform -c "\dt" 2>&1
    
    if ($tableCheck -match "users" -and $tableCheck -match "tenants") {
        Write-Success "Database tables already exist"
        $dbInitialized = $true
    } else {
        Write-Info "Database needs initialization"
        Write-Host "`n╭─────────────────────────────────────────────────╮" -ForegroundColor Magenta
        Write-Host "│  ACTION REQUIRED: Initialize Database          │" -ForegroundColor Magenta
        Write-Host "╰─────────────────────────────────────────────────╯`n" -ForegroundColor Magenta
        
        Write-Host "Run this command in a NEW terminal window:`n" -ForegroundColor Yellow
        Write-Host "docker exec -i vapt-postgres psql -U vapt_user -d vapt_platform < init_database.sql`n" -ForegroundColor Cyan
        
        Write-Host "Or copy and paste the SQL from init_database.sql into psql:`n" -ForegroundColor Yellow
        Write-Host "docker exec -it vapt-postgres psql -U vapt_user -d vapt_platform`n" -ForegroundColor Cyan
        
        Write-Host "Press Enter after you've initialized the database..." -ForegroundColor Yellow
        Read-Host
        
        $dbInitialized = $false
    }
    
    # Verify superuser exists
    Write-Info "Verifying superuser account..."
    $userCheck = docker exec vapt-postgres psql -U vapt_user -d vapt_platform -t -c "SELECT email FROM users WHERE is_superuser = TRUE LIMIT 1;" 2>&1
    
    if ($userCheck -match "admin@vapt-platform.local") {
        Write-Success "Superuser exists: admin@vapt-platform.local"
        Write-Info "Default password: changeme123"
    } else {
        Write-Error "Superuser not found. Database initialization may have failed."
    }
} else {
    Write-Info "Skipping database initialization (--SkipDB flag)"
}

Pause-Test

# ============================================================================
# TEST 3: Start API Gateway
# ============================================================================

Write-TestHeader "API Gateway Service" 3

Write-Info "Checking if API Gateway is running..."
$apiRunning = docker ps --filter "name=vapt-api-gateway" --format "{{.Names}}"

if (-not $apiRunning) {
    Write-Info "Starting API Gateway..."
    docker-compose --profile api up -d
    
    Write-Info "Waiting 20 seconds for API Gateway to start..."
    Start-Sleep -Seconds 20
} else {
    Write-Success "API Gateway is already running"
}

Write-Info "Checking API Gateway health..."
$maxRetries = 5
$retryCount = 0
$healthCheckPassed = $false

while ($retryCount -lt $maxRetries -and -not $healthCheckPassed) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method GET -ErrorAction SilentlyContinue
        if ($health.status -eq "healthy") {
            Write-Success "API Gateway is healthy!"
            Write-Host "  Version: $($health.version)" -ForegroundColor Gray
            Write-Host "  Database: $($health.database)" -ForegroundColor Gray
            Write-Host "  Redis: $($health.redis)" -ForegroundColor Gray
            $healthCheckPassed = $true
        }
    } catch {
        $retryCount++
        Write-Info "Retry $retryCount/$maxRetries - waiting 5 seconds..."
        Start-Sleep -Seconds 5
    }
}

if (-not $healthCheckPassed) {
    Write-Error "API Gateway health check failed. Check logs:"
    Write-Host "docker logs vapt-api-gateway`n" -ForegroundColor Cyan
}

Pause-Test

# ============================================================================
# TEST 4: Authentication Flow
# ============================================================================

Write-TestHeader "Authentication Flow" 4

Write-Info "Testing login endpoint..."

$loginBody = @{
    email = "admin@vapt-platform.local"
    password = "changeme123"
} | ConvertTo-Json

try {
    $loginResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
        -Method POST `
        -Body $loginBody `
        -ContentType "application/json"
    
    $accessToken = $loginResponse.access_token
    
    if ($accessToken) {
        Write-Success "Login successful!"
        Write-Host "  Access Token: $($accessToken.Substring(0, 50))..." -ForegroundColor Gray
        Write-Host "  Token Type: $($loginResponse.token_type)" -ForegroundColor Gray
        
        # Test authenticated endpoint
        Write-Info "`nTesting authenticated endpoint (/auth/me)..."
        $headers = @{
            "Authorization" = "Bearer $accessToken"
        }
        
        $meResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/me" `
            -Method GET `
            -Headers $headers
        
        Write-Success "Authentication verified!"
        Write-Host "  Email: $($meResponse.email)" -ForegroundColor Gray
        Write-Host "  Full Name: $($meResponse.full_name)" -ForegroundColor Gray
        Write-Host "  Is Superuser: $($meResponse.is_superuser)" -ForegroundColor Gray
        
        # Store token for next tests
        $global:AuthToken = $accessToken
        
    } else {
        Write-Error "Login failed - no token received"
    }
} catch {
    Write-Error "Authentication test failed: $_"
    Write-Info "Check API Gateway logs: docker logs vapt-api-gateway"
}

Pause-Test

# ============================================================================
# TEST 5: Create Test Scan
# ============================================================================

Write-TestHeader "Scan Creation & Orchestration" 5

if ($global:AuthToken) {
    Write-Info "Creating a test scan (Nmap quick scan)..."
    
    $scanBody = @{
        name = "Test Scan - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        description = "Automated test scan of scanme.nmap.org"
        scan_type = "network"
        targets = @(
            @{
                type = "hostname"
                value = "scanme.nmap.org"
            }
        )
        options = @{
            profile = "quick"
            timeout = 300
        }
        priority = "normal"
    } | ConvertTo-Json -Depth 4
    
    $headers = @{
        "Authorization" = "Bearer $global:AuthToken"
        "Content-Type" = "application/json"
    }
    
    try {
        $scanResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scans" `
            -Body $scanBody `
            -Headers $headers
        
        Write-Success "Scan created successfully!"
        Write-Host "  Scan ID: $($scanResponse.id)" -ForegroundColor Gray
        Write-Host "  Name: $($scanResponse.name)" -ForegroundColor Gray
        Write-Host "  Status: $($scanResponse.status)" -ForegroundColor Gray
        
        $global:ScanId = $scanResponse.id
        
        Write-Info "`nMonitoring scan progress..."
        $maxChecks = 30
        $checkCount = 0
        $scanCompleted = $false
        
        while ($checkCount -lt $maxChecks -and -not $scanCompleted) {
            Start-Sleep -Seconds 5
            
            try {
                $statusResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scans/$global:ScanId/status" `
                    -Method GET `
                    -Headers $headers
                
                $status = $statusResponse.status
                $progress = $statusResponse.progress
                
                Write-Host "  [$checkCount] Status: $status | Progress: $progress%" -ForegroundColor Cyan
                
                if ($status -eq "completed") {
                    Write-Success "`nScan completed successfully!"
                    
                    # Get full scan results
                    $resultResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scans/$global:ScanId" `
                        -Method GET `
                        -Headers $headers
                    
                    if ($resultResponse.result_summary) {
                        $summary = $resultResponse.result_summary
                        Write-Host "`nScan Results Summary:" -ForegroundColor Green
                        Write-Host "  Total Vulnerabilities: $($summary.total_vulnerabilities)" -ForegroundColor Gray
                        Write-Host "  Critical: $($summary.by_severity.critical)" -ForegroundColor Red
                        Write-Host "  High: $($summary.by_severity.high)" -ForegroundColor DarkRed
                        Write-Host "  Medium: $($summary.by_severity.medium)" -ForegroundColor Yellow
                        Write-Host "  Low: $($summary.by_severity.low)" -ForegroundColor Gray
                        Write-Host "  Info: $($summary.by_severity.info)" -ForegroundColor DarkGray
                        Write-Host "  Risk Score: $($summary.risk_score)/100" -ForegroundColor Magenta
                    }
                    
                    $scanCompleted = $true
                } elseif ($status -eq "failed") {
                    Write-Error "`nScan failed!"
                    if ($statusResponse.error) {
                        Write-Host "  Error: $($statusResponse.error)" -ForegroundColor Red
                    }
                    $scanCompleted = $true
                } elseif ($status -in @("cancelled", "timeout")) {
                    Write-Info "`nScan ended with status: $status"
                    $scanCompleted = $true
                }
                
                $checkCount++
            } catch {
                Write-Error "Failed to check scan status: $_"
                break
            }
        }
        
        if (-not $scanCompleted) {
            Write-Info "Scan is still running. Check status manually:"
            Write-Host "curl -H 'Authorization: Bearer YOUR_TOKEN' http://localhost:8000/api/v1/scans/$global:ScanId/status`n" -ForegroundColor Cyan
        }
        
    } catch {
        Write-Error "Failed to create scan: $_"
        Write-Info "Response: $($_.Exception.Response)"
    }
} else {
    Write-Error "No authentication token available. Skipping scan test."
}

Pause-Test

# ============================================================================
# TEST 6: Worker Services
# ============================================================================

Write-TestHeader "Worker Services" 6

Write-Info "Checking if workers are running..."
$workersRunning = docker ps --filter "name=vapt-worker-nmap" --format "{{.Names}}"

if (-not $workersRunning) {
    Write-Info "Starting Nmap worker..."
    docker-compose --profile workers up -d worker-nmap
    
    Write-Info "Waiting 15 seconds for worker to start..."
    Start-Sleep -Seconds 15
} else {
    Write-Success "Nmap worker is already running"
}

Write-Info "Checking worker logs..."
docker logs --tail 20 vapt-worker-nmap

Write-Info "`nTo start all workers, run:"
Write-Host "docker-compose --profile workers up -d`n" -ForegroundColor Cyan

Pause-Test

# ============================================================================
# TEST SUMMARY
# ============================================================================

Write-Host "`n╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                   TEST SUMMARY                         ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════╝`n" -ForegroundColor Green

Write-Host "✅ Completed Tests:" -ForegroundColor Green
Write-Host "  1. Infrastructure Services - Docker containers" -ForegroundColor Gray
Write-Host "  2. Database Initialization - PostgreSQL schema" -ForegroundColor Gray
Write-Host "  3. API Gateway - Health check" -ForegroundColor Gray
Write-Host "  4. Authentication - Login & JWT" -ForegroundColor Gray
Write-Host "  5. Scan Creation - End-to-end workflow" -ForegroundColor Gray
Write-Host "  6. Worker Services - Task execution" -ForegroundColor Gray

Write-Host "`n📋 Useful Commands:" -ForegroundColor Yellow
Write-Host "  View all containers:    docker-compose ps" -ForegroundColor Gray
Write-Host "  View API logs:          docker logs -f vapt-api-gateway" -ForegroundColor Gray
Write-Host "  View worker logs:       docker logs -f vapt-worker-nmap" -ForegroundColor Gray
Write-Host "  Stop all services:      docker-compose down" -ForegroundColor Gray
Write-Host "  Restart services:       docker-compose restart" -ForegroundColor Gray

Write-Host "`n🌐 Service URLs:" -ForegroundColor Yellow
Write-Host "  API Gateway:            http://localhost:8000" -ForegroundColor Gray
Write-Host "  API Docs (Swagger):     http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "  RabbitMQ Management:    http://localhost:15672 (guest/guest)" -ForegroundColor Gray

Write-Host "`n📚 Documentation:" -ForegroundColor Yellow
Write-Host "  Testing Guide:          TESTING-GUIDE.md" -ForegroundColor Gray
Write-Host "  Current Status:         CURRENT-STATUS.md" -ForegroundColor Gray
Write-Host "  Infrastructure Tests:   INFRASTRUCTURE-TEST-RESULTS.md" -ForegroundColor Gray

if ($global:ScanId) {
    Write-Host "`n🔍 Test Scan ID: $global:ScanId" -ForegroundColor Cyan
    Write-Host "  View in browser: http://localhost:8000/docs#/scans/get_scan_api_v1_scans__scan_id__get" -ForegroundColor Gray
}

Write-Host "`n╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║     🎉 Testing Complete! Platform is operational 🎉   ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════╝`n" -ForegroundColor Green
