#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ENV_FILE="${TRADE_LOCAL_ENV_FILE:-${PROJECT_ROOT}/.env.local}"

if [[ -f "${LOCAL_ENV_FILE}" ]]; then
  set -a
  source "${LOCAL_ENV_FILE}"
  set +a
fi

PYTHON_BIN="${TRADE_PYTHON:-${PROJECT_ROOT}/stock_env/bin/python}"
RUN_DATE="${TRADE_RUN_DATE:-$(date +%F)}"
LOG_DIR="${PROJECT_ROOT}/logs/local_daily_update"
LOG_FILE="${LOG_DIR}/${RUN_DATE}.log"

mkdir -p "${LOG_DIR}"

{
  echo "== Trade local daily update =="
  echo "started_at=$(date '+%Y-%m-%d %H:%M:%S')"
  echo "project_root=${PROJECT_ROOT}"
  echo "run_date=${RUN_DATE}"

  DAILY_ARGS=(--stop-on-error)

  if [[ "${TRADE_DAILY_REFRESH_STOCK_MASTER:-0}" == "1" ]]; then
    DAILY_ARGS+=(--refresh-stock-master)
  fi
  if [[ "${TRADE_DAILY_REFRESH_REVENUE:-0}" == "1" ]]; then
    DAILY_ARGS+=(--refresh-revenue)
  fi
  if [[ "${TRADE_DAILY_REFRESH_COMPANY_LINKS:-0}" == "1" ]]; then
    DAILY_ARGS+=(--refresh-company-links)
  fi
  if [[ "${TRADE_DAILY_REFRESH_MARKET_MAP:-0}" == "1" ]]; then
    DAILY_ARGS+=(--refresh-market-map)
  fi

  if [[ "${TRADE_DAILY_PRICE_SCOPE:-list}" == "all" ]]; then
    DAILY_ARGS+=(--price-all)
  else
    IFS="," read -r -a PRICE_STOCKS <<< "${TRADE_DAILY_PRICE_STOCKS:-}"
    for stock_id in "${PRICE_STOCKS[@]}"; do
      stock_id="$(echo "${stock_id}" | xargs)"
      if [[ -n "${stock_id}" ]]; then
        DAILY_ARGS+=(--price-stock "${stock_id}")
      fi
    done
  fi

  DAILY_ARGS+=(--price-days "${TRADE_DAILY_PRICE_DAYS:-1825}")
  if [[ "${TRADE_DAILY_PRICE_FORCE:-0}" == "1" ]]; then
    DAILY_ARGS+=(--price-force)
  fi

  "${PYTHON_BIN}" -m apps.worker.daily_update "${DAILY_ARGS[@]}"

  if [[ "${TRADE_DAILY_IMPORT_BROKER:-1}" == "1" ]]; then
    BROKER_DIR="${PROJECT_ROOT}/data/raw/broker/twse/${RUN_DATE}"
    if [[ -d "${BROKER_DIR}" ]]; then
      "${PYTHON_BIN}" -m apps.worker.import_broker_csv_folder --date "${RUN_DATE}" --progress-every 100
    else
      echo "broker_import=skipped missing_dir=${BROKER_DIR}"
    fi
  fi

  echo "finished_at=$(date '+%Y-%m-%d %H:%M:%S')"
} >> "${LOG_FILE}" 2>&1
