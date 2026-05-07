#!/usr/bin/env bash
# deploy.sh -- server-pull deploy for retriever-rebuild
#
# Usage: sudo /opt/retriever-rebuild/bin/deploy.sh <git-ref-or-sha>
# Example: sudo /opt/retriever-rebuild/bin/deploy.sh main
#          sudo /opt/retriever-rebuild/bin/deploy.sh 965a75c
#
# Requires: git, python3, pip, systemctl, curl
# Environment: reads /etc/retriever-rebuild/retriever.env for RETRIEVER_SMOKE_BASE_URL

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
APP_NAME="retriever-rebuild"
APP_BASE="/opt/retriever-rebuild"
APP_RELEASES="${APP_BASE}/releases"
APP_CURRENT="${APP_BASE}/current"
APP_PREVIOUS="${APP_BASE}/previous"
APP_REPO="${APP_BASE}/repo"
APP_SHARED="${APP_BASE}/shared"
APP_BIN="${APP_BASE}/bin"

ENV_FILE="/etc/retriever-rebuild/retriever.env"
LOG_DIR="/var/log/retriever-rebuild"
DEPLOY_LOG="${LOG_DIR}/deploy.log"
LOCK_FILE="/tmp/retriever-deploy.lock"
SERVICE_NAME="retriever-web.service"

GITHUB_REMOTE="https://github.com/bobtucker1129/Retriever.git"

# ---------------------------------------------------------------------------
# Argument
# ---------------------------------------------------------------------------
GIT_REF="${1:-}"
if [[ -z "$GIT_REF" ]]; then
  echo "ERROR: git ref required. Usage: $0 <git-ref-or-sha>" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "[${ts}] $*" | tee -a "${DEPLOY_LOG}"
}

die() {
  log "FATAL: $*"
  exit 1
}

record_deploy() {
  local status="$1"
  local sha="${2:-unknown}"
  local prev="${3:-unknown}"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  cat >> "${DEPLOY_LOG}" <<EOF
---
deployedAt: ${ts}
operator: ${SUDO_USER:-${USER:-unknown}}
gitRef: ${GIT_REF}
gitSha: ${sha}
previousSha: ${prev}
host: $(hostname)
service: ${SERVICE_NAME}
status: ${status}
EOF
}

# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------
exec 200>"${LOCK_FILE}"
flock -n 200 || die "Another deploy is in progress (lock: ${LOCK_FILE}). Aborting."
log "Deploy lock acquired."

CLEANUP_DONE=false
cleanup() {
  if [[ "$CLEANUP_DONE" == "false" ]]; then
    flock -u 200
    log "Deploy lock released."
    CLEANUP_DONE=true
  fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
log "=== Deploy starting: ref=${GIT_REF} ==="

[[ -d "$APP_BASE" ]]     || die "${APP_BASE} does not exist. Run VM setup first."
[[ -d "$APP_RELEASES" ]] || die "${APP_RELEASES} does not exist. Run VM setup first."
[[ -f "$ENV_FILE" ]]     || die "${ENV_FILE} not found. Create production env first."
[[ -d "$LOG_DIR" ]]      || die "${LOG_DIR} does not exist. Run VM setup first."

# ---------------------------------------------------------------------------
# Capture current version for rollback reference
# ---------------------------------------------------------------------------
PREV_SHA="none"
if [[ -L "$APP_CURRENT" ]]; then
  PREV_SHA="$(basename "$(readlink "$APP_CURRENT")")"
  log "Current release: ${PREV_SHA}"
fi

# ---------------------------------------------------------------------------
# Fetch source
# ---------------------------------------------------------------------------
log "Fetching from ${GITHUB_REMOTE} ..."
if [[ -d "${APP_REPO}/.git" ]]; then
  git -C "$APP_REPO" fetch --tags origin
else
  log "Cloning repo to ${APP_REPO} ..."
  git clone "$GITHUB_REMOTE" "$APP_REPO"
fi

# Resolve requested ref to a full SHA
FULL_SHA="$(git -C "$APP_REPO" rev-parse --verify "${GIT_REF}^{commit}" 2>/dev/null)" \
  || die "Could not resolve ref '${GIT_REF}' to a commit in ${APP_REPO}."
log "Resolved ${GIT_REF} -> ${FULL_SHA}"

RELEASE_DIR="${APP_RELEASES}/${FULL_SHA}"

if [[ -d "$RELEASE_DIR" ]]; then
  log "Release directory ${RELEASE_DIR} already exists. Re-using."
else
  # ---------------------------------------------------------------------------
  # Create immutable release directory
  # ---------------------------------------------------------------------------
  log "Creating release directory ${RELEASE_DIR} ..."
  mkdir -p "$RELEASE_DIR"
  git -C "$APP_REPO" --work-tree="$RELEASE_DIR" checkout "$FULL_SHA" -- .
  log "Source checked out."

  # Stamp version metadata
  cat > "${RELEASE_DIR}/.release-meta" <<EOF
gitSha=${FULL_SHA}
gitRef=${GIT_REF}
builtAt=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
operator=${SUDO_USER:-${USER:-unknown}}
EOF

  # ---------------------------------------------------------------------------
  # Install dependencies reproducibly
  # ---------------------------------------------------------------------------
  log "Installing Python dependencies ..."
  python3 -m venv "${RELEASE_DIR}/.venv"
  "${RELEASE_DIR}/.venv/bin/pip" install --quiet --upgrade pip
  "${RELEASE_DIR}/.venv/bin/pip" install --quiet -r "${RELEASE_DIR}/requirements.txt" \
    || die "pip install failed."
  log "Dependencies installed."

  # ---------------------------------------------------------------------------
  # Import check (fast build verification)
  # ---------------------------------------------------------------------------
  log "Running import check ..."
  cd "$RELEASE_DIR"
  PYTHONPATH="." "${RELEASE_DIR}/.venv/bin/python" -c "from app.main import app" \
    || die "Import check failed. Release is broken."
  log "Import check passed."

  # ---------------------------------------------------------------------------
  # Tests
  # ---------------------------------------------------------------------------
  log "Running test suite ..."
  PYTHONPATH="." "${RELEASE_DIR}/.venv/bin/python" -m pytest tests/ -q --tb=short \
    || die "Tests failed. Aborting deploy."
  log "Tests passed."
fi

# ---------------------------------------------------------------------------
# Config validation (no secret printing)
# ---------------------------------------------------------------------------
log "Validating production config ..."
cd "$RELEASE_DIR"
set -a; source "$ENV_FILE"; set +a
"${RELEASE_DIR}/.venv/bin/python" -c "
from app.config import get_settings, format_config_error
from pydantic import ValidationError
try:
    s = get_settings()
    print('Config OK: env=' + str(s.retriever_env))
except (ValidationError, ValueError) as e:
    print('Config ERROR: ' + format_config_error(e))
    raise SystemExit(1)
" || die "Config validation failed. Fix /etc/retriever-rebuild/retriever.env before deploying."
log "Config validation passed."

# ---------------------------------------------------------------------------
# Migrations (only when explicitly approved via env flag)
# ---------------------------------------------------------------------------
if [[ "${RETRIEVER_RUN_MIGRATIONS:-false}" == "true" ]]; then
  log "Running database migrations (RETRIEVER_RUN_MIGRATIONS=true) ..."
  cd "$RELEASE_DIR"
  set -a; source "$ENV_FILE"; set +a
  "${RELEASE_DIR}/.venv/bin/python" -c "
from app.db.connection import get_db_connection
from app.db.migrations import run_migrations_and_seeds
import asyncio, os
async def main():
    conn = await get_db_connection()
    await run_migrations_and_seeds(conn)
    await conn.close()
asyncio.run(main())
" || die "Migrations failed."
  log "Migrations complete."
else
  log "Skipping migrations (set RETRIEVER_RUN_MIGRATIONS=true to run on next deploy)."
fi

# ---------------------------------------------------------------------------
# Swap symlinks
# ---------------------------------------------------------------------------
log "Swapping release symlinks ..."
if [[ -L "$APP_CURRENT" ]]; then
  CURRENT_TARGET="$(readlink "$APP_CURRENT")"
  ln -sfn "$CURRENT_TARGET" "$APP_PREVIOUS"
  log "previous -> ${CURRENT_TARGET}"
fi
ln -sfn "$RELEASE_DIR" "$APP_CURRENT"
log "current -> ${RELEASE_DIR}"

# Stamp deployed_at
echo "deployedAt=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "${RELEASE_DIR}/.release-meta"

# ---------------------------------------------------------------------------
# Restart service
# ---------------------------------------------------------------------------
log "Restarting ${SERVICE_NAME} ..."
systemctl restart "$SERVICE_NAME" \
  || { record_deploy "service-restart-failed" "$FULL_SHA" "$PREV_SHA"; die "systemctl restart failed."; }
sleep 2
systemctl is-active --quiet "$SERVICE_NAME" \
  || { record_deploy "service-not-active" "$FULL_SHA" "$PREV_SHA"; die "Service is not active after restart."; }
log "Service restarted and active."

# ---------------------------------------------------------------------------
# Post-deploy health and smoke checks
# ---------------------------------------------------------------------------
log "Running post-deploy health checks ..."
"${APP_BIN}/healthcheck.sh" \
  || { record_deploy "healthcheck-failed" "$FULL_SHA" "$PREV_SHA"; _auto_rollback "$FULL_SHA" "$PREV_SHA"; }

log "Running smoke checks ..."
"${APP_BIN}/smoke.sh" \
  || { record_deploy "smoke-failed" "$FULL_SHA" "$PREV_SHA"; _auto_rollback "$FULL_SHA" "$PREV_SHA"; }

# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------
record_deploy "success" "$FULL_SHA" "$PREV_SHA"
log "=== Deploy complete: ${FULL_SHA} ==="

# ---------------------------------------------------------------------------
# Auto-rollback helper (only called on post-deploy failure)
# ---------------------------------------------------------------------------
_auto_rollback() {
  local failed_sha="${1:-unknown}"
  local restore_sha="${2:-}"
  log "Post-deploy check failed on ${failed_sha}. Attempting automatic rollback ..."
  if [[ -n "$restore_sha" && -d "${APP_RELEASES}/${restore_sha}" ]]; then
    ln -sfn "${APP_RELEASES}/${restore_sha}" "$APP_CURRENT"
    systemctl restart "$SERVICE_NAME" && log "Rolled back to ${restore_sha}." \
      || log "WARNING: Rollback service restart also failed. Manual intervention required."
  else
    log "WARNING: No previous release to roll back to. Manual intervention required."
  fi
  record_deploy "auto-rolled-back" "$failed_sha" "$restore_sha"
  die "Deployment failed. Auto-rollback attempted. Check ${DEPLOY_LOG} and journalctl -u ${SERVICE_NAME}."
}
