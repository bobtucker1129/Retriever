#!/usr/bin/env bash
# smoke.sh -- post-deploy smoke checks for retriever-rebuild
#
# Usage: /opt/retriever-rebuild/bin/smoke.sh
# Exit 0 = all checks passed, Exit 1 = one or more failed
#
# Checks localhost (always) and the Cloudflare public hostname (when configured).
# Set RETRIEVER_SMOKE_CF_URL to enable Cloudflare-path checks.
# Set RETRIEVER_SMOKE_CF_SERVICE_TOKEN to authenticate with a Cloudflare Access service token.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL="${RETRIEVER_SMOKE_BASE_URL:-http://127.0.0.1:8810}"
CF_URL="${RETRIEVER_SMOKE_CF_URL:-}"                      # e.g. https://retriever.boonegraphics.net
CF_SERVICE_TOKEN="${RETRIEVER_SMOKE_CF_SERVICE_TOKEN:-}"  # stored on VM, never in Cursor

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
  echo "[smoke] $*"
}

check() {
  local label="$1"
  local url="$2"
  shift 2
  local extra_args=("$@")
  local http_code
  http_code="$(curl -fsS --max-time 10 -o /dev/null -w "%{http_code}" "${extra_args[@]}" "$url" 2>&1)" \
    || { log "FAIL: ${label} -- no response from ${url}"; FAIL=$((FAIL + 1)); return; }
  if [[ "$http_code" =~ ^[23] ]]; then
    log "OK:   ${label} [${http_code}]"
    PASS=$((PASS + 1))
  else
    log "FAIL: ${label} [${http_code}] -- ${url}"
    FAIL=$((FAIL + 1))
  fi
}

check_body_contains() {
  local label="$1"
  local url="$2"
  local pattern="$3"
  shift 3
  local extra_args=("$@")
  local body
  body="$(curl -fsS --max-time 10 "${extra_args[@]}" "$url" 2>&1)" \
    || { log "FAIL: ${label} -- no response from ${url}"; FAIL=$((FAIL + 1)); return; }
  if echo "$body" | grep -q "$pattern"; then
    log "OK:   ${label}"
    PASS=$((PASS + 1))
  else
    log "FAIL: ${label} -- expected pattern '${pattern}' not found in response"
    FAIL=$((FAIL + 1))
  fi
}

check_body_absent() {
  local label="$1"
  local url="$2"
  local pattern="$3"
  shift 3
  local extra_args=("$@")
  local body
  body="$(curl -fsS --max-time 10 "${extra_args[@]}" "$url" 2>&1)" \
    || { log "FAIL: ${label} -- no response from ${url}"; FAIL=$((FAIL + 1)); return; }
  if ! echo "$body" | grep -q "$pattern"; then
    log "OK:   ${label} (secret absent)"
    PASS=$((PASS + 1))
  else
    log "FAIL: ${label} -- sensitive pattern '${pattern}' found in response"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# 1. Localhost checks
# ---------------------------------------------------------------------------
log "=== Localhost checks (${BASE_URL}) ==="

check           "health/live"              "${BASE_URL}/health/live"
check           "health/ready"             "${BASE_URL}/health/ready"
check           "version"                  "${BASE_URL}/version"
check_body_contains "version has gitSha"   "${BASE_URL}/version"     '"gitSha"'
check_body_contains "version has env"      "${BASE_URL}/version"     '"environment"'
check_body_absent   "health does not leak secrets" \
                                           "${BASE_URL}/health/ready" '"password"'
check_body_absent   "version does not leak secrets" \
                                           "${BASE_URL}/version"      '"password"'

# Fetch must be disabled
FETCH_CODE="$(curl -fsS --max-time 10 -o /dev/null -w "%{http_code}" "${BASE_URL}/fetch" 2>/dev/null || echo "000")"
if [[ "$FETCH_CODE" =~ ^(200|307|302|303)$ ]]; then
  log "WARN: /fetch is reachable (HTTP ${FETCH_CODE}). Confirm FETCH_ENABLED is intentionally set."
else
  log "OK:   /fetch is disabled (HTTP ${FETCH_CODE})"
  PASS=$((PASS + 1))
fi

# ---------------------------------------------------------------------------
# 2. Cloudflare-path checks (only when CF_URL is set)
# ---------------------------------------------------------------------------
if [[ -n "$CF_URL" ]]; then
  log ""
  log "=== Cloudflare-path checks (${CF_URL}) ==="

  CF_ARGS=()
  if [[ -n "$CF_SERVICE_TOKEN" ]]; then
    CF_ARGS+=(-H "CF-Access-Client-Id: $(echo "$CF_SERVICE_TOKEN" | cut -d: -f1)")
    CF_ARGS+=(-H "CF-Access-Client-Secret: $(echo "$CF_SERVICE_TOKEN" | cut -d: -f2)")
    log "Using Cloudflare Access service token."
  else
    log "No CF service token set. Expecting Access challenge (302/403) on protected routes."
  fi

  # /health/live should be accessible (Cloudflare Access typically allows it)
  check "CF health/live" "${CF_URL}/health/live" "${CF_ARGS[@]}"
  check "CF version"     "${CF_URL}/version"     "${CF_ARGS[@]}"

  # Root should return Access challenge (302/403) when no token, or app page with token
  ROOT_CODE="$(curl -fsS --max-time 10 -o /dev/null -w "%{http_code}" "${CF_ARGS[@]}" "${CF_URL}/" 2>/dev/null || echo "000")"
  if [[ -n "$CF_SERVICE_TOKEN" ]]; then
    if [[ "$ROOT_CODE" =~ ^[23] ]]; then
      log "OK:   CF root (service token) [${ROOT_CODE}]"
      PASS=$((PASS + 1))
    else
      log "FAIL: CF root (service token) [${ROOT_CODE}]"
      FAIL=$((FAIL + 1))
    fi
  else
    if [[ "$ROOT_CODE" =~ ^(302|303|307|403|401)$ ]]; then
      log "OK:   CF root gives Access challenge [${ROOT_CODE}] (expected without token)"
      PASS=$((PASS + 1))
    else
      log "WARN: CF root returned ${ROOT_CODE} without a service token. Verify Access policy is active."
    fi
  fi
else
  log ""
  log "Cloudflare-path checks skipped."
  log "Set RETRIEVER_SMOKE_CF_URL=https://retriever.boonegraphics.net to enable them."
  log "Set RETRIEVER_SMOKE_CF_SERVICE_TOKEN=<client-id>:<client-secret> for authenticated checks."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log ""
log "Results: ${PASS} passed, ${FAIL} failed"
if [[ $FAIL -gt 0 ]]; then
  log "SMOKE FAILED"
  exit 1
fi
log "SMOKE PASSED"
