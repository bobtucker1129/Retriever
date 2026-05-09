# healthcheck.ps1 -- fast localhost health check for RetrieverRebuild
#
# Exit 0 = healthy, Exit 1 = failed
# Used by deploy.ps1, rollback.ps1, and manual checks.
#
# Targets ONLY port 8810 (RetrieverRebuild). Does not probe legacy Retriever.

param(
    [string]$BaseUrl = "http://127.0.0.1:8810",
    [int]$MaxWaitSeconds = 15
)

$ErrorActionPreference = "SilentlyContinue"

function Write-Check {
    param([string]$Label, [bool]$Pass, [string]$Detail = "")
    if ($Pass) {
        Write-Host "[healthcheck] OK:   $Label"
    } else {
        Write-Host "[healthcheck] FAIL: $Label $Detail"
    }
}

# ---------------------------------------------------------------------------
# Wait for the process to accept connections
# ---------------------------------------------------------------------------
Write-Host "[healthcheck] Waiting for service on $BaseUrl ..."
$elapsed = 0
$ready = $false
while ($elapsed -lt $MaxWaitSeconds) {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/health/live" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -lt 400) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
    $elapsed += 2
}

if (-not $ready) {
    Write-Host "[healthcheck] FAIL: Service did not respond within ${MaxWaitSeconds}s."
    exit 1
}

# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------
$allPassed = $true

foreach ($path in @("/health/live", "/health/ready", "/version")) {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl$path" -UseBasicParsing -TimeoutSec 8
        Write-Check -Label $path -Pass ($r.StatusCode -lt 400)
        if ($r.StatusCode -ge 400) { $allPassed = $false }
    } catch {
        Write-Check -Label $path -Pass $false -Detail $_.Exception.Message
        $allPassed = $false
    }
}

# ---------------------------------------------------------------------------
# Check health/ready does not report 'failed' dependencies
# ---------------------------------------------------------------------------
try {
    $r    = Invoke-WebRequest -Uri "$BaseUrl/health/ready" -UseBasicParsing -TimeoutSec 8
    $body = $r.Content | ConvertFrom-Json
    $failedDeps = @()
    foreach ($prop in $body.checks.PSObject.Properties) {
        if ($prop.Value -eq "failed") { $failedDeps += $prop.Name }
    }
    if ($failedDeps.Count -gt 0) {
        Write-Host "[healthcheck] FAIL: Required dependencies are 'failed': $($failedDeps -join ', ')"
        $allPassed = $false
    } else {
        Write-Host "[healthcheck] OK:   No required dependencies failed"
    }
    $fetchState = $body.checks.fetch
    $modelState = $body.checks.modelProvider
    if ($fetchState -ne "disabled" -or $modelState -ne "disabled") {
        Write-Host "[healthcheck] FAIL: Fetch/model routing must stay disabled until explicitly enabled (fetch=$fetchState modelProvider=$modelState)"
        $allPassed = $false
    } else {
        Write-Host "[healthcheck] OK:   Fetch integration and model routing disabled"
    }
} catch {
    Write-Host "[healthcheck] WARN: Could not parse health/ready body: $($_.Exception.Message)"
}

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
if ($allPassed) {
    Write-Host "[healthcheck] Health check passed."
    exit 0
} else {
    Write-Host "[healthcheck] Health check FAILED."
    exit 1
}
