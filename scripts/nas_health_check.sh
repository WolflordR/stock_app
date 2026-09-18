#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${PROJECT_ROOT}/scripts/load_nas_env.sh"

WEB_HOST="${TRADE_WEB_HOST:-127.0.0.1}"
WEB_PORT="${TRADE_WEB_PORT:-8080}"
API_HOST="${TRADE_API_HOST:-127.0.0.1}"
API_PORT="${TRADE_API_PORT:-8000}"

curl -fsS "http://${WEB_HOST}:${WEB_PORT}/health" >/dev/null
curl -fsS "http://${WEB_HOST}:${WEB_PORT}/api/data/sources" >/dev/null
curl -fsS "http://${API_HOST}:${API_PORT}/health" >/dev/null

echo "NAS deployment health check passed:"
echo "- web: http://${WEB_HOST}:${WEB_PORT}"
echo "- api: http://${API_HOST}:${API_PORT}"
