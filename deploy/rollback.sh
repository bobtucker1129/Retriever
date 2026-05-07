#!/usr/bin/env bash
# rollback.sh -- revert retriever-rebuild to the previous release
#
# Usage: sudo /opt/retriever-rebuild/bin/rollback.sh [reason]
# Example: sudo /opt/retriever-rebuild/bin/rollback.sh "health check failure after deploy"
#
# Does NOT require Cursor, GitHub, or package installation.
# Works entirely from releases already on disk.

set -euo pipefail

APP_BASE="/opt/retriever-rebuild"
APP_CURRENT="${APP_BASE}/current"
APP_PREVIOUS="${APP_BASE}/previous"
APP_BIN="${APP_BASE}/bin"
LOG_DIR="/var/log/retriever-rebuild"
DEPLOY_LOG="${LOG_DIR}/deploy.log"
SERVICE_NAME="retriever-web.service"
LOCK_FILE="/tmp/retriever-deploy.lock"

REASON="${1:-manual rollback}"

log() {
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "[${ts}] $*" | tee -a "${DEPLOY_LOG}"
}

die() {
  log "FATAL: $*"
  exit 1
}

# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------
exec 200>"${LOCK_FILE}"
flock -n 200 || die "A deploy or rollback is already in progress. Aborting."

CLEANUP_DONE=false
cleanup() {
  if [[ "$CLEANUP_DONE" == "false" ]]; then
    flock -u 200
    CLEANUP_DONE=true
  fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
[[ -L "$APP_PREVIOUS" ]] || die "No previous release found at ${APP_PREVIOUS}. Cannot roll back."
[[ -L "$APP_CURRENT" ]]  || die "No current release found at ${APP_CURRENT}. Cannot roll back."

CURRENT_TARGET="$(readlink "$APP_CURRENT")"
PREVIOUS_TARGET="$(readlink "$APP_PREVIOUS")"
CURRENT_SHA="$(basename "$CURRENT_TARGET")"
PREVIOUS_SHA="$(basename "$PREVIOUS_TARGET")"

[[ -d "$PREVIOUS_TARGET" ]] || die "Previous release directory ${PREVIOUS_TARGET} does not exist on disk."
[[ "$CURRENT_SHA" != "$PREVIOUS_SHA" ]] \
  || die "current (${CURRENT_SHA}) and previous (${PREVIOUS_SHA}) point to the same release. Nothing to roll back."

log "=== Rollback starting ==="
log "Current: ${CURRENT_SHA}"
log "Restoring: ${PREVIOUS_SHA}"
log "Reason: ${REASON}"

# ---------------------------------------------------------------------------
# Swap symlinks
# ---------------------------------------------------------------------------
ln -sfn "$CURRENT_TARGET" "$APP_PREVIOUS"
ln -sfn "$PREVIOUS_TARGET" "$APP_CURRENT"
log "current -> ${PREVIOUS_TARGET}"
log "previous -> ${CURRENT_TARGET}"

# ---------------------------------------------------------------------------
# Restart service
# ---------------------------------------------------------------------------
log "Restarting ${SERVICE_NAME} ..."
systemctl restart "$SERVICE_NAME" \
  || die "systemctl restart failed. Release symlinks have been swapped. Inspect manually."
sleep 2
systemctl is-active --quiet "$SERVICE_NAME" \
  || die "Service is not active after rollback restart. Inspect with: journalctl -u ${SERVICE_NAME} -n 50"
log "Service restarted."

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
log "Running health check ..."
"${APP_BIN}/healthcheck.sh" || die "Health check failed after rollback. Inspect manually."

# ---------------------------------------------------------------------------
# Smoke check
# ---------------------------------------------------------------------------
log "Running smoke check ..."
"${APP_BIN}/smoke.sh" || die "Smoke check failed after rollback. Inspect manually."

# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------
local ts
ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
cat >> "${DEPLOY_LOG}" <<EOF
---
rolledBackAt: ${ts}
operator: ${SUDO_USER:-${USER:-unknown}}
restoredSha: ${PREVIOUS_SHA}
replacedSha: ${CURRENT_SHA}
host: $(hostname)
service: ${SERVICE_NAME}
reason: ${REASON}
status: success
EOF

log "=== Rollback complete: restored ${PREVIOUS_SHA} ==="
