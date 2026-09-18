#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${PROJECT_ROOT}/scripts/load_nas_env.sh"

PYTHON_BIN="${TRADE_PYTHON:-${PROJECT_ROOT}/stock_env/bin/python}"
HOST="${TRADE_API_HOST:-127.0.0.1}"
PORT="${TRADE_API_PORT:-8000}"

cd "${PROJECT_ROOT}"
exec "${PYTHON_BIN}" -m uvicorn apps.api.main:app --reload --host "${HOST}" --port "${PORT}"
