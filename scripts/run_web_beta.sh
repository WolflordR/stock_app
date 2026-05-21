#!/usr/bin/env bash
set -euo pipefail

cd /Users/ralph/Desktop/code/trade
exec stock_env/bin/python -m uvicorn web_app.api:app --reload --port 8010
