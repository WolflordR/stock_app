#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/trade-app}"
APP_USER="${APP_USER:-tradeapp}"
APP_GROUP="${APP_GROUP:-tradeapp}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-trade-app}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/stock_env/bin/python}"
PIP_BIN="${PIP_BIN:-$APP_DIR/stock_env/bin/pip}"

echo "[1/5] Enter app directory: $APP_DIR"
cd "$APP_DIR"

if [ -d .git ]; then
  echo "[2/5] Pull latest code from branch: $BRANCH"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  echo "This directory is not a git repository: $APP_DIR" >&2
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python virtualenv not found at: $PYTHON_BIN" >&2
  exit 1
fi

echo "[3/5] Install/update Python dependencies"
"$PIP_BIN" install -r requirements.txt

echo "[4/5] Fix ownership"
sudo chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"

echo "[5/5] Restart service: $SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager

echo "Deployment finished."
