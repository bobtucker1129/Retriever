# deploy.ps1 -- server-pull deploy for RetrieverRebuild on Windows Server
#
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 main
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 965a75c
#
# Set $env:RETRIEVER_RUN_MIGRATIONS = "true" to run DB migrations on this deploy.
# Set $env:RETRIEVER_ASSERT_MIGRATION_0002 = "true" to require MySQL to already
#   have migration 0002_fetch_conversations applied (read-only check; fails before swap).
#
# GUARDRAILS (do not regress):
# - Restarts and manages ONLY the RetrieverRebuild service on port 8810.
# - Never stops or reconfigures legacy service "Retriever" on port 8000.

param(
    [Parameter(Mandatory=$true)]
    [string]$GitRef
)

# Use 'Continue', not 'Stop': in PowerShell 5.1, 'Stop' treats any native
# command stderr output as a terminating error (e.g. git's "Cloning into..."
# message). All real errors below are handled with explicit if/throw blocks.
$ErrorActionPreference = "Continue"

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
# Explicit legacy names: this script must never call Restart-Service on these.
$LegacyRetrieverServiceName = "Retriever"
$LegacyRetrieverPort        = 8000
$RetrieverRebuildPort       = 8810
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
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') failed (exit $LASTEXITCODE)" }
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
        # Capture stdout AND stderr so we can log what Python actually said
        $output = & $PythonExe $tmpFile 2>&1 | Out-String
        $code = $LASTEXITCODE
        Pop-Location
        if ($output.Trim()) {
            foreach ($line in ($output -split "`r?`n")) {
                if ($line.Trim()) { Write-Log "py: $line" }
            }
        }
        return $code
    } finally {
        Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
    }
}

function Assert-NonLegacyServiceName {
    param([string]$Name)
    if ($Name -eq $LegacyRetrieverServiceName) {
        throw "Refusing to operate on legacy service '$LegacyRetrieverServiceName'. Use '$ServiceName' (RetrieverRebuild) on port $RetrieverRebuildPort only."
    }
}

function Clear-StaleEnvVars {
    # Old Retriever sets system-level FETCH_*, MODEL_*, ANTHROPIC_*, BOONEOPS_*,
    # PRINTSMITH_* env vars that pollute new Retriever's pydantic-settings.
    # Clear them at process scope so they don't shadow values from retriever.env.
    # System/user-level settings are not modified.
    $prefixPatterns = '^FETCH_|^MODEL_|^ANTHROPIC_|^BOONEOPS_|^PRINTSMITH_'
    $cleared = @()
    Get-ChildItem Env: | Where-Object { $_.Name -match $prefixPatterns } | ForEach-Object {
        [System.Environment]::SetEnvironmentVariable($_.Name, $null, 'Process')
        $cleared += $_.Name
    }
    if ($cleared.Count -gt 0) {
        Write-Log "Cleared $($cleared.Count) inherited env vars: $($cleared -join ', ')"
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

Assert-NonLegacyServiceName -Name $ServiceName

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
Write-Log "=== Deploy starting: ref=$GitRef ==="
Write-Log "Target service: $ServiceName (port $RetrieverRebuildPort). Legacy $LegacyRetrieverServiceName on port $LegacyRetrieverPort is not modified by this script."

foreach ($dir in @($AppBase, $AppReleases)) {
    if (-not (Test-Path $dir)) { throw "$dir does not exist. Run VM_SETUP_RUNBOOK first." }
}
if (-not (Test-Path $EnvFile)) { throw "Env file not found: $EnvFile" }
if (-not (Test-Path $LogDir))  { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# ---------------------------------------------------------------------------
# Clean inherited env, then load production env from retriever.env
# This must happen BEFORE any Python invocation (import check, tests,
# config validation, migrations) so all of them see the same env state.
# ---------------------------------------------------------------------------
Clear-StaleEnvVars

Write-Log "Loading env from $EnvFile ..."
Get-Content $EnvFile |
    Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } |
    ForEach-Object {
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
        }
    }

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
    Invoke-Git -GitArgs @("-C", $AppRepo, "fetch", "--tags", "origin")
} else {
    Write-Log "Cloning repo to $AppRepo ..."
    Invoke-Git -GitArgs @("clone", $GithubUrl, $AppRepo)
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
    # Populate release dir via clone-and-strip-git.
    # Avoids GIT_DIR/GIT_WORK_TREE + pathspec quirks on Windows PowerShell.
    # ---------------------------------------------------------------------------
    Write-Log "Cloning $AppRepo to $releaseDir ..."
    $cloneOutput = & git clone $AppRepo $releaseDir 2>&1 | Out-String
    $cloneExit = $LASTEXITCODE
    if ($cloneOutput.Trim()) { Write-Log "git clone: $($cloneOutput.Trim())" }
    if ($cloneExit -ne 0) { throw "git clone failed (exit $cloneExit)." }

    Write-Log "Checking out $fullSha ..."
    $coOutput = & git -C $releaseDir checkout -f $fullSha 2>&1 | Out-String
    $coExit = $LASTEXITCODE
    if ($coOutput.Trim()) { Write-Log "git checkout: $($coOutput.Trim())" }
    if ($coExit -ne 0) { throw "git checkout failed (exit $coExit)." }

    # Strip .git so the release is an immutable source snapshot
    Remove-Item -Recurse -Force "$releaseDir\.git" -ErrorAction SilentlyContinue

    # Diagnostic: list what's actually in the release dir
    $releasedItems = Get-ChildItem -Path $releaseDir -Force -ErrorAction SilentlyContinue
    Write-Log "Release dir contains $($releasedItems.Count) entries"
    if ($releasedItems.Count -gt 0) {
        Write-Log "Top-level entries: $($releasedItems.Name -join ', ')"
    }

    # Verify required subdirectories made it
    foreach ($must in @('pyproject.toml', 'app\main.py', 'app\static', 'app\templates')) {
        if (-not (Test-Path "$releaseDir\$must")) {
            throw "Source extraction did not produce $must at $releaseDir."
        }
    }
    Write-Log "Source extracted to release directory."

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

    # Install the app and dev dependencies from pyproject.toml.
    # pip must run from the release dir so it can find pyproject.toml.
    Push-Location $releaseDir
    try {
        & $venvPython -m pip install --quiet ".[dev]"
        $pipExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($pipExit -ne 0) { throw "pip install failed (exit $pipExit)." }
    Write-Log "Dependencies installed."

    # ---------------------------------------------------------------------------
    # Import check
    # ---------------------------------------------------------------------------
    Write-Log "Running import check ..."
    $env:PYTHONPATH = $releaseDir
    Push-Location $releaseDir
    try {
        # Python imports use relative paths (e.g. "app/static") that resolve
        # against cwd, so cwd must be the release dir.
        & $venvPython -c "from app.main import app"
        $importExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($importExit -ne 0) { throw "Import check failed. Release is broken." }
    Write-Log "Import check passed."

    # ---------------------------------------------------------------------------
    # NOTE: Tests are NOT run during deploy. They are designed to run with
    # local mode env (RETRIEVER_ENV=local, no real MySQL), not against
    # production config loaded by this script. Run pytest on your dev machine
    # before pushing. Deploy validates: imports work, config is valid,
    # health checks pass after restart, smoke checks pass through Cloudflare.
    # ---------------------------------------------------------------------------

} else {
    Write-Log "Release $releaseDir already exists. Skipping build."
    $venvPython = "$releaseDir\.venv\Scripts\python.exe"
}

# ---------------------------------------------------------------------------
# Config validation (env was loaded earlier, before build steps)
# ---------------------------------------------------------------------------
Write-Log "Validating production config ..."

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
# Migrations + 0002 verification (Fetch conversation tables)
# ---------------------------------------------------------------------------
$migrationVerifyScript = @'
from __future__ import annotations

from app.config import get_settings
from app.db.connection import create_connection

REQUIRED_VERSION = "0002_fetch_conversations"


def main() -> None:
    settings = get_settings()
    if not settings.mysql_host or not settings.mysql_user:
        print("migration-verify: skip (MySQL not configured)")
        return
    conn = create_connection(settings)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = %s",
            (REQUIRED_VERSION,),
        )
        row = cur.fetchone()
        if not row or row[0] < 1:
            raise SystemExit(f"migration-verify: missing {REQUIRED_VERSION} in schema_migrations")
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name IN ('fetch_conversations', 'fetch_messages')
            """,
            (settings.mysql_database,),
        )
        n = cur.fetchone()[0]
        if n != 2:
            raise SystemExit(
                "migration-verify: fetch_conversations / fetch_messages not found in "
                + repr(settings.mysql_database)
            )
    finally:
        conn.close()
    print("migration-verify: OK (0002 + conversation tables)")


if __name__ == "__main__":
    main()
'@

if ($env:RETRIEVER_RUN_MIGRATIONS -eq "true") {
    Write-Log "Running database migrations (including seeds) ..."
    $migScript = @'
from app.db.migrations import run_migrations

for name, count in run_migrations(include_seeds=True):
    print(f"applied {name}: {count} statements")
'@
    $migResult = Run-PythonScript -PythonExe $venvPython -Script $migScript -WorkDir $releaseDir
    if ($migResult -ne 0) { throw "Migrations failed." }
    Write-Log "Migrations complete. Verifying 0002 Fetch conversation migration ..."
    $verifyMig = Run-PythonScript -PythonExe $venvPython -Script $migrationVerifyScript -WorkDir $releaseDir
    if ($verifyMig -ne 0) { throw "Post-migration verification failed (expect 0002_fetch_conversations + tables)." }
    Write-Log "Migration verification passed."
} else {
    Write-Log "Skipping migrations (set RETRIEVER_RUN_MIGRATIONS=true to run on next deploy)."
}

if ($env:RETRIEVER_ASSERT_MIGRATION_0002 -eq "true") {
    Write-Log "RETRIEVER_ASSERT_MIGRATION_0002: verifying 0002 is present before junction swap ..."
    $assertMig = Run-PythonScript -PythonExe $venvPython -Script $migrationVerifyScript -WorkDir $releaseDir
    if ($assertMig -ne 0) {
        throw "Database missing 0002_fetch_conversations. Run deploy with RETRIEVER_RUN_MIGRATIONS=true or apply migrations, then retry."
    }
    Write-Log "Assert migration 0002: OK."
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
# Restart service (RetrieverRebuild only; never legacy Retriever)
# ---------------------------------------------------------------------------
Assert-NonLegacyServiceName -Name $ServiceName
Write-Log "Restarting $ServiceName (localhost:$RetrieverRebuildPort) ..."
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
