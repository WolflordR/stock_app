#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${TRADE_NAS_ENV_FILE:-${PROJECT_ROOT}/.env.nas}"

if [[ ! -f "${ENV_FILE}" ]]; then
  ENV_FILE="${PROJECT_ROOT}/.env.nas.example"
fi

set -a
source "${ENV_FILE}"
set +a

export TRADE_NAS_ROOT="${TRADE_NAS_ROOT:-/private/tmp/trade_nas}"
export TRADE_DATA_DIR="${TRADE_DATA_DIR:-${TRADE_NAS_ROOT}/data}"
export TRADE_DB_DIR="${TRADE_DB_DIR:-${TRADE_DATA_DIR}/db}"
export TRADE_RAW_DATA_DIR="${TRADE_RAW_DATA_DIR:-${TRADE_DATA_DIR}/raw}"
export TRADE_PROCESSED_DATA_DIR="${TRADE_PROCESSED_DATA_DIR:-${TRADE_DATA_DIR}/processed}"
export TRADE_CACHE_DIR="${TRADE_CACHE_DIR:-${TRADE_DATA_DIR}/cache}"
export TRADE_LOGS_DIR="${TRADE_LOGS_DIR:-${TRADE_NAS_ROOT}/logs}"
export TRADE_BACKUPS_DIR="${TRADE_BACKUPS_DIR:-${TRADE_NAS_ROOT}/backups}"
