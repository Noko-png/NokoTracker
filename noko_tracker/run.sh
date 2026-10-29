#!/usr/bin/with-contenv bashio
set -e

LOG_LEVEL="$(bashio::config 'log_level')"
export LOG_LEVEL="${LOG_LEVEL:-info}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////data/noko_tracker.db}"
export NOKO_STATIC_DIR="${NOKO_STATIC_DIR:-/app/frontend}"
export NOKO_AUTH_MODE="ingress"
export NOKO_ADMIN_USERNAME="$(bashio::config 'admin_username')"

mkdir -p /data

bashio::log.info "Starting NokoTracker on port 8000"
bashio::log.info "Using database ${DATABASE_URL}"

cd /app/backend
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --no-proxy-headers \
    --limit-concurrency 50 \
    --timeout-keep-alive 5
