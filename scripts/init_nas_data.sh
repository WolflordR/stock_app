#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${PROJECT_ROOT}/scripts/load_nas_env.sh"

PYTHON_BIN="${TRADE_PYTHON:-${PROJECT_ROOT}/stock_env/bin/python}"
ARGS=(--target "${TRADE_DATA_DIR}")

if [[ "${TRADE_FORCE_COPY:-0}" == "1" ]]; then
  ARGS+=(--force)
fi

if [[ "${TRADE_COPY_RAW:-1}" == "1" ]]; then
  ARGS+=(--copy-raw)
fi

mkdir -p "${TRADE_NAS_ROOT}" "${TRADE_DATA_DIR}" "${TRADE_LOGS_DIR}" "${TRADE_BACKUPS_DIR}"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/setup_nas_dry_run.py" "${ARGS[@]}"
