#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${PROJECT_ROOT}/scripts/load_nas_env.sh"

HOST="${TRADE_WEB_HOST:-127.0.0.1}"
PORT="${TRADE_WEB_PORT:-5173}"

cd "${PROJECT_ROOT}/apps/web"
exec npm run dev -- --host "${HOST}" --port "${PORT}"
