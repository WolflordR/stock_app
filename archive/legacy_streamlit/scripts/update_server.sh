#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${PROJECT_ROOT}/data"
BRANCH="${1:-main}"
SESSION_NAME="${TMUX_SESSION_NAME:-trade}"
STREAMLIT_HOST="${STREAMLIT_HOST:-127.0.0.1}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
BACKUP_DIR="${PROJECT_ROOT}/.server_db_backup"

cd "${PROJECT_ROOT}"

CORE_DBS=(
  "data/stocks.db"
  "data/company_links.db"
  "data/market_map.db"
  "data/active_etf_history.db"
)

CACHE_DBS=(
  "data/ui_persistent_cache.db"
  "data/price_cache.db"
  "data/revenue_cache.db"
  "data/chip_cache.db"
)

echo "[1/6] Checking local worktree..."
python3 - <<'PY'
from pathlib import Path
import subprocess
import sys

allowed = {
    "stocks.db",
    "company_links.db",
    "market_map.db",
    "active_etf_history.db",
    "ui_persistent_cache.db",
    "ui_persistent_cache.db-wal",
    "ui_persistent_cache.db-shm",
    "price_cache.db",
    "price_cache.db-wal",
    "price_cache.db-shm",
    "revenue_cache.db",
    "revenue_cache.db-wal",
    "revenue_cache.db-shm",
    "chip_cache.db",
    "chip_cache.db-wal",
    "chip_cache.db-shm",
    "broker_daily_trades.db",
    "broker_daily_trades.db-wal",
    "broker_daily_trades.db-shm",
    "industry_theme_overrides.csv",
    "short_term_broker_tags.csv",
}

result = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=True,
)

unsafe = []
for raw_line in result.stdout.splitlines():
    if not raw_line.strip():
        continue
    path = raw_line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    name = Path(path).name
    if name not in allowed:
        unsafe.append(raw_line)

if unsafe:
    print("Refusing to update because non-database local changes exist:")
    for line in unsafe:
        print(line)
    sys.exit(1)
PY

echo "[2/6] Backing up mutable databases..."
mkdir -p "${BACKUP_DIR}"
for db in "${CORE_DBS[@]}"; do
  if [[ -f "${db}" ]]; then
    mkdir -p "${BACKUP_DIR}/$(dirname "${db}")"
    cp "${db}" "${BACKUP_DIR}/${db}"
  fi
done

echo "[3/6] Cleaning cache sidecar files..."
for db in "${CACHE_DBS[@]}" "${CORE_DBS[@]}"; do
  rm -f "${db}-wal" "${db}-shm"
done

echo "[4/6] Restoring tracked databases before pull..."
git restore --source=HEAD -- "${CORE_DBS[@]}" 2>/dev/null || true

echo "[5/6] Pulling latest code from origin/${BRANCH}..."
git fetch origin "${BRANCH}"
git switch "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

echo "[6/6] Restoring database backups and restarting Streamlit..."
for db in "${CORE_DBS[@]}"; do
  if [[ -f "${BACKUP_DIR}/${db}" ]]; then
    mkdir -p "$(dirname "${db}")"
    cp "${BACKUP_DIR}/${db}" "${db}"
  fi
done

RUN_CMD="cd '${PROJECT_ROOT}' && source stock_env/bin/activate && exec streamlit run main.py --server.port ${STREAMLIT_PORT} --server.address ${STREAMLIT_HOST} --server.headless true"

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  tmux send-keys -t "${SESSION_NAME}" C-c
  sleep 1
  tmux send-keys -t "${SESSION_NAME}" "${RUN_CMD}" C-m
else
  tmux new-session -d -s "${SESSION_NAME}" "${RUN_CMD}"
fi

echo
echo "Server update completed."
echo "Project root : ${PROJECT_ROOT}"
echo "Branch       : ${BRANCH}"
echo "tmux session : ${SESSION_NAME}"
echo "App URL      : http://${STREAMLIT_HOST}:${STREAMLIT_PORT}"
