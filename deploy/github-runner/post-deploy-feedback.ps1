# post-deploy-feedback.ps1 -- machine-readable deploy feedback for CI and agents
#
# Runs on bggol-vesko01 after deploy.ps1 (or standalone). Writes JSON + summary under
# -OutputDir. Does not print secrets; does not read token/HMAC lines from retriever.env.
#
# PowerShell 5.1 compatible. ASCII-only output files (non-ASCII stripped in summaries).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\deploy\github-runner\post-deploy-feedback.ps1
#   $env:RETRIEVER_SMOKE_SKIP_LEGACY = "true"   # skip legacy :8000 probe (same as smoke.ps1)
#   $env:RETRIEVER_FEEDBACK_SKIP_LEGACY = "true"
#   $env:RETRIEVER_FEEDBACK_FAIL_ON_BROKER = "true"  # exit 1 if broker URL set but /health bad
#
param(
    [string]$BaseUrl = "http://127.0.0.1:8810",
    [string]$LegacyBaseUrl = "http://127.0.0.1:8000",
    [string]$OutputDir = "",
    [string]$EnvFile = "D:\retriever-rebuild\env\retriever.env",
    [string]$SmokeScript = "",
    [switch]$RunSmoke
)

$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# Output directory: prefer GITHUB_WORKSPACE in Actions; else cwd/deploy-feedback
# ---------------------------------------------------------------------------
if (-not $OutputDir) {
    if ($env:GITHUB_WORKSPACE -and $env:GITHUB_WORKSPACE.Trim()) {
        $OutputDir = Join-Path $env:GITHUB_WORKSPACE.Trim() "deploy-feedback"
    } else {
        $OutputDir = Join-Path (Get-Location).Path "deploy-feedback"
    }
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$JsonPath = Join-Path $OutputDir "feedback.json"
$SummaryPath = Join-Path $OutputDir "FEEDBACK_SUMMARY.md"
$SmokeTranscriptPath = Join-Path $OutputDir "smoke-transcript.txt"

$feed = New-Object System.Collections.Specialized.OrderedDictionary
$feed["generatedAt"] = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$feed["host"] = $env:COMPUTERNAME
$feed["feedbackVersion"] = "1"

if ($env:GITHUB_RUN_ID) { $feed["githubRunId"] = $env:GITHUB_RUN_ID }
if ($env:GITHUB_RUN_NUMBER) { $feed["githubRunNumber"] = $env:GITHUB_RUN_NUMBER }
if ($env:GITHUB_REF) { $feed["githubRef"] = $env:GITHUB_REF }
if ($env:GITHUB_SHA) { $feed["githubSha"] = $env:GITHUB_SHA }

$exitCode = 0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Get-SimpleEnvFileValue {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    foreach ($raw in Get-Content -LiteralPath $Path) {
        $line = $raw.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { continue }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) { continue }
        $k = $parts[0].Trim()
        if ($k -ne $Key) { continue }
        $v = $parts[1].Trim()
        if ($v.StartsWith('"') -and $v.EndsWith('"') -and $v.Length -ge 2) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        return $v
    }
    return $null
}

function Invoke-HttpProbe {
    param([string]$Url, [int]$TimeoutSec = 10)
    $row = New-Object System.Collections.Specialized.OrderedDictionary
    $row["url"] = $Url
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        $row["statusCode"] = [int]$r.StatusCode
        $row["ok"] = [bool]($r.StatusCode -lt 400)
        $row["error"] = $null
        return @{ Row = $row; Response = $r }
    } catch {
        $code = $null
        $ok = $false
        try {
            if ($_.Exception.Response) {
                $code = [int]$_.Exception.Response.StatusCode
                $ok = $false
            }
        } catch { }
        $row["statusCode"] = $code
        $row["ok"] = $ok
        $row["error"] = $_.Exception.Message
        return @{ Row = $row; Response = $null }
    }
}

function Remove-NonAscii {
    param([string]$Text)
    if ($null -eq $Text) { return "" }
    return -join ($Text.ToCharArray() | Where-Object { [int]$_ -lt 128 })
}

function Test-BrokerProbeUrl {
    param([string]$TrimmedUrl, [ref]$ReasonOut)
    $ReasonOut.Value = $null
    if ([string]::IsNullOrWhiteSpace($TrimmedUrl)) {
        $ReasonOut.Value = "not_set"
        return $false
    }
    if ($TrimmedUrl.IndexOf("<") -ge 0 -or $TrimmedUrl.IndexOf(">") -ge 0) {
        $ReasonOut.Value = "placeholder_or_template"
        return $false
    }
    $uri = $null
    if (-not [uri]::TryCreate($TrimmedUrl, [System.UriKind]::Absolute, [ref]$uri)) {
        $ReasonOut.Value = "invalid_uri"
        return $false
    }
    if ($uri.Scheme -ne "http" -and $uri.Scheme -ne "https") {
        $ReasonOut.Value = "invalid_uri"
        return $false
    }
    return $true
}

function Resolve-SmokePath {
    if ($SmokeScript -and (Test-Path -LiteralPath $SmokeScript)) { return $SmokeScript }
    $binSmoke = "D:\retriever-rebuild\bin\smoke.ps1"
    if (Test-Path -LiteralPath $binSmoke) { return $binSmoke }
    $here = $PSScriptRoot
    if ($here) {
        $rel = Join-Path $here "..\smoke.ps1"
        if (Test-Path -LiteralPath $rel) { return $rel }
    }
    return $null
}

# ---------------------------------------------------------------------------
# Service states
# ---------------------------------------------------------------------------
$servicesOut = New-Object System.Collections.Specialized.OrderedDictionary
foreach ($name in @("RetrieverRebuild", "Retriever")) {
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    $sentry = New-Object System.Collections.Specialized.OrderedDictionary
    if ($svc) {
        $sentry["exists"] = $true
        $sentry["status"] = ($svc.Status).ToString()
        $sentry["name"] = $svc.Name
    } else {
        $sentry["exists"] = $false
        $sentry["status"] = "missing"
        $sentry["name"] = $name
    }
    $servicesOut[$name] = $sentry
}
$feed["windowsServices"] = $servicesOut

# ---------------------------------------------------------------------------
# RetrieverRebuild HTTP probes
# ---------------------------------------------------------------------------
$rebuild = New-Object System.Collections.Specialized.OrderedDictionary
$rebuild["baseUrl"] = $BaseUrl

# /version
$vProbe = Invoke-HttpProbe -Url ($BaseUrl + "/version")
$rebuild["version"] = $vProbe.Row
$gitShaOk = $true
$gitRefVal = $null
$gitShaVal = $null
if ($vProbe.Response -and $vProbe.Response.StatusCode -lt 400) {
    try {
        $vj = $vProbe.Response.Content | ConvertFrom-Json
        if ($vj.PSObject.Properties.Name -contains 'gitSha') { $gitShaVal = [string]$vj.gitSha }
        if ($vj.PSObject.Properties.Name -contains 'gitRef') { $gitRefVal = [string]$vj.gitRef }
    } catch {
        $rebuild["versionParseError"] = $_.Exception.Message
    }
}
$badSha = ($gitShaVal -eq "dev" -or $gitShaVal -eq "local" -or [string]::IsNullOrWhiteSpace($gitShaVal))
$badRef = ($gitRefVal -eq "local")
if ($badSha -or $badRef) { $gitShaOk = $false }
$rebuild["gitShaValue"] = if ($gitShaVal) { $gitShaVal } else { $null }
$rebuild["gitRefValue"] = if ($gitRefVal) { $gitRefVal } else { $null }
$rebuild["gitStampOk"] = $gitShaOk

# /health/live
$liveProbe = Invoke-HttpProbe -Url ($BaseUrl + "/health/live")
$rebuild["healthLive"] = $liveProbe.Row

# /health/ready
$readyProbe = Invoke-HttpProbe -Url ($BaseUrl + "/health/ready")
$rebuild["healthReady"] = $readyProbe.Row
$readyChecks = $null
if ($readyProbe.Response -and $readyProbe.Response.StatusCode -lt 400) {
    try {
        $readyJson = $readyProbe.Response.Content | ConvertFrom-Json
        $readyChecks = New-Object System.Collections.Specialized.OrderedDictionary
        if ($readyJson.checks) {
            foreach ($prop in $readyJson.checks.PSObject.Properties) {
                $readyChecks[($prop.Name)] = [string]$prop.Value
            }
        }
        $rebuild["healthReadyStatus"] = [string]$readyJson.status
    } catch {
        $rebuild["healthReadyParseError"] = $_.Exception.Message
    }
}
if ($readyChecks) { $rebuild["healthReadyChecks"] = $readyChecks }

# GET /fetch (status only; no cookie jar)
$fetchProbe = Invoke-HttpProbe -Url ($BaseUrl + "/fetch") -TimeoutSec 12
$fetchRow = New-Object System.Collections.Specialized.OrderedDictionary
$fetchRow["statusCode"] = $fetchProbe.Row["statusCode"]
$fetchRow["ok"] = $fetchProbe.Row["ok"]
$fetchRow["error"] = $fetchProbe.Row["error"]
$localFetch = ($env:RETRIEVER_SMOKE_LOCAL_FETCH -eq "true")
if ($null -ne $fetchProbe.Row["statusCode"]) {
    $fc = [int]$fetchProbe.Row["statusCode"]
    $fetchOk = ($fc -in @(401, 403)) -or ($localFetch -and $fc -eq 200)
    $fetchRow["expectsAnonymousBlockedOrLocal"] = $fetchOk
} else {
    $fetchRow["expectsAnonymousBlockedOrLocal"] = $false
}
$rebuild["fetchGet"] = $fetchRow

$feed["retrieverRebuild"] = $rebuild

# ---------------------------------------------------------------------------
# Broker GET /health when BOONEOPS_BROKER_URL is present in env file
# ---------------------------------------------------------------------------
$brokerBase = Get-SimpleEnvFileValue -Path $EnvFile -Key "BOONEOPS_BROKER_URL"
$brokerTrimmed = if ($brokerBase) { $brokerBase.Trim() } else { "" }
$brokerSkipReason = $null
$brokerProbeOk = Test-BrokerProbeUrl -TrimmedUrl $brokerTrimmed -ReasonOut ([ref]$brokerSkipReason)

$brokerOut = New-Object System.Collections.Specialized.OrderedDictionary
$brokerOut["envFile"] = $EnvFile
$brokerOut["envValuePresent"] = [bool]($brokerTrimmed.Length -gt 0)
$brokerOut["urlConfigured"] = [bool]$brokerProbeOk
$brokerOut["skipReason"] = if ($brokerProbeOk) { $null } else { $brokerSkipReason }
$brokerOut["probeRan"] = $false
$brokerOut["healthUrl"] = $null
$brokerOut["statusCode"] = $null
$brokerOut["ok"] = $null
$brokerOut["error"] = $null

if ($brokerProbeOk) {
    $bb = $brokerTrimmed.TrimEnd("/")
    $healthUrl = $bb + "/health"
    $brokerOut["probeRan"] = $true
    $brokerOut["healthUrl"] = $healthUrl
    $bh = Invoke-HttpProbe -Url $healthUrl -TimeoutSec 10
    $brokerOut["statusCode"] = $bh.Row["statusCode"]
    $brokerOut["ok"] = [bool]($bh.Row["ok"])
    $brokerOut["error"] = $bh.Row["error"]
    if ($env:RETRIEVER_FEEDBACK_FAIL_ON_BROKER -eq "true") {
        if (-not $brokerOut["ok"]) { $exitCode = 1 }
    }
}
$feed["booneopsBroker"] = $brokerOut

# ---------------------------------------------------------------------------
# Legacy Retriever liveness
# ---------------------------------------------------------------------------
$skipLegacy =
    ($env:RETRIEVER_SMOKE_SKIP_LEGACY -eq "true") -or
    ($env:RETRIEVER_FEEDBACK_SKIP_LEGACY -eq "true")

$legacyOut = New-Object System.Collections.Specialized.OrderedDictionary
$legacyOut["skipped"] = [bool]$skipLegacy
$legacyOut["baseUrl"] = $LegacyBaseUrl
if (-not $skipLegacy) {
    $lg = Invoke-HttpProbe -Url $LegacyBaseUrl -TimeoutSec 8
    $legacyOut["statusCode"] = $lg.Row["statusCode"]
    $legacyOut["ok"] = $lg.Row["ok"]
    $legacyOut["error"] = $lg.Row["error"]
} else {
    $legacyOut["statusCode"] = $null
    $legacyOut["ok"] = $null
    $legacyOut["error"] = $null
}
$feed["legacyRetriever"] = $legacyOut

# ---------------------------------------------------------------------------
# Optional smoke transcript (second pass; deploy.ps1 already ran smoke on success)
# ---------------------------------------------------------------------------
$smokeMeta = New-Object System.Collections.Specialized.OrderedDictionary
$smokeMeta["ran"] = [bool]$RunSmoke
$smokeMeta["transcriptPath"] = $null
$smokeMeta["exitCode"] = $null

if ($RunSmoke) {
    $sp = Resolve-SmokePath
    if ($sp) {
        $smokeMeta["script"] = $sp
        $smokeMeta["transcriptPath"] = $SmokeTranscriptPath
        try {
            & $sp *>&1 | Out-File -FilePath $SmokeTranscriptPath -Encoding ascii
            $smokeMeta["exitCode"] = $LASTEXITCODE
        } catch {
            $smokeMeta["exitCode"] = 1
            $smokeMeta["error"] = $_.Exception.Message
        }
    } else {
        $smokeMeta["error"] = "smoke.ps1 path not found"
    }
}
$feed["smoke"] = $smokeMeta

# ---------------------------------------------------------------------------
# Write JSON + summary
# ---------------------------------------------------------------------------
$feed | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $JsonPath -Encoding ascii

$lines = New-Object System.Collections.Generic.List[string]
[void]$lines.Add("# RetrieverRebuild deploy feedback")
[void]$lines.Add("")
$genAt = $feed["generatedAt"]
$hostNm = $feed["host"]
[void]$lines.Add("- Generated (UTC): $genAt")
[void]$lines.Add("- Host: $hostNm")
if ($feed["githubRunNumber"]) {
    $grn = $feed["githubRunNumber"]
    $grid = $feed["githubRunId"]
    [void]$lines.Add("- GitHub run: $grn (id $grid)")
}
[void]$lines.Add("")
[void]$lines.Add("## RetrieverRebuild ($BaseUrl)")
[void]$lines.Add("")
[void]$lines.Add("| Check | Result |")
[void]$lines.Add("| --- | --- |")
$vs = $rebuild["version"]["statusCode"]
[void]$lines.Add("| GET /version | $vs |")
$gitStampText = if ($gitShaOk) { "yes" } else { "NO" }
[void]$lines.Add("| git stamp ok (not dev/local placeholder) | $gitStampText |")
if ($gitShaVal) { [void]$lines.Add("| gitSha | $gitShaVal |") }
if ($gitRefVal) { [void]$lines.Add("| gitRef | $gitRefVal |") }
$ls = $rebuild["healthLive"]["statusCode"]
[void]$lines.Add("| GET /health/live | $ls |")
$rs = $rebuild["healthReady"]["statusCode"]
[void]$lines.Add("| GET /health/ready | $rs |")
$fs = $fetchRow["statusCode"]
$fok = $fetchRow["expectsAnonymousBlockedOrLocal"]
[void]$lines.Add("| GET /fetch (expect 401/403 or local 200) | $fs (ok=$fok) |")
[void]$lines.Add("")
[void]$lines.Add("## BooneOps broker (optional)")
[void]$lines.Add("")
if ($brokerOut["probeRan"]) {
    [void]$lines.Add("- Probed: $($brokerOut['healthUrl'])")
    [void]$lines.Add("- HTTP: $($brokerOut['statusCode']) ok=$($brokerOut['ok'])")
    if ($brokerOut["error"]) { [void]$lines.Add("- Error: $(Remove-NonAscii ([string]$brokerOut['error']))") }
} elseif ($brokerOut["envValuePresent"] -and $brokerOut["skipReason"]) {
    $sr = [string]$brokerOut["skipReason"]
    if ($sr -eq "placeholder_or_template") {
        [void]$lines.Add("- Skipped: BOONEOPS_BROKER_URL looks like a placeholder (contains angle brackets); not probed.")
    } elseif ($sr -eq "invalid_uri") {
        [void]$lines.Add("- Skipped: BOONEOPS_BROKER_URL is not a valid absolute http(s) URL; not probed.")
    } else {
        [void]$lines.Add("- Skipped: BOONEOPS_BROKER_URL not usable for probe (reason: $sr).")
    }
} else {
    [void]$lines.Add("- Skipped (BOONEOPS_BROKER_URL not set in env file).")
}
[void]$lines.Add("")
[void]$lines.Add("## Legacy Retriever (8000)")
[void]$lines.Add("")
if ($skipLegacy) {
    [void]$lines.Add("- Skipped (RETRIEVER_SMOKE_SKIP_LEGACY or RETRIEVER_FEEDBACK_SKIP_LEGACY).")
} else {
    [void]$lines.Add("- HTTP: $($legacyOut['statusCode']) ok=$($legacyOut['ok'])")
    if ($legacyOut["error"]) { [void]$lines.Add("- Error: $(Remove-NonAscii ([string]$legacyOut['error']))") }
}
[void]$lines.Add("")
[void]$lines.Add("## Windows services")
[void]$lines.Add("")
foreach ($svcName in $servicesOut.Keys) {
    $se = $servicesOut[$svcName]
    [void]$lines.Add("- ${svcName}: exists=$($se['exists']) status=$($se['status'])")
}
[void]$lines.Add("")
[void]$lines.Add("## Smoke transcript")
[void]$lines.Add("")
if ($RunSmoke -and $smokeMeta["transcriptPath"]) {
    [void]$lines.Add("- Path: $($smokeMeta['transcriptPath'])")
    [void]$lines.Add("- Exit code: $($smokeMeta['exitCode'])")
} else {
    [void]$lines.Add("- Not captured (omit -RunSmoke or script missing).")
}
[void]$lines.Add("")
[void]$lines.Add("## Artifacts")
[void]$lines.Add("")
[void]$lines.Add("- JSON: $JsonPath")
[void]$lines.Add("- This summary: $SummaryPath")

$summaryText = (($lines | ForEach-Object { Remove-NonAscii $_ }) -join "`r`n") + "`r`n"
Set-Content -LiteralPath $SummaryPath -Value $summaryText -Encoding ascii

Write-Host "=== Post-deploy feedback ==="
Write-Host $summaryText

exit $exitCode
