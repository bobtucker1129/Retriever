# smoke.ps1 -- post-deploy smoke checks for RetrieverRebuild
#
# Exit 0 = all checks passed, Exit 1 = one or more failed
#
# Always checks localhost. Also checks the Cloudflare public hostname
# when RETRIEVER_SMOKE_CF_URL is set in the environment or passed as a param.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\smoke.ps1
#   $env:RETRIEVER_SMOKE_CF_URL = "https://retriever.boonegraphics.net"
#   $env:RETRIEVER_SMOKE_CF_SERVICE_TOKEN = "client-id:client-secret"

param(
    [string]$BaseUrl        = "http://127.0.0.1:8810",
    [string]$CfUrl          = $env:RETRIEVER_SMOKE_CF_URL,
    [string]$CfServiceToken = $env:RETRIEVER_SMOKE_CF_SERVICE_TOKEN
)

$ErrorActionPreference = "SilentlyContinue"
$pass = 0
$fail = 0

function Write-Result {
    param([bool]$Ok, [string]$Label, [string]$Detail = "")
    if ($Ok) {
        Write-Host "[smoke] OK:   $Label"
        $script:pass++
    } else {
        Write-Host "[smoke] FAIL: $Label $Detail"
        $script:fail++
    }
}

function Invoke-Check {
    param([string]$Url, [hashtable]$Headers = @{}, [int]$TimeoutSec = 10)
    try {
        $r = Invoke-WebRequest -Uri $Url -Headers $Headers -UseBasicParsing -TimeoutSec $TimeoutSec
        return $r
    } catch {
        return $null
    }
}

function Get-CfHeaders {
    if (-not $CfServiceToken) { return @{} }
    $parts = $CfServiceToken -split ':', 2
    return @{
        "CF-Access-Client-Id"     = $parts[0]
        "CF-Access-Client-Secret" = $parts[1]
    }
}

# ---------------------------------------------------------------------------
# 1. Localhost checks
# ---------------------------------------------------------------------------
Write-Host "[smoke] === Localhost checks ($BaseUrl) ==="

foreach ($path in @("/health/live", "/health/ready", "/version")) {
    $r = Invoke-Check -Url "$BaseUrl$path"
    Write-Result -Ok ($null -ne $r -and $r.StatusCode -lt 400) -Label $path
}

# version must contain gitSha and environment
$r = Invoke-Check -Url "$BaseUrl/version"
if ($r) {
    Write-Result -Ok ($r.Content -match '"gitSha"')      -Label "version has gitSha"
    Write-Result -Ok ($r.Content -match '"environment"') -Label "version has environment"
    Write-Result -Ok ($r.Content -notmatch '"password"') -Label "version does not leak secrets"
} else {
    Write-Result -Ok $false -Label "version body checks" -Detail "(no response)"
}

# health/ready must not leak secrets
$r = Invoke-Check -Url "$BaseUrl/health/ready"
if ($r) {
    Write-Result -Ok ($r.Content -notmatch '"password"') -Label "health does not leak secrets"
}

# /fetch must be disabled
$r = Invoke-Check -Url "$BaseUrl/fetch"
$fetchOk = ($null -eq $r) -or ($r.StatusCode -notin @(200, 302, 303, 307))
Write-Result -Ok $fetchOk -Label "/fetch is disabled"

# ---------------------------------------------------------------------------
# 2. Cloudflare-path checks (only when CfUrl is set)
# ---------------------------------------------------------------------------
if ($CfUrl) {
    Write-Host ""
    Write-Host "[smoke] === Cloudflare-path checks ($CfUrl) ==="

    $cfHeaders = Get-CfHeaders

    if ($CfServiceToken) {
        Write-Host "[smoke] Using Cloudflare Access service token."
    } else {
        Write-Host "[smoke] No service token. Expecting Access challenge on protected routes."
    }

    # health/live and version through Cloudflare
    foreach ($path in @("/health/live", "/version")) {
        $r = Invoke-Check -Url "$CfUrl$path" -Headers $cfHeaders
        Write-Result -Ok ($null -ne $r -and $r.StatusCode -lt 400) -Label "CF $path"
    }

    # Root: with service token should succeed; without should give Access challenge.
    # Cloudflare Access may return a login page as HTTP 200 (not only 302/401/403),
    # so treat a 200 response containing Access/login markers as a protected route.
    $r = Invoke-Check -Url "$CfUrl/" -Headers $cfHeaders
    if ($CfServiceToken) {
        Write-Result -Ok ($null -ne $r -and $r.StatusCode -lt 400) -Label "CF root (service token)"
    } else {
        $code = if ($r) { $r.StatusCode } else { 0 }
        $body = if ($r) { [string]$r.Content } else { "" }
        $accessLoginOk = ($code -eq 200) -and (
            $body -match "cloudflareaccess" -or
            $body -match "Cloudflare Access" -or
            $body -match "Access" -or
            $body -match "Sign in"
        )
        $challengeOk = ($code -in @(302, 303, 307, 401, 403)) -or $accessLoginOk
        Write-Result -Ok $challengeOk -Label "CF root gives Access challenge [$code]"
    }
} else {
    Write-Host ""
    Write-Host "[smoke] Cloudflare-path checks skipped."
    Write-Host "[smoke] Set RETRIEVER_SMOKE_CF_URL=https://retriever.boonegraphics.net to enable."
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[smoke] Results: $pass passed, $fail failed"
if ($fail -gt 0) {
    Write-Host "[smoke] SMOKE FAILED"
    exit 1
}
Write-Host "[smoke] SMOKE PASSED"
exit 0
