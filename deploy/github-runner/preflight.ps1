# preflight.ps1 -- Self-hosted runner checks before GitHub Actions calls deploy.ps1
#
# Run from the workspace root during CI, or standalone on bggol-vesko01 for manual checks:
#   powershell -ExecutionPolicy Bypass -File .\deploy\github-runner\preflight.ps1
#
# Validates layout for RetrieverRebuild (8810 only). Does not touch legacy Retriever (8000).
# Contains no secrets.

$ErrorActionPreference = 'Stop'

$DeployScript = 'D:\retriever-rebuild\bin\deploy.ps1'
$EnvFile      = 'D:\retriever-rebuild\env\retriever.env'
$AppBase      = 'D:\retriever-rebuild'
$SvcNameNew   = 'RetrieverRebuild'

function Write-PreflightOk {
    param([string]$Message)
    Write-Host "[preflight] OK: $Message"
}

function Write-PreflightFail {
    param([string]$Message)
    Write-Host "::error::$Message"
    Write-Host "[preflight] FAIL: $Message"
    exit 1
}

Write-Host "[preflight] RetrieverRebuild runner checks (port 8810). Legacy Retriever on port 8000 is not altered by deploy.ps1 or this script."

if ($env:OS -ne 'Windows_NT') {
    Write-PreflightFail 'Runner must be Windows (expected OS environment Windows_NT).'
}

foreach ($must in @($AppBase, 'D:\retriever-rebuild\bin', 'D:\retriever-rebuild\releases', $EnvFile)) {
    if (-not (Test-Path $must)) {
        Write-PreflightFail "Missing path required for deploy: $must (complete deploy/VM_SETUP_RUNBOOK.md on this host)."
    }
}
Write-PreflightOk "App directories and env file exist under D:\retriever-rebuild."

if (-not (Test-Path $DeployScript)) {
    Write-PreflightFail "deploy.ps1 not found at $DeployScript - copy repo deploy scripts into bin\."
}
Write-PreflightOk "deploy.ps1 is present."

$git = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $git) {
    Write-PreflightFail 'git.exe is not on PATH (GitHub runner install adds it - repair runner or install Git).'
}
Write-PreflightOk ('git.exe: ' + $git.Source)

$svcLegacy = Get-Service -Name 'Retriever' -ErrorAction SilentlyContinue
$svcNew    = Get-Service -Name $SvcNameNew -ErrorAction SilentlyContinue

if (-not $svcNew) {
    Write-Host "::warning::$SvcNameNew service is not installed. deploy.ps1 can stage releases but cannot restart NSSM until install-service.ps1 runs."
}
else {
    Write-PreflightOk "$SvcNameNew service is registered ($($svcNew.Status))."
}

if ($svcLegacy) {
    Write-PreflightOk "Legacy 'Retriever' service is present ($($svcLegacy.Status)) - this script does not stop or restart it."
}
else {
    Write-Host "::warning::Legacy 'Retriever' service was not found; smoke legacy probe may fail unless SKIP_LEGACY."
}

Write-Host '[preflight] Done.'
exit 0
