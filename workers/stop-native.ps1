# ============================================================================
# VAPT Platform - Stop Native Workers
# ============================================================================
# Stops all native Celery workers (nmap, zap, metasploit) started by
# start-native.ps1 by reading the saved PID file.
#
# Usage:  .\stop-native.ps1
# ============================================================================

$ErrorActionPreference = "SilentlyContinue"
$WorkersDir = $PSScriptRoot
$PidFile = Join-Path $WorkersDir ".native-worker-pids.json"

function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [XX] $msg" -ForegroundColor Red }

Write-Host "`n=== Stopping VAPT Native Workers ===" -ForegroundColor Magenta

if (-not (Test-Path $PidFile)) {
    Write-Warn "No PID file found at $PidFile"
    Write-Warn "Attempting to kill all Celery worker processes..."
    
    # Fallback: kill any Python processes running celery in the workers dir
    Get-Process python, python3 -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Stop-Process -Id $_.Id -Force
            Write-Ok "Killed python process PID $($_.Id)"
        } catch {}
    }
} else {
    $pids = Get-Content $PidFile | ConvertFrom-Json
    $pids.PSObject.Properties | ForEach-Object {
        $name = $_.Name
        $pid  = $_.Value
        try {
            $proc = Get-Process -Id $pid -ErrorAction Stop
            Stop-Process -Id $pid -Force
            Write-Ok "Stopped $name worker (PID $pid)"
        } catch {
            Write-Warn "$name (PID $pid) was not running"
        }
    }
    Remove-Item $PidFile -Force
    Write-Ok "PID file removed"
}

Write-Host "`n  All native workers stopped.`n" -ForegroundColor Cyan
