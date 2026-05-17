# deploy.ps1 -- server-pull deploy for RetrieverRebuild on Windows Server
#
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 main
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 965a75c
#
# Optional pilot: add RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true to retriever.env while
# FETCH_ENABLED=true so healthcheck.ps1 + smoke.ps1 expect checks.fetch/modelProvider ok
# (see deploy/WINDOWS_FETCH_RELEASE.md).
#
# Set $env:RETRIEVER_RUN_MIGRATIONS = "true" to run DB migrations on this deploy.
# Set $env:RETRIEVER_ASSERT_MIGRATION_0002 = "true" to require MySQL to already
#   have migration 0002_fetch_conversations applied (read-only check; fails before swap).
#
# GUARDRAILS (do not regress):
# - RetrieverRebuild recycle uses controlled Stop-Service / guarded 8810 cleanup /
#   Start-Service with explicit Running confirmation — not blind Restart-Service.
#   Stale listeners: only processes on 8810 whose command line includes the app
#   root (D:\retriever-rebuild) and --port 8810 (or --port=8810), and never if
#   --port 8000 appears — clears orphaned uvicorn after junction swap or failed
#   NSSM stop. Does not touch legacy service or port 8000.
# - After restart: requires GET /version JSON field gitSha to equal the resolved
#   full deploy SHA before health/smoke; mismatch fails deploy and triggers rollback.
# - Auto-rollback calls rollback.ps1 -InvokedByDeploy so deploy.lock does not block.
# - If RetrieverRebuild is not installed after the junction swap, deploy fails (no
#   success without restart + live /version SHA proof).

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
# PowerShell's Out-File -Encoding utf8 writes UTF-8 with BOM, which can prefix
# the first key in .release-meta (e.g. ﻿GIT_SHA) and break env injection.
function Write-Utf8NoBomText {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Path,
        [Parameter(Mandatory=$true)]
        [string]$Text
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

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
    if ($LASTEXITCODE -ne 0) { Write-Error "git $($GitArgs -join ' ') failed (exit $LASTEXITCODE)"; exit 1 }
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
        Write-Error "Refusing to operate on legacy service '$LegacyRetrieverServiceName'. Use '$ServiceName' (RetrieverRebuild) on port $RetrieverRebuildPort only."; exit 1
    }
}

function Get-ListeningPidsOnPort {
    param([int]$Port)
    $pids = New-Object 'System.Collections.Generic.HashSet[int]'
    try {
        $mod = Get-Module -ListAvailable -Name NetTCPIP -ErrorAction SilentlyContinue
        if ($mod) {
            Import-Module NetTCPIP -ErrorAction Stop | Out-Null
            $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
            foreach ($c in $conns) {
                if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
                    [void]$pids.Add([int]$c.OwningProcess)
                }
            }
        }
    } catch {
        # NetTCPIP may be unavailable or deny access; netstat merge below still runs.
    }
    $lines = @(netstat -ano 2>$null)
    foreach ($line in $lines) {
        if ($line -notmatch 'LISTENING') { continue }
        if ($line -notmatch ":$Port\s") { continue }
        $parts = @($line -split '\s+' | Where-Object { $_ -ne '' })
        if ($parts.Length -lt 4) { continue }
        $pidStr = $parts[-1]
        if ($pidStr -match '^\d+$' -and [int]$pidStr -gt 0) {
            [void]$pids.Add([int]$pidStr)
        }
    }
    return @([int[]]@($pids))
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    try {
        $p = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($p) { return [string]$p.CommandLine }
    } catch { }
    return $null
}

function Test-StaleRetrieverRebuild8810CommandLine {
    param(
        [string]$CommandLine,
        [string]$AppRootPath
    )
    if (-not $CommandLine) { return $false }
    if ($CommandLine -notmatch '(?i)--port(\s+|=)8810\b') { return $false }
    if ($CommandLine -match '(?i)--port(\s+|=)8000\b') { return $false }
    $normRoot = $AppRootPath.TrimEnd('\')
    if (-not $normRoot) { return $false }
    if ($CommandLine -notmatch '(?i)' + [regex]::Escape($normRoot)) { return $false }
    return $true
}

function Stop-StaleRetrieverRebuild8810Listeners {
    param([string]$AppRootPath)
    $pids = Get-ListeningPidsOnPort -Port $RetrieverRebuildPort
    if ($pids.Count -eq 0) {
        Write-Log "No process listening on port $RetrieverRebuildPort (guarded cleanup: nothing to do)."
        return
    }
    foreach ($procId in $pids) {
        $cmd = Get-ProcessCommandLine -ProcessId $procId
        if (-not (Test-StaleRetrieverRebuild8810CommandLine -CommandLine $cmd -AppRootPath $AppRootPath)) {
            Write-Log "Port $RetrieverRebuildPort listener PID $procId skipped (guards not met; not killing): $(if ($cmd) { $cmd } else { '<no command line>' })"
            continue
        }
        Write-Log "Stopping stale RetrieverRebuild listener on port $RetrieverRebuildPort (PID $procId) ..."
        Write-Log "  commandLine: $cmd"
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 500
        } catch {
            Write-Log "WARNING: Stop-Process failed for PID ${procId}: $($_.Exception.Message)"
        }
    }
}

function Test-HasStaleRetrieverRebuild8810Listener {
    param([string]$AppRootPath)
    $pids = Get-ListeningPidsOnPort -Port $RetrieverRebuildPort
    foreach ($procId in $pids) {
        $cmd = Get-ProcessCommandLine -ProcessId $procId
        if (Test-StaleRetrieverRebuild8810CommandLine -CommandLine $cmd -AppRootPath $AppRootPath) {
            return $true
        }
    }
    return $false
}

function Wait-ServiceReachStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [ValidateSet('Stopped', 'Running')]
        [string]$DesiredStatus,
        [int]$TimeoutSec = 120
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    # PS 5.1: avoid [Type]::$variable static access; parse enum by name.
    $want = [System.ServiceProcess.ServiceControllerStatus] [Enum]::Parse(
        [System.ServiceProcess.ServiceControllerStatus],
        $DesiredStatus,
        $true)
    while ((Get-Date) -lt $deadline) {
        $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
        if (-not $svc) {
            Start-Sleep -Milliseconds 400
            continue
        }
        try { $svc.Refresh() } catch { }
        if ($svc.Status -eq $want) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Restart-RetrieverRebuildForDeploy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SvcName,
        [Parameter(Mandatory = $true)]
        [string]$AppRootPath
    )
    Assert-NonLegacyServiceName -Name $SvcName

    Write-Log "=== Controlled service recycle: $SvcName (port $RetrieverRebuildPort; no Restart-Service shortcut) ==="

    if (Test-HasStaleRetrieverRebuild8810Listener -AppRootPath $AppRootPath) {
        Write-Log "Pre-stop: guarded stale listener on port $RetrieverRebuildPort; clearing before Stop-Service ..."
        Stop-StaleRetrieverRebuild8810Listeners -AppRootPath $AppRootPath
        Start-Sleep -Seconds 1
    }

    Write-Log "Stop step: Stop-Service -Force -ErrorAction Stop ..."
    try {
        Stop-Service -Name $SvcName -Force -ErrorAction Stop
        Write-Log "Stop-Service returned without throwing."
    } catch {
        Write-Log "Stop-Service threw (will still wait for Stopped / run guarded cleanup): $($_.Exception.Message)"
    }

    Write-Log "Waiting for service to reach Stopped (up to 90s) ..."
    $stoppedOk = Wait-ServiceReachStatus -Name $SvcName -DesiredStatus Stopped -TimeoutSec 90
    $svc = Get-Service -Name $SvcName -ErrorAction SilentlyContinue
    if ($svc) { try { $svc.Refresh() } catch { } }
    $statusAfterWait = if ($svc) { [string]$svc.Status } else { '<missing>' }
    Write-Log "After initial stop wait: status=$statusAfterWait (reachedStopped=$stoppedOk)."

    $staleOnPort = Test-HasStaleRetrieverRebuild8810Listener -AppRootPath $AppRootPath
    $needIntervention = ($svc -and $svc.Status -ne 'Stopped') -or $staleOnPort

    if ($needIntervention) {
        Write-Log "Intervention: service not Stopped and/or guarded listener still on $RetrieverRebuildPort (staleOnPort=$staleOnPort). Running guarded 8810 cleanup ..."
        Stop-StaleRetrieverRebuild8810Listeners -AppRootPath $AppRootPath
        Start-Sleep -Seconds 2
        if ($svc -and $svc.Status -ne 'Stopped') {
            Write-Log "Follow-up Stop-Service -Force after cleanup ..."
            try {
                Stop-Service -Name $SvcName -Force -ErrorAction Stop
                Write-Log "Follow-up Stop-Service returned without throwing."
            } catch {
                Write-Log "Follow-up Stop-Service threw: $($_.Exception.Message)"
            }
        }
        Write-Log "Waiting again for Stopped (up to 60s) ..."
        $stoppedOk = Wait-ServiceReachStatus -Name $SvcName -DesiredStatus Stopped -TimeoutSec 60
        $svc = Get-Service -Name $SvcName -ErrorAction SilentlyContinue
        if ($svc) { try { $svc.Refresh() } catch { } }
        Write-Log "After intervention wait: status=$(if ($svc) { $svc.Status } else { '<missing>' }); reachedStopped=$stoppedOk."
    }

    if (-not $svc -or $svc.Status -ne 'Stopped') {
        Write-Log "ERROR: Service did not reach Stopped (final status: $(if ($svc) { $svc.Status } else { 'missing' }))."
        return $false
    }

    if (Test-HasStaleRetrieverRebuild8810Listener -AppRootPath $AppRootPath) {
        Write-Log "Pre-start: residual guarded listener on $RetrieverRebuildPort; clearing before Start-Service ..."
        Stop-StaleRetrieverRebuild8810Listeners -AppRootPath $AppRootPath
        Start-Sleep -Seconds 1
    }

    Write-Log "Start step: Start-Service -ErrorAction Stop ..."
    try {
        Start-Service -Name $SvcName -ErrorAction Stop
        Write-Log "Start-Service returned without throwing."
    } catch {
        Write-Log "ERROR: Start-Service failed: $($_.Exception.Message)"
        return $false
    }

    Write-Log "Waiting for service to reach Running (up to 120s) ..."
    $runningOk = Wait-ServiceReachStatus -Name $SvcName -DesiredStatus Running -TimeoutSec 120
    $svc = Get-Service -Name $SvcName -ErrorAction SilentlyContinue
    if ($svc) { try { $svc.Refresh() } catch { } }
    if (-not $runningOk -or -not $svc -or $svc.Status -ne 'Running') {
        Write-Log "ERROR: Service did not reach Running (status: $(if ($svc) { $svc.Status } else { 'missing' }))."
        return $false
    }

    Write-Log "=== Controlled service recycle complete: Running ==="
    return $true
}

function Invoke-DeployAutoRollback {
    param([Parameter(Mandatory = $true)] [string]$Reason)
    Write-Log "Auto-rollback: invoking rollback.ps1 -InvokedByDeploy ..."
    try {
        & "$AppBin\rollback.ps1" -InvokedByDeploy -Reason $Reason
    } catch {
        Write-Log "ERROR: rollback.ps1 threw or failed terminating: $($_.Exception.Message)"
        return $false
    }
    if (-not $?) {
        Write-Log "ERROR: rollback.ps1 returned with `$?=$false."
        return $false
    }
    Write-Log "Auto-rollback: rollback.ps1 completed (`$?=$true)."
    return $true
}

function Assert-VersionGitShaMatches {
    param(
        [string]$ExpectedFullSha,
        [string]$BaseUrl = "http://127.0.0.1:8810",
        [int]$MaxWaitSeconds = 45
    )
    if (-not $ExpectedFullSha) {
        Write-Error "Assert-VersionGitShaMatches: ExpectedFullSha is empty."; return $false
    }
    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    $lastBody = ""
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "$BaseUrl/version" -UseBasicParsing -TimeoutSec 8
            $lastBody = $r.Content
            $json = $r.Content | ConvertFrom-Json
            $got = [string]$json.gitSha
            if (-not $got) {
                Write-Log "WAIT /version: gitSha missing in JSON (body length $($lastBody.Length))."
            } else {
                if ([string]::Equals($got, $ExpectedFullSha, [System.StringComparison]::OrdinalIgnoreCase)) {
                    Write-Log "Verified /version.gitSha matches deploy target: $ExpectedFullSha"
                    return $true
                }
                Write-Log "WAIT /version: gitSha mismatch (got '$got', want '$ExpectedFullSha')."
            }
        } catch {
            Write-Log "WAIT /version: request failed (will retry): $($_.Exception.Message)"
        }
        Start-Sleep -Seconds 2
    }
    Write-Log "ERROR: /version.gitSha did not match '$ExpectedFullSha' within ${MaxWaitSeconds}s."
    if ($lastBody) {
        Write-Log "Last /version body (truncated): $($lastBody.Substring(0, [Math]::Min(500, $lastBody.Length)))"
    }
    return $false
}

function Read-ReleaseMetaValue {
    param([string]$MetaPath, [string]$Key)
    if (-not (Test-Path -LiteralPath $MetaPath)) { return $null }
    foreach ($raw in Get-Content -LiteralPath $MetaPath) {
        $line = $raw.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { continue }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) { continue }
        $foundKey = $parts[0].Trim().TrimStart([char]0xFEFF)
        if ($foundKey -ne $Key) { continue }
        return $parts[1].Trim()
    }
    return $null
}

function Write-ReleaseMetaComplete {
    param(
        [string]$ReleaseDirPath,
        [string]$Sha,
        [string]$RefForMeta
    )
    $metaPath = Join-Path $ReleaseDirPath ".release-meta"
    $builtAt = Read-ReleaseMetaValue -MetaPath $metaPath -Key "BUILT_AT"
    if (-not $builtAt) { $builtAt = Get-Date -Format "o" }
    $lines = @(
        "GIT_SHA=$Sha",
        "GIT_REF=$RefForMeta",
        "BUILT_AT=$builtAt",
        "HOST_NAME=$env:COMPUTERNAME",
        "DEPLOY_OPERATOR=$env:USERNAME",
        "DEPLOYED_AT=$(Get-Date -Format 'o')"
    )
    $body = ($lines -join "`n") + "`n"
    Write-Utf8NoBomText -Path $metaPath -Text $body
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
    if (-not (Test-Path $dir)) { Write-Error "$dir does not exist. Run VM_SETUP_RUNBOOK first."; exit 1 }
}
if (-not (Test-Path $EnvFile)) { Write-Error "Env file not found: $EnvFile"; exit 1 }
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
# Process env from the file (including optional RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true)
# is inherited by healthcheck.ps1 and smoke.ps1 later in this script.

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

# Resolve ref to full SHA (PS 5.1 compatible). Prefer origin/<branch> for
# branch-like refs so manual dispatch with "main" cannot use a stale local branch
# in D:\retriever-rebuild\repo.
$fullSha = ""
$resolveCandidates = New-Object System.Collections.Generic.List[string]
if ($GitRef -match '^[A-Za-z0-9._/-]+$' -and $GitRef -notmatch '^refs/' -and $GitRef -notmatch '^[0-9a-fA-F]{7,40}$') {
    [void]$resolveCandidates.Add("origin/$GitRef")
}
[void]$resolveCandidates.Add($GitRef)

foreach ($candidate in $resolveCandidates) {
    $gitOutput = & git -C $AppRepo rev-parse --verify "$candidate^{commit}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitOutput) {
        $fullSha = $gitOutput.Trim()
        Write-Log "Resolved $GitRef via $candidate -> $fullSha"
        break
    }
}
if (-not $fullSha) { Write-Error "Could not resolve ref '$GitRef' to a commit in $AppRepo"; exit 1 }

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
    if ($cloneExit -ne 0) { Write-Error "git clone failed (exit $cloneExit)."; exit 1 }

    Write-Log "Checking out $fullSha ..."
    $coOutput = & git -C $releaseDir checkout -f $fullSha 2>&1 | Out-String
    $coExit = $LASTEXITCODE
    if ($coOutput.Trim()) { Write-Log "git checkout: $($coOutput.Trim())" }
    if ($coExit -ne 0) { Write-Error "git checkout failed (exit $coExit)."; exit 1 }

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
            Write-Error "Source extraction did not produce $must at $releaseDir."; exit 1
        }
    }
    Write-Log "Source extracted to release directory."

    # Stamp metadata
    $meta = "GIT_SHA=$fullSha`nGIT_REF=$GitRef`nBUILT_AT=$(Get-Date -Format 'o')`nHOST_NAME=$env:COMPUTERNAME`nDEPLOY_OPERATOR=$env:USERNAME"
    Write-Utf8NoBomText -Path "$releaseDir\.release-meta" -Text $meta

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
    if (-not (Test-Path $pythonExe)) { Write-Error "python.exe not found."; exit 1 }
    Write-Log "Python: $pythonExe"

    # ---------------------------------------------------------------------------
    # Create venv and install dependencies
    # ---------------------------------------------------------------------------
    Write-Log "Creating virtual environment ..."
    & $pythonExe -m venv "$releaseDir\.venv"
    if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed."; exit 1 }

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
    if ($pipExit -ne 0) { Write-Error "pip install failed (exit $pipExit)."; exit 1 }
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
    if ($importExit -ne 0) { Write-Error "Import check failed. Release is broken."; exit 1 }
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
if ($configResult -ne 0) { Write-Error "Config validation failed. Fix $EnvFile before deploying."; exit 1 }
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
    if ($migResult -ne 0) { Write-Error "Migrations failed."; exit 1 }
    Write-Log "Migrations complete. Verifying 0002 Fetch conversation migration ..."
    $verifyMig = Run-PythonScript -PythonExe $venvPython -Script $migrationVerifyScript -WorkDir $releaseDir
    if ($verifyMig -ne 0) { Write-Error "Post-migration verification failed (expect 0002_fetch_conversations + tables)."; exit 1 }
    Write-Log "Migration verification passed."
} else {
    Write-Log "Skipping migrations (set RETRIEVER_RUN_MIGRATIONS=true to run on next deploy)."
}

if ($env:RETRIEVER_ASSERT_MIGRATION_0002 -eq "true") {
    Write-Log "RETRIEVER_ASSERT_MIGRATION_0002: verifying 0002 is present before junction swap ..."
    $assertMig = Run-PythonScript -PythonExe $venvPython -Script $migrationVerifyScript -WorkDir $releaseDir
    if ($assertMig -ne 0) {
        Write-Error "Database missing 0002_fetch_conversations. Run deploy with RETRIEVER_RUN_MIGRATIONS=true or apply migrations, then retry."; exit 1
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

Write-ReleaseMetaComplete -ReleaseDirPath $releaseDir -Sha $fullSha -RefForMeta $GitRef
Write-Log "Updated $releaseDir\.release-meta (full stamp for current release)."

# ---------------------------------------------------------------------------
# Restart service (RetrieverRebuild only; never legacy Retriever)
# ---------------------------------------------------------------------------
Assert-NonLegacyServiceName -Name $ServiceName
Write-Log "Restarting $ServiceName (localhost:$RetrieverRebuildPort) via controlled stop/start ..."
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-DeployRecord -Status "service-not-installed" -Sha $fullSha -Prev $prevSha
    Write-Error "Deploy failed: Windows service '$ServiceName' is not installed. The release junction was swapped; run install-service.ps1, then deploy again so restart and GET /version can prove the target SHA is live."; exit 1
}

$restartOk = Restart-RetrieverRebuildForDeploy -SvcName $ServiceName -AppRootPath $AppBase
if (-not $restartOk) {
    Write-DeployRecord -Status "service-restart-failed" -Sha $fullSha -Prev $prevSha
    Write-Error "Deploy failed: could not stop/start '$ServiceName' cleanly (see steps above in $DeployLog). Junction already points at $fullSha; fix the service or port $RetrieverRebuildPort listeners, then redeploy or run rollback manually."
    exit 1
}
Start-Sleep -Seconds 2

# ---------------------------------------------------------------------------
# Live SHA gate, then health and smoke (required for deploy success)
# ---------------------------------------------------------------------------
Write-Log "Verifying running code matches deploy target (GET /version gitSha == $fullSha) ..."
if (-not (Assert-VersionGitShaMatches -ExpectedFullSha $fullSha)) {
    Write-DeployRecord -Status "version-sha-mismatch" -Sha $fullSha -Prev $prevSha
    Write-Log "/version.gitSha mismatch after controlled restart. Attempting auto-rollback ..."
    $rbOk = Invoke-DeployAutoRollback -Reason "auto-rollback: /version.gitSha did not match $fullSha after deploy"
    if ($rbOk) {
        Write-Error "Deployment failed: /version.gitSha did not match deployed commit $fullSha. Auto-rollback finished. Check $DeployLog"; exit 1
    }
    Write-Error "Deployment failed: /version.gitSha did not match deployed commit $fullSha. Auto-rollback did not complete successfully. Check $DeployLog"; exit 1
}

Write-Log "Running health check ..."
& "$AppBin\healthcheck.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-DeployRecord -Status "healthcheck-failed" -Sha $fullSha -Prev $prevSha
    Write-Log "Health check failed. Attempting auto-rollback ..."
    $rbOk = Invoke-DeployAutoRollback -Reason "auto-rollback: healthcheck failed on $fullSha"
    if ($rbOk) {
        Write-Error "Deployment failed: health check failed after deploy. Auto-rollback finished. Check $DeployLog"; exit 1
    }
    Write-Error "Deployment failed: health check failed after deploy. Auto-rollback did not complete successfully. Check $DeployLog"; exit 1
}

Write-Log "Running smoke check ..."
& "$AppBin\smoke.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-DeployRecord -Status "smoke-failed" -Sha $fullSha -Prev $prevSha
    Write-Log "Smoke check failed. Attempting auto-rollback ..."
    $rbOk = Invoke-DeployAutoRollback -Reason "auto-rollback: smoke failed on $fullSha"
    if ($rbOk) {
        Write-Error "Deployment failed: smoke check failed after deploy. Auto-rollback finished. Check $DeployLog"; exit 1
    }
    Write-Error "Deployment failed: smoke check failed after deploy. Auto-rollback did not complete successfully. Check $DeployLog"; exit 1
}

# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------
Write-DeployRecord -Status "success" -Sha $fullSha -Prev $prevSha
Write-Log "=== Deploy complete: $fullSha ==="

} finally {
    if (Test-Path $LockFile) { Remove-Item $LockFile -Force }
}
