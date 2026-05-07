#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${RETRIEVER_SMOKE_BASE_URL:-http://127.0.0.1:8810}"

check() {
  local path="$1"
  curl -fsS "${BASE_URL}${path}" >/dev/null
}

check "/health/live"
check "/health/ready"
check "/version"

echo "Retriever smoke checks passed for ${BASE_URL}"

