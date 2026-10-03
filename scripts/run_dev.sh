#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${TRADE_PYTHON:-${PROJECT_ROOT}/stock_env/bin/python}"
API_HOST="${TRADE_API_HOST:-127.0.0.1}"
API_PORT="${TRADE_API_PORT:-8000}"
WEB_HOST="${TRADE_WEB_HOST:-127.0.0.1}"
WEB_PORT="${TRADE_WEB_PORT:-5173}"

cd "${PROJECT_ROOT}"

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "${API_PID}" 2>/dev/null || true
  fi
  if [[ -n "${WEB_PID:-}" ]]; then
    kill "${WEB_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"${PYTHON_BIN}" -m uvicorn apps.api.main:app --reload --host "${API_HOST}" --port "${API_PORT}" &
API_PID=$!

cd "${PROJECT_ROOT}/apps/web"
npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}" &
WEB_PID=$!

echo "API: http://${API_HOST}:${API_PORT}"
echo "Web: http://${WEB_HOST}:${WEB_PORT}"
while kill -0 "${API_PID}" 2>/dev/null && kill -0 "${WEB_PID}" 2>/dev/null; do
  sleep 1
done
