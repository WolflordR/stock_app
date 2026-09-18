SHELL := /bin/bash

PROJECT_ROOT := $(CURDIR)
PYTHON_BIN ?= $(PROJECT_ROOT)/stock_env/bin/python
WEB_URL ?= http://127.0.0.1:5173

.PHONY: help api web open update log build check nas-api nas-web

help:
	@echo "Trade Lab commands:"
	@echo "  make api       Start FastAPI backend on 127.0.0.1:8000"
	@echo "  make web       Start React frontend on 127.0.0.1:5173"
	@echo "  make open      Open the web app in your browser"
	@echo "  make update    Run local daily data update now"
	@echo "  make log       Show today's local update log"
	@echo "  make build     Build the React frontend"
	@echo "  make check     Run quick backend/frontend checks"
	@echo "  make nas-api   Start API with NAS-style env"
	@echo "  make nas-web   Start web with NAS-style env"

api:
	TRADE_PYTHON="$(PYTHON_BIN)" scripts/run_api.sh

web:
	scripts/run_web.sh

open:
	open "$(WEB_URL)"

update:
	scripts/run_local_daily_update_now.sh

log:
	@tail -n 160 "logs/local_daily_update/$$(date +%F).log"

build:
	cd apps/web && npm run build

check:
	"$(PYTHON_BIN)" -m py_compile apps/api/main.py apps/api/read_models.py modules/data_sources/price_cache.py apps/worker/daily_update.py
	cd apps/web && npm run build

nas-api:
	TRADE_PYTHON="$(PYTHON_BIN)" scripts/run_api_nas.sh

nas-web:
	scripts/run_web_nas.sh
