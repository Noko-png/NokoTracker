#!/usr/bin/with-contenv bashio
set -e
umask 077

OPTIONS_FILE=/data/options.json
LOG_LEVEL="$(jq -r '.log_level // "info"' "$OPTIONS_FILE")"
NOKO_ADMIN_USERNAME="$(jq -r '.admin_username // ""' "$OPTIONS_FILE")"
export LOG_LEVEL="${LOG_LEVEL:-info}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////data/noko_tracker.db}"
export NOKO_STATIC_DIR="${NOKO_STATIC_DIR:-/app/frontend}"
export NOKO_AUTH_MODE="ingress"
export NOKO_ADMIN_USERNAME
unset SUPERVISOR_TOKEN

mkdir -p /data/imports

bashio::log.info "Starting NokoTracker on port 8000"

cd /app/backend
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --no-proxy-headers \
    --limit-concurrency 50 \
    --timeout-keep-alive 5
