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
    $record = @"
---
deployedAt: $ts
operator: $env:USERNAME
gitRef: $GitRef
gitSha: $Sha
previousSha: $Prev
host: $env:COMPUTERNAME
service: $ServiceName
status: $Status
"@
    $record | Out-File -FilePath $DeployLog -Append -Encoding utf8
}

function Invoke-Git {
    param([string[]]$Args)
    & git @Args
    if ($LASTEXITCODE -ne 0) { throw "git $($Args -join ' ') failed (exit $LASTEXITCODE)" }
}

function Set-Junction {
    param([string]$Link, [string]$Target)
    if (Test-Path $Link) {
        Remove-Item $Link -Force -Recurse -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null
}

function Run-PythonScript {
    param([string]$PythonExe, [string]$Script, [string]$WorkDir)
    $tmpFile = [System.IO.Path]::GetTempFileName() -replace '\.tmp$', '.py'
    $Script | Out-File -FilePath $tmpFile -Encoding utf8
    try {
        Push-Location $WorkDir
        & $PythonExe $tmpFile
        $code = $LASTEXITCODE
        Pop-Location
        return $code
    } finally {
        Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
    }
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

# Resolve ref to full SHA (PS 5.1 compatible)
$fullSha = ""
$gitOutput = & git -C $AppRepo rev-parse --verify "$GitRef^{commit}" 2>$null
if ($LASTEXITCODE -eq 0 -and $gitOutput) {
    $fullSha = $gitOutput.Trim()
}
if (-not $fullSha) { throw "Could not resolve ref '$GitRef' to a commit in $AppRepo" }
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
    $meta = "gitSha=$fullSha`ngitRef=$GitRef`nbuiltAt=$(Get-Date -Format 'o')`noperator=$env:USERNAME"
    $meta | Out-File "$releaseDir\.release-meta" -Encoding utf8

    # ---------------------------------------------------------------------------
    # Find Python (PS 5.1 compatible - no ?. operator)
    # ---------------------------------------------------------------------------
    Write-Log "Locating Python ..."
    $pythonExe = $null
    $pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $pythonExe = $pythonCmd.Source
    }
    if (-not $pythonExe -or -not (Test-Path $pythonExe)) {
        $pythonExe = "D:\Repository\pm-review-dashboard-ContexEng\venv\Scripts\python.exe"
    }
    if (-not (Test-Path $pythonExe)) { throw "python.exe not found." }
    Write-Log "Python: $pythonExe"

    # ---------------------------------------------------------------------------
    # Create venv and install dependencies
    # ---------------------------------------------------------------------------
    Write-Log "Creating virtual environment ..."
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
    $env:PYTHONPATH = $releaseDir
    & $venvPython -c "from app.main import app"
    if ($LASTEXITCODE -ne 0) { throw "Import check failed. Release is broken." }
    Write-Log "Import check passed."

    # ---------------------------------------------------------------------------
    # Tests
    # ---------------------------------------------------------------------------
    Write-Log "Running test suite ..."
    Push-Location $releaseDir
    & $venvPython -m pytest tests/ -q --tb=short
    $testResult = $LASTEXITCODE
    Pop-Location
    if ($testResult -ne 0) { throw "Tests failed. Aborting deploy." }
    Write-Log "Tests passed."

} else {
    Write-Log "Release $releaseDir already exists. Skipping build."
    $venvPython = "$releaseDir\.venv\Scripts\python.exe"
}

# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------
Write-Log "Validating production config ..."

# Load env file into process environment
Get-Content $EnvFile |
    Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } |
    ForEach-Object {
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
        }
    }

$configScript = @'
from app.config import get_settings, format_config_error
from pydantic import ValidationError
try:
    s = get_settings()
    print('Config OK: env=' + str(s.retriever_env))
except (ValidationError, ValueError) as e:
    print('Config ERROR: ' + format_config_error(e))
    raise SystemExit(1)
'@
$configResult = Run-PythonScript -PythonExe $venvPython -Script $configScript -WorkDir $releaseDir
if ($configResult -ne 0) { throw "Config validation failed. Fix $EnvFile before deploying." }
Write-Log "Config validation passed."

# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
if ($env:RETRIEVER_RUN_MIGRATIONS -eq "true") {
    Write-Log "Running database migrations ..."
    $migScript = @'
from app.db.connection import get_db_connection
from app.db.migrations import run_migrations_and_seeds
import asyncio
async def main():
    conn = await get_db_connection()
    await run_migrations_and_seeds(conn)
    await conn.close()
asyncio.run(main())
'@
    $migResult = Run-PythonScript -PythonExe $venvPython -Script $migScript -WorkDir $releaseDir
    if ($migResult -ne 0) { throw "Migrations failed." }
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
    Write-Log "Service '$ServiceName' not installed yet. Run install-service.ps1 first."
    Write-Log "Release staged at $releaseDir - install the service then run deploy again."
}

# ---------------------------------------------------------------------------
# Health and smoke checks (only if service is running)
# ---------------------------------------------------------------------------
$svcCheck = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svcCheck -and $svcCheck.Status -eq 'Running') {
    Write-Log "Running health check ..."
    & "$AppBin\healthcheck.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-DeployRecord -Status "healthcheck-failed" -Sha $fullSha -Prev $prevSha
        Write-Log "Health check failed. Attempting auto-rollback ..."
        & "$AppBin\rollback.ps1" -Reason "auto-rollback: healthcheck failed on $fullSha"
        throw "Deployment failed. Auto-rollback attempted. Check $DeployLog"
    }

    Write-Log "Running smoke check ..."
    & "$AppBin\smoke.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-DeployRecord -Status "smoke-failed" -Sha $fullSha -Prev $prevSha
        Write-Log "Smoke check failed. Attempting auto-rollback ..."
        & "$AppBin\rollback.ps1" -Reason "auto-rollback: smoke failed on $fullSha"
        throw "Deployment failed. Auto-rollback attempted. Check $DeployLog"
    }
}

# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------
Write-DeployRecord -Status "success" -Sha $fullSha -Prev $prevSha
Write-Log "=== Deploy complete: $fullSha ==="

} finally {
    if (Test-Path $LockFile) { Remove-Item $LockFile -Force }
}
