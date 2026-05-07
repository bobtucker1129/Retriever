# run-service.ps1 -- NSSM launcher for RetrieverRebuild
#
# NSSM calls this script to start the app. Do not call directly.
# Mirrors the pattern from old Retriever's run_retriever_service.ps1.
#
# Service name: RetrieverRebuild
# Port: 8810 (localhost only, behind Cloudflare Tunnel)

param(
    [string]$AppBase    = "D:\retriever-rebuild",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port          = 8810
)

$ErrorActionPreference = "Stop"

$AppCurrent = Join-Path $AppBase "current"
$LogDir     = Join-Path $AppBase "logs"
$EnvFile    = Join-Path $AppBase "env\retriever.env"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$bootstrapLog = Join-Path $LogDir "service-bootstrap.log"
function Write-Boot {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
    "$ts $Message" | Out-File -FilePath $bootstrapLog -Append -Encoding utf8
}

Write-Boot "RetrieverRebuild bootstrap starting."

# ---------------------------------------------------------------------------
# Load production env file into process environment
# ---------------------------------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    Write-Boot "ERROR: env file not found at $EnvFile"
    throw "Env file not found: $EnvFile"
}

Write-Boot "Loading env from $EnvFile"
Get-Content $EnvFile |
    Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } |
    ForEach-Object {
        $key, $value = $_ -split '=', 2
        $key   = $key.Trim()
        $value = $value.Trim()
        if ($key) {
            [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }

# ---------------------------------------------------------------------------
# Verify current release exists
# ---------------------------------------------------------------------------
if (-not (Test-Path $AppCurrent)) {
    Write-Boot "ERROR: current release not found at $AppCurrent"
    throw "Current release not found: $AppCurrent"
}

Set-Location -Path $AppCurrent

$pythonExe = Join-Path $AppCurrent ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Boot "ERROR: Python not found at $pythonExe"
    throw "Python executable not found: $pythonExe"
}

Write-Boot "Python: $pythonExe"
Write-Boot "Starting Uvicorn host=$HostAddress port=$Port"

$env:PYTHONUNBUFFERED = "1"

& $pythonExe -m uvicorn app.main:app `
    --host $HostAddress `
    --port $Port `
    --log-level info

$exitCode = $LASTEXITCODE
Write-Boot "Uvicorn exited with code $exitCode."
exit $exitCode
