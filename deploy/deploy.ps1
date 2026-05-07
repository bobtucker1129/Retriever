# deploy.ps1 -- server-pull deploy for RetrieverRebuild on Windows Server
#
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 main
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 965a75c
#
# Set $env:RETRIEVER_RUN_MIGRATIONS = "true" to run DB migrations on this deploy.

param(
    [Parameter(Mandatory=$true)]
    [string]$GitRef
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
$AppBase     = "D:\retriever-rebuild"
$AppReleases = "$AppBase\releases"
$AppBin      = "$AppBase\bin"
$EnvFile     = "$AppBase\env\retriever.env"
$LogDir      = "$AppBase\logs"
$DeployLog   = "$LogDir\deploy.log"
$LockFile    = "$AppBase\deploy.lock"
$ServiceName = "RetrieverRebuild"
$GithubUrl   = "https://github.com/bobtucker1129/Retriever.git"
$AppRepo     = "$AppBase\repo"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
    $line = "[$ts] $Message"
    Write-Host $line
    $line | Out-File -FilePath $DeployLog -Append -Encoding utf8
}

function Write-DeployRecord {
    param([string]$Status, [string]$Sha = "unknown", [string]$Prev = "unknown")
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
    @"
---
deployedAt: $ts
operator: $env:USERNAME
gitRef: $GitRef
gitSha: $Sha
previousSha: $Prev
host: $env:COMPUTERNAME
service: $ServiceName
status: $Status
"@ | Out-File -FilePath $DeployLog -Append -Encoding utf8
}

function Invoke-Git {
    param([string[]]$Args)
    & git @Args
    if ($LASTEXITCODE -ne 0) { throw "git $($Args -join ' ') failed (exit $LASTEXITCODE)" }
}

function Set-Junction {
    param([string]$Link, [string]$Target)
    if (Test-Path $Link) {
        # Remove existing junction or directory
        Remove-Item $Link -Force -Recurse -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null
}

# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------
if (Test-Path $LockFile) {
    $lockAge = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 30) {
        Write-Log "ERROR: Deploy lock exists ($LockFile). Another deploy may be running."
        exit 1
    }
    Write-Log "Stale lock found (age: $([int]$lockAge.TotalMinutes)m). Removing."
    Remove-Item $LockFile -Force
}
"$env:USERNAME $(Get-Date -Format 'o')" | Out-File $LockFile -Encoding utf8

try {

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
Write-Log "=== Deploy starting: ref=$GitRef ==="

foreach ($dir in @($AppBase, $AppReleases)) {
    if (-not (Test-Path $dir)) { throw "$dir does not exist. Run VM_SETUP_RUNBOOK first." }
}
if (-not (Test-Path $EnvFile)) { throw "Env file not found: $EnvFile" }
if (-not (Test-Path $LogDir))  { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# ---------------------------------------------------------------------------
# Current release for rollback reference
# ---------------------------------------------------------------------------
$prevSha = "none"
$currentLink = "$AppBase\current"
if (Test-Path $currentLink) {
    $prevSha = Split-Path -Leaf (Get-Item $currentLink).Target
    Write-Log "Current release: $prevSha"
}

# ---------------------------------------------------------------------------
# Fetch source
# ---------------------------------------------------------------------------
Write-Log "Fetching from $GithubUrl ..."
if (Test-Path "$AppRepo\.git") {
    Invoke-Git -Args @("-C", $AppRepo, "fetch", "--tags", "origin")
} else {
    Write-Log "Cloning repo to $AppRepo ..."
    Invoke-Git -Args @("clone", $GithubUrl, $AppRepo)
}

# Resolve ref to full SHA
$fullSha = (& git -C $AppRepo rev-parse --verify "$GitRef^{commit}" 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $fullSha) {
    throw "Could not resolve ref '$GitRef' to a commit in $AppRepo"
}
Write-Log "Resolved $GitRef -> $fullSha"

$releaseDir = "$AppReleases\$fullSha"

if (-not (Test-Path $releaseDir)) {
    # ---------------------------------------------------------------------------
    # Checkout into immutable release directory
    # ---------------------------------------------------------------------------
    Write-Log "Creating release directory $releaseDir ..."
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
    Invoke-Git -Args @("-C", $AppRepo, "--work-tree=$releaseDir", "checkout", $fullSha, "--", ".")
    Write-Log "Source checked out."

    # Stamp metadata
    @"
gitSha=$fullSha
gitRef=$GitRef
builtAt=$(Get-Date -Format 'o')
operator=$env:USERNAME
"@ | Out-File "$releaseDir\.release-meta" -Encoding utf8

    # ---------------------------------------------------------------------------
    # Create venv and install dependencies
    # ---------------------------------------------------------------------------
    Write-Log "Creating Python virtual environment ..."
    $pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue)?.Source
    if (-not $pythonExe) {
        # Fall back to old Retriever's venv Python (same server, same Python install)
        $pythonExe = "D:\Repository\pm-review-dashboard-ContexEng\venv\Scripts\python.exe"
    }
    if (-not (Test-Path $pythonExe)) { throw "python.exe not found. Install Python 3.10+ first." }

    & $pythonExe -m venv "$releaseDir\.venv"
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }

    $venvPython = "$releaseDir\.venv\Scripts\python.exe"
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r "$releaseDir\requirements.txt"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
    Write-Log "Dependencies installed."

    # ---------------------------------------------------------------------------
    # Import check
    # ---------------------------------------------------------------------------
    Write-Log "Running import check ..."
    Set-Location $releaseDir
    $env:PYTHONPATH = $releaseDir
    & $venvPython -c "from app.main import app"
    if ($LASTEXITCODE -ne 0) { throw "Import check failed. Release is broken." }
    Write-Log "Import check passed."

    # ---------------------------------------------------------------------------
    # Tests
    # ---------------------------------------------------------------------------
    Write-Log "Running test suite ..."
    & $venvPython -m pytest tests/ -q --tb=short
    if ($LASTEXITCODE -ne 0) { throw "Tests failed. Aborting deploy." }
    Write-Log "Tests passed."
} else {
    Write-Log "Release $releaseDir already exists. Skipping build."
    $venvPython = "$releaseDir\.venv\Scripts\python.exe"
}

# ---------------------------------------------------------------------------
# Config validation (no secret printing)
# ---------------------------------------------------------------------------
Write-Log "Validating production config ..."
Set-Location $releaseDir
$env:PYTHONPATH = $releaseDir

# Load env into process for validation
Get-Content $EnvFile |
    Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } |
    ForEach-Object {
        $k, $v = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
    }

& $venvPython -c @"
from app.config import get_settings, format_config_error
from pydantic import ValidationError
try:
    s = get_settings()
    print('Config OK: env=' + str(s.retriever_env))
except (ValidationError, ValueError) as e:
    print('Config ERROR: ' + format_config_error(e))
    raise SystemExit(1)
"@
if ($LASTEXITCODE -ne 0) { throw "Config validation failed. Fix $EnvFile before deploying." }
Write-Log "Config validation passed."

# ---------------------------------------------------------------------------
# Migrations (only when explicitly opted in)
# ---------------------------------------------------------------------------
if ($env:RETRIEVER_RUN_MIGRATIONS -eq "true") {
    Write-Log "Running database migrations (RETRIEVER_RUN_MIGRATIONS=true) ..."
    & $venvPython -c @"
from app.db.connection import get_db_connection
from app.db.migrations import run_migrations_and_seeds
import asyncio
async def main():
    conn = await get_db_connection()
    await run_migrations_and_seeds(conn)
    await conn.close()
asyncio.run(main())
"@
    if ($LASTEXITCODE -ne 0) { throw "Migrations failed." }
    Write-Log "Migrations complete."
} else {
    Write-Log "Skipping migrations (set RETRIEVER_RUN_MIGRATIONS=true to run on next deploy)."
}

# ---------------------------------------------------------------------------
# Swap junctions
# ---------------------------------------------------------------------------
Write-Log "Swapping release junctions ..."
$previousLink = "$AppBase\previous"
if (Test-Path $currentLink) {
    $currentTarget = (Get-Item $currentLink).Target
    Set-Junction -Link $previousLink -Target $currentTarget
    Write-Log "previous -> $currentTarget"
}
Set-Junction -Link $currentLink -Target $releaseDir
Write-Log "current -> $releaseDir"

# Stamp deployed_at
"deployedAt=$(Get-Date -Format 'o')" | Out-File "$releaseDir\.release-meta" -Append -Encoding utf8

# ---------------------------------------------------------------------------
# Restart service
# ---------------------------------------------------------------------------
Write-Log "Restarting $ServiceName ..."
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    Restart-Service -Name $ServiceName -Force
    Start-Sleep -Seconds 4
    $svc.Refresh()
    if ($svc.Status -ne 'Running') {
        Write-DeployRecord -Status "service-not-running" -Sha $fullSha -Prev $prevSha
        throw "Service is not running after restart."
    }
    Write-Log "Service restarted and running."
} else {
    Write-Log "Service '$ServiceName' not installed yet. Run deploy\windows\install-service.ps1 first."
    Write-Log "Skipping restart — release is staged at $releaseDir"
}

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
Write-Log "Running health check ..."
& "$AppBin\healthcheck.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-DeployRecord -Status "healthcheck-failed" -Sha $fullSha -Prev $prevSha
    Write-Log "Health check failed. Attempting auto-rollback ..."
    & "$AppBin\rollback.ps1" -Reason "auto-rollback: healthcheck failed on $fullSha"
    throw "Deployment failed. Auto-rollback attempted. Check $DeployLog"
}

# ---------------------------------------------------------------------------
# Smoke check
# ---------------------------------------------------------------------------
Write-Log "Running smoke check ..."
& "$AppBin\smoke.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-DeployRecord -Status "smoke-failed" -Sha $fullSha -Prev $prevSha
    Write-Log "Smoke check failed. Attempting auto-rollback ..."
    & "$AppBin\rollback.ps1" -Reason "auto-rollback: smoke failed on $fullSha"
    throw "Deployment failed. Auto-rollback attempted. Check $DeployLog"
}

# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------
Write-DeployRecord -Status "success" -Sha $fullSha -Prev $prevSha
Write-Log "=== Deploy complete: $fullSha ==="

} finally {
    # Always release the lock
    if (Test-Path $LockFile) { Remove-Item $LockFile -Force }
}
