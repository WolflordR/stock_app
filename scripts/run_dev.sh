#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${TRADE_PYTHON:-${PROJECT_ROOT}/stock_env/bin/python}"
API_HOST="${TRADE_API_HOST:-127.0.0.1}"
API_PORT="${TRADE_API_PORT:-8000}"
WEB_HOST="${TRADE_WEB_HOST:-127.0.0.1}"
WEB_PORT="${TRADE_WEB_PORT:-5173}"

cd "${PROJECT_ROOT}"

api_running() {
  curl -fsS -m 2 "http://${API_HOST}:${API_PORT}/health" >/dev/null 2>&1
}

web_running() {
  curl -fsS -m 2 "http://${WEB_HOST}:${WEB_PORT}/" >/dev/null 2>&1
}

STARTED_PIDS=()

cleanup() {
  for pid in "${STARTED_PIDS[@]:-}"; do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

if api_running; then
  echo "API already running: http://${API_HOST}:${API_PORT}"
else
  "${PYTHON_BIN}" -m uvicorn apps.api.main:app --reload --host "${API_HOST}" --port "${API_PORT}" &
  API_PID=$!
  STARTED_PIDS+=("${API_PID}")
fi

if web_running; then
  echo "Web already running: http://${WEB_HOST}:${WEB_PORT}"
else
  (
    cd "${PROJECT_ROOT}/apps/web"
    exec npx vite --host "${WEB_HOST}" --port "${WEB_PORT}"
  ) &
  WEB_PID=$!
  STARTED_PIDS+=("${WEB_PID}")
fi

echo "API: http://${API_HOST}:${API_PORT}"
echo "Web: http://${WEB_HOST}:${WEB_PORT}"

if [[ "${#STARTED_PIDS[@]}" -eq 0 ]]; then
  echo "Both services are already running."
  exit 0
fi

while true; do
  for pid in "${STARTED_PIDS[@]}"; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      exit 1
    fi
  done
  sleep 1
done
