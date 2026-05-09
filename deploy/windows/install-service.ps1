# install-service.ps1 -- register RetrieverRebuild as a Windows Service via NSSM
#
# Run once (or again to update) as Administrator:
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\install-service.ps1
#
# Manages ONLY RetrieverRebuild on port 8810. Never pass ServiceName "Retriever"
# (legacy PrePress stack on port 8000).

param(
    [string]$ServiceName = "RetrieverRebuild",
    [string]$AppBase     = "D:\retriever-rebuild",
    [int]$Port           = 8810
)

# Use Continue because Windows PowerShell 5.1 can turn native-command stderr
# into parser-looking failures when ErrorActionPreference is Stop. Explicit
# exit-code checks below handle real failures.
$ErrorActionPreference = "Continue"

if ($ServiceName -eq "Retriever") {
    throw "Refusing to install NSSM app for legacy service 'Retriever'. Use -ServiceName RetrieverRebuild (port 8810) only; do not replace the old Retriever service."
}
if ([int]$Port -eq 8000) {
    throw "Refusing Port 8000 — legacy Retriever owns that port. Use -Port 8810 for RetrieverRebuild."
}

# ---------------------------------------------------------------------------
# Locate NSSM (same search order as old Retriever)
# ---------------------------------------------------------------------------
function Resolve-NssmPath {
    $cmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Path }
    $candidates = @(
        "C:\nssm\win64\nssm.exe",
        "C:\tools\nssm\nssm.exe",
        "C:\Program Files\nssm\nssm.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    throw "nssm.exe not found. NSSM must be installed (it is already present for old Retriever)."
}

function Invoke-Nssm {
    param([string]$NssmPath, [string[]]$NssmArgs)
    & $NssmPath @NssmArgs
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM command failed (exit $LASTEXITCODE): $($NssmArgs -join ' ')"
    }
}

$nssm = Resolve-NssmPath
Write-Host "NSSM found at: $nssm"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$runScript = Join-Path $AppBase "bin\run-service.ps1"
$LogDir    = Join-Path $AppBase "logs"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

if (-not (Test-Path $runScript)) {
    throw "Launcher script not found: $runScript`nRun deploy.ps1 first to create the initial release, then copy bin\ scripts."
}

# ---------------------------------------------------------------------------
# Stop existing service if present
# ---------------------------------------------------------------------------
$svcExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svcExists) {
    Write-Host "Service '$ServiceName' exists - stopping before update."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

# ---------------------------------------------------------------------------
# Install or update via NSSM
# ---------------------------------------------------------------------------
$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$appParams     = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -AppBase `"$AppBase`" -Port $Port"

if (-not $svcExists) {
    Write-Host "Installing service '$ServiceName'."
    Invoke-Nssm -NssmPath $nssm -NssmArgs @("install", $ServiceName, $powershellExe, $appParams)
} else {
    Write-Host "Updating service '$ServiceName' application parameters."
    Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "Application", $powershellExe)
    Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppParameters", $appParams)
}

Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppDirectory",  $AppBase)
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "DisplayName",   "Retriever Rebuild Service")
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "Description",   "New Retriever app (auth shell + Fetch) on port 8810.")
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "Start",         "SERVICE_AUTO_START")
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppStdout",     (Join-Path $LogDir "service-stdout.log"))
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppStderr",     (Join-Path $LogDir "service-stderr.log"))
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppRotateFiles",  "1")
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppRotateOnline", "1")
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppRotateBytes",  "10485760")
Invoke-Nssm -NssmPath $nssm -NssmArgs @("set", $ServiceName, "AppExit", "Default", "Restart")

# Service recovery: restart on failure
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
sc.exe failureflag $ServiceName 1 | Out-Null

# ---------------------------------------------------------------------------
# Start the service
# ---------------------------------------------------------------------------
Write-Host "Starting service '$ServiceName'."
Start-Service -Name $ServiceName
Start-Sleep -Seconds 4

try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health/live" -UseBasicParsing -TimeoutSec 8
    Write-Host "Health check OK: $($resp.StatusCode)"
} catch {
    Write-Warning "Service started but health check failed. Check $LogDir\service-stderr.log"
}

Write-Host ""
Write-Host "RetrieverRebuild service installation complete."
Write-Host "Service name : $ServiceName"
Write-Host "Port         : $Port"
Write-Host "Logs         : $LogDir"
Write-Host ""
Write-Host "To manage:"
Write-Host "  Start-Service $ServiceName"
Write-Host "  Stop-Service  $ServiceName"
Write-Host "  Get-Service   $ServiceName"
