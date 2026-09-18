# Trade Lab Deployment Guide

Trade Lab 的正式方向是 React web + FastAPI API + worker，NAS 負責保存資料庫、快取、log 與備份。舊 Streamlit UI 已移到 `archive/legacy_streamlit/`，只保留為參考。

## Recommended architecture

1. Keep the code in a fixed directory such as `/opt/trade-app`
2. Keep market data under a NAS folder, for example `/volume1/trade/data`
3. Run FastAPI as the internal API service
4. Serve the React build with nginx, Docker, or NAS web station
5. Run crawler / backup jobs separately as worker tasks
6. Restrict access to your LAN, VPN, or reverse proxy authentication

## 1. Prepare the workstation

Create a service user:

```bash
sudo useradd --system --create-home --shell /bin/bash tradeapp
```

Clone the project:

```bash
sudo mkdir -p /opt/trade-app
sudo chown -R $USER:$USER /opt/trade-app
git clone <YOUR_GIT_REPO_URL> /opt/trade-app
cd /opt/trade-app
```

Create the virtual environment and install dependencies:

```bash
python3 -m venv stock_env
stock_env/bin/pip install --upgrade pip
stock_env/bin/pip install -r requirements.txt
```

If you use local Ollama on the workstation, install and start it separately.

## 2. NAS data configuration

Copy the example NAS env file:

```bash
cp .env.nas.example .env.nas
```

Edit `.env.nas`:

```bash
TRADE_NAS_ROOT=/volume1/trade
TRADE_DATA_DIR=${TRADE_NAS_ROOT}/data
TRADE_DB_DIR=${TRADE_NAS_ROOT}/data/db
TRADE_RAW_DATA_DIR=${TRADE_NAS_ROOT}/data/raw
TRADE_LOGS_DIR=${TRADE_NAS_ROOT}/logs
TRADE_BACKUPS_DIR=${TRADE_NAS_ROOT}/backups
```

Prepare the NAS folder and copy current local data:

```bash
scripts/init_nas_data.sh
```

By default this keeps existing NAS files. To overwrite with current local files:

```bash
TRADE_FORCE_COPY=1 scripts/init_nas_data.sh
```

Prepare and verify a local NAS-like folder:

```bash
scripts/check_nas_dry_run.sh
```

For real NAS deployment, use your mounted NAS path instead of `/private/tmp/trade_nas`.

## 3. Run API and web locally against NAS data

Start API:

```bash
scripts/run_api_nas.sh
```

Start web in another terminal:

```bash
scripts/run_web_nas.sh
```

Open:

```text
http://127.0.0.1:5173
```

## 4. Docker Compose on NAS / Linux

The compose file is under `infra/docker-compose.yml`:

```bash
scripts/nas_compose_up.sh
scripts/nas_health_check.sh
```

It mounts:

```text
${TRADE_NAS_ROOT}/data   -> /trade/data
${TRADE_NAS_ROOT}/logs   -> /trade/logs
${TRADE_NAS_ROOT}/backups -> /trade/backups
```

Inside containers, DB files live under `/trade/data/db`.

The site opens at:

```text
http://<NAS-IP>:8080
```

The API health endpoint is:

```text
http://<NAS-IP>:8000/health
```

## 5. Useful commands

Check current data paths:

```bash
scripts/check_nas_dry_run.sh
```

Build web:

```bash
cd apps/web
npm run build
```

Run API health check:

```bash
curl http://127.0.0.1:8000/health
```

Import manually downloaded broker branch CSV files:

```bash
python -m apps.worker.import_broker_csv_folder --date 2026-09-04
```

## 6. Security notes

At minimum, use one of these:

- Internal LAN only
- VPN only
- Reverse proxy basic auth
- Company SSO or access gateway

If you later want HTTPS:

- add an internal certificate
- or use a reverse proxy such as Caddy or nginx with TLS
