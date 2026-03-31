param(
    [switch]$NmapOnly,
    [switch]$SkipMsf,
    [switch]$SkipZap,
    [switch]$SkipProwler,
    [switch]$SkipTrivy
)

$WorkersDir  = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile     = Join-Path $WorkersDir ".native-worker-pids.json"

function Write-Step($msg)  { Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "  [XX] $msg" -ForegroundColor Red }
function Write-Header($msg){ Write-Host "" ; Write-Host "=== $msg ===" -ForegroundColor Magenta }

# Env vars pointing to Docker infra on localhost
$env:CELERY_BROKER_URL     = "amqp://guest:guest@localhost:5672//"
$env:CELERY_RESULT_BACKEND = "redis://:redis123@localhost:6379/0"
$env:DATABASE_URL          = "postgresql://vapt_user:changeme123@localhost:5433/vapt_platform"
$env:MINIO_ENDPOINT        = "localhost:9000"
$env:MINIO_ACCESS_KEY      = "minioadmin"
$env:MINIO_SECRET_KEY      = "minioadmin123"
$env:LOG_LEVEL             = "INFO"
$env:ZAP_HOST              = "localhost"
$env:ZAP_PORT              = "8080"
$env:MSF_RPC_HOST          = "localhost"
$env:MSF_RPC_PORT          = "55553"

Write-Header "VAPT Native Worker Launcher"
Write-Host "  Project: $ProjectRoot"

# Refresh PATH so freshly installed tools (nmap) are available
$machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
$userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$env:PATH    = "$machinePath;$userPath"

# Stop all Docker workers first
Write-Header "Stopping Docker workers"
$dockerWorkers = @("vapt-worker-nmap","vapt-worker-zap","vapt-worker-metasploit","vapt-worker-prowler","vapt-worker-trivy")
foreach ($w in $dockerWorkers) {
    $running = docker ps --filter "name=$w" --format "{{.Names}}" 2>$null
    if ($running) {
        docker stop $running 2>&1 | Out-Null
        Write-Ok "Stopped: $w"
    } else {
        Write-Step "Already stopped: $w"
    }
}

# Kill any existing native worker processes to prevent duplicates
Write-Header "Stopping existing native workers"
$workerQueues = @("nmap", "trivy", "prowler", "zap", "metasploit")
foreach ($q in $workerQueues) {
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*celery*" -and $_.CommandLine -like "*-Q $q*"
    }
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Step "Killed existing $q worker PID=$($p.ProcessId)"
    }
    if (-not $procs) { Write-Step "No existing $q worker running" }
}

# Check infra connectivity
Write-Header "Checking Docker infra on localhost"
$checks = @(
    @{name="RabbitMQ";   port=5672},
    @{name="Redis";      port=6379},
    @{name="PostgreSQL"; port=5433}
)
$infraOk = $true
foreach ($c in $checks) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("localhost", $c.port)
        $tcp.Close()
        Write-Ok "$($c.name) OK on :$($c.port)"
    } catch {
        Write-Err "$($c.name) NOT reachable on localhost:$($c.port) -- is Docker running?"
        $infraOk = $false
    }
}
if (-not $infraOk) {
    Write-Err "Cannot start workers -- fix Docker infra first"
    exit 1
}

# Setup venv helper
function Setup-WorkerVenv {
    param([string]$Name, [string]$Dir)
    $venv       = Join-Path $Dir ".venv"
    $pip        = Join-Path $venv "Scripts\pip.exe"
    $baseReqs   = Join-Path $WorkersDir "base\requirements.txt"
    $workerReqs = Join-Path $Dir "requirements.txt"

    Write-Step "Setting up $Name venv..."
    if (-not (Test-Path $venv)) {
        $null = python -m venv $venv 2>&1
    }
    # Upgrade pip silently, ignore stderr warnings
    $null = & $pip install --upgrade pip 2>&1
    if (Test-Path $baseReqs) {
        $out = & $pip install -q -r $baseReqs 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Warn "Base deps warning for $Name" }
    }
    if (Test-Path $workerReqs) {
        $out = & $pip install -q -r $workerReqs 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Warn "Worker deps warning for $Name" }
    }
    Write-Ok "$Name venv ready"
    return (Join-Path $venv "Scripts\python.exe")
}

# Start celery worker helper
function Start-CeleryWorker {
    param([string]$Name, [string]$Dir, [string]$Queue, [string]$Concurrency="2", [string]$Python)
    $logsDir = Join-Path $WorkersDir "logs"
    if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
    $logOut = Join-Path $logsDir "$Name.log"
    $logErr = Join-Path $logsDir "$Name-err.log"

    $basePath = Join-Path $WorkersDir "base"
    $env:PYTHONPATH = "$Dir;$basePath"

    # Use --pool=solo on Windows: prefork/billiard multiprocessing causes PermissionError (WinError 5)
    $argList = @("-m", "celery", "-A", "app.tasks", "worker", "--loglevel=info", "--pool=solo", "--concurrency=1", "-Q", $Queue)
    $proc = Start-Process -FilePath $Python -ArgumentList $argList `
        -WorkingDirectory $Dir -PassThru `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr

    Write-Ok "$Name worker started PID=$($proc.Id)  queue=$Queue"
    return $proc.Id
}

$pids = @{}

# ---- nmap Worker ----
Write-Header "nmap Worker (real LAN scanning)"
$nmapBin = Get-Command nmap -ErrorAction SilentlyContinue
if ($nmapBin) {
    Write-Ok "nmap found: $($nmapBin.Source)"
} else {
    $nmapFallback = "C:\Program Files (x86)\Nmap\nmap.exe"
    if (Test-Path $nmapFallback) {
        $env:PATH += ";C:\Program Files (x86)\Nmap"
        Write-Ok "nmap found at default install path (added to PATH)"
    } else {
        Write-Warn "nmap not in PATH -- worker will use python socket fallback"
    }
}
$nmapDir = Join-Path $WorkersDir "nmap"
$py = Setup-WorkerVenv -Name "nmap" -Dir $nmapDir
$pids["nmap"] = Start-CeleryWorker -Name "nmap" -Dir $nmapDir -Queue "nmap" -Concurrency "4" -Python $py

# ---- Trivy Worker ----
if (-not $SkipTrivy -and -not $NmapOnly) {
    Write-Header "Trivy Worker (container/image scanning)"
    $trivyDir = Join-Path $WorkersDir "trivy"
    $py = Setup-WorkerVenv -Name "trivy" -Dir $trivyDir
    $pids["trivy"] = Start-CeleryWorker -Name "trivy" -Dir $trivyDir -Queue "trivy" -Concurrency "2" -Python $py
}

# ---- Prowler Worker ----
if (-not $SkipProwler -and -not $NmapOnly) {
    Write-Header "Prowler Worker (cloud scanning)"
    $prowlerDir = Join-Path $WorkersDir "prowler"
    $py = Setup-WorkerVenv -Name "prowler" -Dir $prowlerDir
    $pids["prowler"] = Start-CeleryWorker -Name "prowler" -Dir $prowlerDir -Queue "prowler" -Concurrency "1" -Python $py
}

# ---- ZAP Worker ----
if (-not $NmapOnly -and -not $SkipZap) {
    Write-Header "ZAP Worker (web app scanning)"
    $zapPaths = @(
        "C:\Program Files\OWASP\Zed Attack Proxy\zap.bat",
        "C:\Program Files (x86)\OWASP\Zed Attack Proxy\zap.bat",
        "$env:LOCALAPPDATA\ZAP\zap.bat"
    )
    $zapExe = $zapPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($zapExe) {
        Write-Ok "ZAP found: $zapExe"
        $zapDir = Join-Path $WorkersDir "zap"
        $py = Setup-WorkerVenv -Name "zap" -Dir $zapDir
        $pids["zap"] = Start-CeleryWorker -Name "zap" -Dir $zapDir -Queue "zap" -Concurrency "2" -Python $py
    } else {
        Write-Warn "OWASP ZAP not installed -- skipping"
        Write-Warn "Install from: https://www.zaproxy.org/download/"
    }
}

# ---- Metasploit Worker ----
if (-not $NmapOnly -and -not $SkipMsf) {
    Write-Header "Metasploit Worker"
    $msfReady = $false
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("localhost", 55553)
        $tcp.Close()
        $msfReady = $true
        Write-Ok "Metasploit RPC reachable on :55553"
    } catch {
        $wsl = Get-Command wsl -ErrorAction SilentlyContinue
        if ($wsl) {
            Write-Step "Trying to start Metasploit via WSL2..."
            Start-Process "wsl" -ArgumentList @("-e","bash","-c","nohup msfrpcd -P msf -S false -a 0.0.0.0 -p 55553 > /tmp/msfrpc.log 2>&1 &") | Out-Null
            Start-Sleep -Seconds 5
            $msfReady = $true
        } else {
            Write-Warn "Metasploit not available -- skipping"
        }
    }
    if ($msfReady) {
        $msfDir = Join-Path $WorkersDir "metasploit"
        $py = Setup-WorkerVenv -Name "metasploit" -Dir $msfDir
        $pids["metasploit"] = Start-CeleryWorker -Name "metasploit" -Dir $msfDir -Queue "metasploit" -Concurrency "1" -Python $py
    }
}

# Save PIDs
$pids | ConvertTo-Json | Set-Content $PidFile

Write-Header "All native workers running"
$pids.Keys | ForEach-Object { Write-Host "  [OK] $_ (PID $($pids[$_]))" -ForegroundColor Green }
Write-Host ""
Write-Host "  Logs : $WorkersDir\logs\" -ForegroundColor Cyan
Write-Host "  Stop : .\stop-native.ps1" -ForegroundColor Cyan
Write-Host ""