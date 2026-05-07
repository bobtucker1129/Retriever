# rollback.ps1 -- revert RetrieverRebuild to the previous release
#
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\rollback.ps1
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\rollback.ps1 -Reason "health check failure"
#
# Does NOT require GitHub or pip. Works from releases already on disk.

param(
    [string]$Reason = "manual rollback",
    [string]$AppBase = "D:\retriever-rebuild"
)

$ErrorActionPreference = "Stop"

$AppBin      = "$AppBase\bin"
$LogDir      = "$AppBase\logs"
$DeployLog   = "$LogDir\deploy.log"
$LockFile    = "$AppBase\deploy.lock"
$ServiceName = "RetrieverRebuild"
$currentLink  = "$AppBase\current"
$previousLink = "$AppBase\previous"

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
    $line = "[$ts] $Message"
    Write-Host $line
    $line | Out-File -FilePath $DeployLog -Append -Encoding utf8
}

function Set-Junction {
    param([string]$Link, [string]$Target)
    if (Test-Path $Link) {
        Remove-Item $Link -Force -Recurse -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null
}

# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------
if (Test-Path $LockFile) {
    Write-Log "ERROR: Deploy lock exists. Another operation may be running."
    exit 1
}
"$env:USERNAME $(Get-Date -Format 'o') rollback" | Out-File $LockFile -Encoding utf8

try {

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
if (-not (Test-Path $currentLink))  { throw "No current release at $currentLink. Cannot roll back." }
if (-not (Test-Path $previousLink)) { throw "No previous release at $previousLink. Cannot roll back." }

$currentTarget  = (Get-Item $currentLink).Target
$previousTarget = (Get-Item $previousLink).Target
$currentSha  = Split-Path -Leaf $currentTarget
$previousSha = Split-Path -Leaf $previousTarget

if (-not (Test-Path $previousTarget)) { throw "Previous release directory $previousTarget does not exist on disk." }
if ($currentSha -eq $previousSha) { throw "current and previous point to the same release ($currentSha). Nothing to roll back." }

Write-Log "=== Rollback starting ==="
Write-Log "Current : $currentSha"
Write-Log "Restoring: $previousSha"
Write-Log "Reason  : $Reason"

# ---------------------------------------------------------------------------
# Swap junctions
# ---------------------------------------------------------------------------
Set-Junction -Link $previousLink -Target $currentTarget
Set-Junction -Link $currentLink  -Target $previousTarget
Write-Log "current -> $previousTarget"
Write-Log "previous -> $currentTarget"

# ---------------------------------------------------------------------------
# Restart service
# ---------------------------------------------------------------------------
Write-Log "Restarting $ServiceName ..."
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    Restart-Service -Name $ServiceName -Force
    Start-Sleep -Seconds 4
    $svc.Refresh()
    if ($svc.Status -ne 'Running') { throw "Service is not running after rollback restart." }
    Write-Log "Service restarted."
} else {
    Write-Log "WARNING: Service '$ServiceName' not found. Junctions swapped but service not restarted."
}

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
Write-Log "Running health check ..."
& "$AppBin\healthcheck.ps1"
if ($LASTEXITCODE -ne 0) { throw "Health check failed after rollback. Manual inspection required." }

# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------
$ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"
@"
---
rolledBackAt: $ts
operator: $env:USERNAME
restoredSha: $previousSha
replacedSha: $currentSha
host: $env:COMPUTERNAME
service: $ServiceName
reason: $Reason
status: success
"@ | Out-File $DeployLog -Append -Encoding utf8

Write-Log "=== Rollback complete: restored $previousSha ==="

} finally {
    if (Test-Path $LockFile) { Remove-Item $LockFile -Force }
}
