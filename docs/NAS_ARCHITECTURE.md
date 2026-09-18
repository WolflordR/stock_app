# NAS Architecture Plan

這份文件定下第一階段的穩定地基：NAS 負責資料、排程與部署；程式切成 worker、API、web。舊 Streamlit UI 已移到 `archive/legacy_streamlit/`，只保留為參考。

## Target Roles

- `worker`
  - 爬蟲、官方 CSV 匯入、資料清洗、DB 更新、備份。
  - 第一階段可以用 Python scripts + cron / NAS 排程。

- `api`
  - FastAPI 後端。
  - 只透過 repositories / services 讀資料，不直接爬蟲。

- `web`
  - Next.js / React 正式網站。
  - 只呼叫 API，不直接讀 NAS 檔案。

## NAS Directory Layout

建議 NAS 上固定放在：

```text
/volume1/trade/
├── data/
│   ├── db/
│   ├── raw/
│   ├── processed/
│   ├── cache/
│   └── ...
├── logs/
├── backups/
└── apps/
```

本機開發可以繼續用專案內的 `data/`。部署到 NAS 時，用環境變數切換。

## Environment Variables

最重要的是：

```text
TRADE_NAS_ROOT=/volume1/trade
TRADE_DATA_DIR=/volume1/trade/data
```

可選設定：

```text
TRADE_RAW_DATA_DIR=/volume1/trade/data/raw
TRADE_PROCESSED_DATA_DIR=/volume1/trade/data/processed
TRADE_DB_DIR=/volume1/trade/data/db
TRADE_CACHE_DIR=/volume1/trade/data/cache
TRADE_LOGS_DIR=/volume1/trade/logs
TRADE_BACKUPS_DIR=/volume1/trade/backups
```

所有正式程式都透過 `modules.core.project_paths` 讀取資料路徑，會依照 `TRADE_DATA_DIR` 指到 NAS 或本機。

## Data Flow

```text
worker
  -> raw data
  -> processed data
  -> database
  -> api
  -> web
```

原始資料要留在 `raw/`，清洗後資料放 `processed/`，可重建快取放 `cache/`。

## Migration Order

1. 統一資料路徑：所有資料路徑從 `modules.core.project_paths` 取得。
2. 建立 FastAPI：先做 `/health` 與少量 read-only API。
3. 建立 Vite React web：先做架構主控台，再搬首頁與個股頁。
4. 建立 worker 指令：把爬蟲、匯入、更新任務獨立出來。
5. 舊 Streamlit UI 已封存，不再新增功能。

## Page Migration Backlog

新功能統一做在 React/API/worker，不再修改舊 Streamlit UI。

1. `Dashboard`
   - 目前已建立第一版。
   - 來源：`/api/dashboard/overview`

2. `Stock Detail`
   - 先搬股票主檔、價量摘要、券商分點摘要。
   - API 拆成 `/api/stocks/{stock_id}`、`/api/stocks/{stock_id}/quotes`、`/api/stocks/{stock_id}/brokers`。

3. `Market Map`
   - 先搬 group/topic/member read-only table。
   - API 拆成 `/api/market-map/status`、`/api/market-map/groups`、`/api/market-map/topics`。

4. `Active ETF`
   - 第一版已搬快照結果與成分異動查詢，不讓前端直接觸發外部抓取。
   - worker 負責更新，API 只讀取最新資料。

5. `Backtest`
   - 第一版已搬小範圍背景 job、進度輪詢與策略設定。
   - job 狀態落在 `api_jobs.db`，避免 API reload 後查不到任務。

6. `Research`
   - 第一版已搬公司題材資料庫搜尋。
   - 後續再接候選股掃描與法說會 transcript 工作流。

7. `News`
   - 第一版已搬背景 job 啟動與狀態輪詢。
   - 外部新聞來源較慢時不阻塞網站主流程。

## Local Web Development

啟動 API：

```bash
scripts/run_api.sh
```

啟動前端：

```bash
scripts/run_web.sh
```

開發時 Vite 會把 `/api` proxy 到 `127.0.0.1:8000`。

## NAS Dry Run

先在本機建立一個像 NAS 的資料目錄：

```bash
scripts/setup_nas_dry_run.py --target /private/tmp/trade_nas --force
```

檢查程式是否真的讀到 dry-run 路徑：

```bash
TRADE_NAS_ENV_FILE=.env.nas.example scripts/check_nas_dry_run.sh
```

用 dry-run 資料啟動 API：

```bash
scripts/run_api_nas.sh
```

另一個終端機啟動 web：

```bash
scripts/run_web_nas.sh
```

真的搬到 NAS 時，複製 `.env.nas.example` 成 `.env.nas`，把 `TRADE_NAS_ROOT` 改成你的 NAS 專案根目錄，例如 `/Volumes/trade` 或 `/volume1/trade`。

## NAS Web Deployment

第一版用 Docker Compose：

```bash
cd infra
TRADE_NAS_ROOT=/volume1/trade docker compose up -d --build
```

或使用專案腳本：

```bash
scripts/init_nas_data.sh
scripts/nas_compose_up.sh
scripts/nas_health_check.sh
```

預設：

- `web`: NAS port `8080`
- `api`: NAS port `8000`
- `worker`: 用 profile 保留給手動工具或排程

`api_jobs.db` 會放在 `TRADE_DB_DIR`，記錄 web 觸發的背景任務狀態。這個檔案會被資料檢查與備份流程納入。

## First Verification

本機檢查：

```bash
python scripts/check_data_paths.py
```

模擬 NAS 路徑：

```bash
TRADE_DATA_DIR=/volume1/trade/data python scripts/check_data_paths.py
```

備份目前設定的 DB：

```bash
python -m apps.worker.backup_databases --label manual
```

更新指定股票價格快取：

```bash
python -m apps.worker.update_price_cache --stock 2330 --days 180
```

先前抓取失敗時，快取會短時間保護避免一直重試。確認網路正常後可強制重抓：

```bash
python -m apps.worker.update_price_cache --stock 2330 --days 180 --force
```

每日總控 dry-run：

```bash
python -m apps.worker.daily_update --dry-run
```

保守每日排程，只備份並記錄目前資料狀態：

```bash
python -m apps.worker.daily_update
```

若每日排程要一起強制重抓指定股票價格：

```bash
python -m apps.worker.daily_update --price-stock 2330 --price-days 180 --price-force
```

每日下載券商分點 CSV 後，匯入指定日期：

```bash
python -m apps.worker.import_broker_csv_folder --date 2026-09-04
```
