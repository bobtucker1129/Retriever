#!/usr/bin/env bash
# healthcheck.sh -- fast local health check for retriever-rebuild
#
# Usage: /opt/retriever-rebuild/bin/healthcheck.sh
# Exit 0 = healthy, Exit 1 = failed
#
# Hits localhost endpoints only (no Cloudflare path).
# Used by deploy.sh, rollback.sh, and systemd as a post-start check.

set -euo pipefail

BASE_URL="${RETRIEVER_HEALTH_BASE_URL:-http://127.0.0.1:8810}"
MAX_WAIT="${RETRIEVER_HEALTH_MAX_WAIT:-15}"
INTERVAL=2

log() {
  echo "[healthcheck] $*"
}

check_endpoint() {
  local path="$1"
  local label="${2:-$1}"
  local response
  response="$(curl -fsS --max-time 5 "${BASE_URL}${path}" 2>&1)" \
    || { log "FAIL: ${label} -- ${response}"; return 1; }
  log "OK:   ${label}"
}

# ---------------------------------------------------------------------------
# Wait for the process to accept connections
# ---------------------------------------------------------------------------
log "Waiting for service to accept connections on ${BASE_URL} ..."
elapsed=0
until curl -fsS --max-time 3 "${BASE_URL}/health/live" >/dev/null 2>&1; do
  if [[ $elapsed -ge $MAX_WAIT ]]; then
    log "FAIL: Service did not respond within ${MAX_WAIT}s."
    exit 1
  fi
  sleep $INTERVAL
  elapsed=$((elapsed + INTERVAL))
done

# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------
check_endpoint "/health/live"  "health/live"
check_endpoint "/health/ready" "health/ready"
check_endpoint "/version"      "version"

# ---------------------------------------------------------------------------
# Validate health/ready does not report 'failed' for required dependencies
# ---------------------------------------------------------------------------
log "Checking health/ready for failed required dependencies ..."
READY_BODY="$(curl -fsS --max-time 5 "${BASE_URL}/health/ready")"
if echo "$READY_BODY" | grep -q '"failed"'; then
  log "WARNING: /health/ready reports at least one 'failed' dependency:"
  echo "$READY_BODY" | python3 -c "
import sys, json
body = json.load(sys.stdin)
checks = body.get('checks', {})
for name, state in checks.items():
    if state == 'failed':
        print(f'  FAILED: {name}')
" 2>/dev/null || echo "$READY_BODY"
  log "Deployment should be reviewed. Required dependencies are failed."
  exit 1
fi

log "Health check passed."
