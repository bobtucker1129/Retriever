# smoke.ps1 -- post-deploy smoke checks for RetrieverRebuild
#
# Exit 0 = all checks passed, Exit 1 = one or more failed
#
# Targets ONLY the new service (localhost:8810 by default). Optionally verifies
# legacy Retriever on port 8000 still accepts connections — does NOT stop or
# restart legacy service "Retriever".
#
# Always checks localhost. Also checks the Cloudflare public hostname
# when RETRIEVER_SMOKE_CF_URL is set in the environment or passed as a param.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\smoke.ps1
#   $env:RETRIEVER_SMOKE_CF_URL = "https://retriever.boonegraphics.net"
#   $env:RETRIEVER_SMOKE_CF_SERVICE_TOKEN = "client-id:client-secret"
#   $env:RETRIEVER_SMOKE_SKIP_LEGACY = "true"   # skip legacy :8000 check
#   $env:RETRIEVER_SMOKE_LOCAL_FETCH = "true"   # allow anonymous /fetch 200 (local dev identity)
#   $env:RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED = "true"
#       # pilot: FETCH_ENABLED=true on the service — assert checks.fetch and checks.modelProvider are "ok" (not disabled)

param(
    [string]$BaseUrl        = "http://127.0.0.1:8810",
    [string]$CfUrl          = $env:RETRIEVER_SMOKE_CF_URL,
    [string]$CfServiceToken = $env:RETRIEVER_SMOKE_CF_SERVICE_TOKEN,
    [string]$LegacyBaseUrl  = "http://127.0.0.1:8000",
    [switch]$SkipLegacyCheck
)

$effectiveSkipLegacy = $SkipLegacyCheck -or ($env:RETRIEVER_SMOKE_SKIP_LEGACY -eq "true")
$expectFetchEnabledPilot = ($env:RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED -eq "true")

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
        if ($_.Exception.Response) {
            return $_.Exception.Response
        }
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
if ($expectFetchEnabledPilot) {
    Write-Host "[smoke] Pilot: RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true (expect checks.fetch/modelProvider = ok)"
}

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

# health/ready must not leak secrets.
# Default: Fetch + modelProvider must be disabled (foundation). Pilot: RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true expects both "ok".
$r = Invoke-Check -Url "$BaseUrl/health/ready"
if ($r) {
    Write-Result -Ok ($r.Content -notmatch '"password"') -Label "health does not leak secrets"
    try {
        $ready = $r.Content | ConvertFrom-Json
        $fetchState = $ready.checks.fetch
        $modelState = $ready.checks.modelProvider
        if ($expectFetchEnabledPilot) {
            Write-Result -Ok ($fetchState -eq "ok") -Label "health: fetch integration enabled (pilot expects ok) [$fetchState]"
            Write-Result -Ok ($modelState -eq "ok") -Label "health: model routing enabled for pilot (expects ok) [$modelState]"
        } else {
            Write-Result -Ok ($fetchState -eq "disabled") -Label "health: fetch integration disabled [$fetchState]"
            Write-Result -Ok ($modelState -eq "disabled") -Label "health: model routing disabled [$modelState]"
        }
    } catch {
        Write-Result -Ok $false -Label "health/ready Fetch guardrails parse" -Detail $_.Exception.Message
    }
} else {
    Write-Result -Ok $false -Label "health/ready Fetch guardrails" -Detail "(no response)"
}

# GET /fetch: production should require Cloudflare identity (401) or deny (403);
# anonymous HTML 200 is a misconfiguration unless local-dev override is set.
$r = Invoke-Check -Url "$BaseUrl/fetch"
$localFetch = ($env:RETRIEVER_SMOKE_LOCAL_FETCH -eq "true")
if ($r) {
    $c = [int]$r.StatusCode
    $fetchRouteOk =
        ($c -in @(401, 403)) -or
        ($localFetch -and $c -eq 200)
    Write-Result -Ok $fetchRouteOk -Label "/fetch requires identity or local override [$c]"
} else {
    Write-Result -Ok $false -Label "/fetch requires identity or local override" -Detail "(no response)"
}

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

    # Fetch shell through Cloudflare: with service token, expect shell HTML (200) or gate (403), not 401
    if ($CfServiceToken) {
        $rf = Invoke-Check -Url "$CfUrl/fetch" -Headers $cfHeaders
        if ($rf) {
            $fc = [int]$rf.StatusCode
            $cfFetchOk = ($fc -in @(200, 403)) -and ($fc -ne 401)
            Write-Result -Ok $cfFetchOk -Label "CF /fetch reachable with token [$fc]"
        } else {
            Write-Result -Ok $false -Label "CF /fetch reachable with token" -Detail "(no response)"
        }
        $rcf = Invoke-Check -Url "$CfUrl/health/ready" -Headers $cfHeaders
        if ($rcf) {
            try {
                $cj = $rcf.Content | ConvertFrom-Json
                if ($expectFetchEnabledPilot) {
                    Write-Result -Ok ($cj.checks.fetch -eq "ok") -Label "CF health: fetch enabled pilot (expects ok) [$($cj.checks.fetch)]"
                    Write-Result -Ok ($cj.checks.modelProvider -eq "ok") -Label "CF health: model routing pilot (expects ok) [$($cj.checks.modelProvider)]"
                } else {
                    Write-Result -Ok ($cj.checks.fetch -eq "disabled") -Label "CF health: fetch disabled"
                    Write-Result -Ok ($cj.checks.modelProvider -eq "disabled") -Label "CF health: model routing disabled"
                }
            } catch {
                Write-Result -Ok $false -Label "CF health/ready parse" -Detail $_.Exception.Message
            }
        }
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
# 3. Legacy Retriever (port 8000) — read-only liveness
# ---------------------------------------------------------------------------
if (-not $effectiveSkipLegacy) {
    Write-Host ""
    Write-Host "[smoke] === Legacy Retriever liveness ($LegacyBaseUrl) ==="
    try {
        $lr = Invoke-WebRequest -Uri $LegacyBaseUrl -UseBasicParsing -TimeoutSec 8
        Write-Result -Ok ($lr.StatusCode -gt 0) -Label "legacy HTTP responds [$($lr.StatusCode)]"
    } catch {
        Write-Result -Ok $false -Label "legacy HTTP responds" -Detail $_.Exception.Message
    }
} else {
    Write-Host ""
    Write-Host "[smoke] Legacy Retriever check skipped (-SkipLegacyCheck or RETRIEVER_SMOKE_SKIP_LEGACY)."
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
