# Trade Lab Architecture

Trade Lab 的正式架構已改為 React + FastAPI + worker。舊 Streamlit UI 已移到 `archive/legacy_streamlit/`，只保留做歷史參考。

## Runtime Apps

- `apps/web/`
  - Vite React + TypeScript 正式網站。
  - 負責頁面、表格、K 線圖與互動。
  - 只透過 HTTP API 取資料，不直接讀 DB 或 NAS 檔案。

- `apps/api/`
  - FastAPI 後端。
  - 對前端提供 `/api/...` read API 與背景任務啟動/查詢 API。
  - 讀取 SQLite DB 和整理好的資料檔。

- `apps/worker/`
  - NAS 或本機排程執行的資料任務。
  - 負責股價快取、券商分點 CSV 匯入、資料更新、備份。

## Shared Modules

- `modules/core/`
  - 設定、路徑、job store、job manager、HTTP helper。

- `modules/data_sources/`
  - 股票主檔、價格快取、法人資料、券商分點、ETF、營收等資料來源。

- `modules/backtest/`
  - 選股與回測邏輯。

- `modules/industry/`, `modules/market_map/`, `modules/news/`, `modules/research/`
  - 可重用的資料整理、分類、新聞與研究邏輯。

- `packages/`
  - 跨 app 共用的資料檔清單與未來 domain package。

## Data Layout

NAS 上建議使用：

```text
/volume1/trade/
  data/
    db/
    raw/
    processed/
    cache/
  logs/
  backups/
```

程式透過環境變數切換本機或 NAS：

```text
TRADE_NAS_ROOT=/volume1/trade
TRADE_DATA_DIR=/volume1/trade/data
TRADE_DB_DIR=/volume1/trade/data/db
TRADE_RAW_DATA_DIR=/volume1/trade/data/raw
```

## Data Flow

```text
worker -> raw/processed/cache/db -> FastAPI -> React web
```

API 原則上負責讀資料；worker 是主要寫入者。這樣 SQLite 放在 NAS 上會比較穩。

## Development

Local development:

```bash
make api
make web
```

NAS-style local test:

```bash
TRADE_NAS_ENV_FILE=.env.nas.example scripts/check_nas_dry_run.sh
```

Docker/NAS deployment:

```bash
scripts/init_nas_data.sh
scripts/nas_compose_up.sh
scripts/nas_health_check.sh
```

## Legacy Code

舊 Streamlit UI 放在：

```text
archive/legacy_streamlit/
```

這些檔案不再參與正式部署，也不應該被新功能引用。若要找舊版頁面行為，可從 archive 讀設計與流程，再搬成 React/API 實作。
