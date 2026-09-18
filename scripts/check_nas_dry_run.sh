#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${PROJECT_ROOT}/scripts/load_nas_env.sh"

PYTHON_BIN="${TRADE_PYTHON:-${PROJECT_ROOT}/stock_env/bin/python}"

"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/setup_nas_dry_run.py" --target "${TRADE_DATA_DIR}" --force
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/check_data_paths.py"
"${PYTHON_BIN}" -c "from apps.api.read_models import build_stock_overview, list_strong_stocks, list_revenue_momentum, list_active_etf_snapshots; stock=build_stock_overview('2330'); strong=list_strong_stocks(days=7, limit=3); revenue=list_revenue_momentum(limit=3); etf=list_active_etf_snapshots(limit=3, days=30); print({'stock_found': stock['found'], 'quote_rows': len(stock['quotes']), 'institutional_rows': len(stock['institutional_trading']), 'strong_rows': strong['summary']['returned_count'], 'revenue_rows': len(revenue['rows']), 'etf_rows': len(etf['rows'])})"
