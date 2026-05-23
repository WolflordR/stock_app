# Trade Lab Architecture Notes

## Editing Rule

- `main.py`
  - Streamlit app entrypoint
  - 負責主導航和頁面切換

- `app_pages/`
  - 頁面入口與 orchestration
  - 想改頁面流程、版面組裝、頁面級互動，先看這裡

- `modules/`
  - 真正的功能實作本體
  - 想改資料整理、查詢、業務邏輯、共用 UI，優先改這裡

## Current Structure

### App Entry

- `main.py`

### Page Layer

- `app_pages/home_page.py`
- `app_pages/industry_page.py`
- `app_pages/market_map_page.py`
- `app_pages/market_map_page_helpers.py`
- `app_pages/research_page.py`
- `app_pages/news_page.py`
- `app_pages/stock_detail_page.py`
- `app_pages/backtest_page.py`
- `app_pages/active_etf_page.py`

### Module Layer

- `modules/core/`
  - `app_constants.py`
  - `http_utils.py`
  - `internal_nav.py`
  - `persistent_cache.py`
  - `project_paths.py`
  - `trading_calendar.py`

- `modules/data_sources/`
  - `stock_db.py`
  - `market_watch.py`
  - `revenue_data.py`
  - `broker_branch_data.py`
  - `official_broker_import.py`
  - `chip_data.py`
  - `price_cache.py`

- `modules/home/`
  - `home_page_data.py`
  - `home_page_sections.py`
  - `homepage_brief.py`

- `modules/etf/`
  - `active_etf_watch.py`
  - `active_etf_history_store.py`

- `modules/market_map/`
  - `market_map_db.py`
  - `market_map_events.py`
  - `market_map_queries.py`
  - `market_map_snapshot_store.py`
  - `market_map_taxonomy.py`
  - `market_map_value_chain.py`

- `modules/industry/`
  - `industry_rotation.py`
  - `industry_page_helpers.py`
  - `industry_page_sections.py`
  - `industry_taxonomy.py`
  - `industry_utils.py`
  - `classification_refresh.py`
  - `classification_queries.py`
  - `classification_exports.py`
  - `company_links_db.py`

- `modules/news/`
  - `news_ai.py`
  - `news_analysis.py`
  - `news_common.py`
  - `news_events.py`
  - `news_market.py`

- `modules/research/`
  - `research_*`
  - `transcript_*`

- `modules/backtest/`
  - `backtest_*`
  - `strategy_*`
  - `performance_metrics.py`
  - `bowl_scoring.py`
  - `func.py`

- `modules/ui/`
  - `ui_*`

## Root Now Intentionally Small

repo root 現在主要只留：

- app 入口：`main.py`
- 頁面資料夾：`app_pages/`
- 功能模組：`modules/`
- 部署 / 腳本 / web beta：`deploy/`, `scripts/`, `web_app/`
- 文件與設定：`docs/`, `.streamlit/`
- 資料與快取：`data/`

## Documents

- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`
- `docs/DEPLOYMENT.md`
- `docs/FIX_BACKLOG.md`

這樣多人協作時，不需要再從 root 滿滿同名檔案裡猜哪個才是真的實作。

## Collaboration Guidance

- 想改 ETF：
  - 頁面流程看 `app_pages/active_etf_page.py`
  - 資料邏輯看 `modules/etf/`

- 想改首頁：
  - `app_pages/home_page.py`
  - `modules/home/`
  - `modules/ui/`

- 想改產業地圖：
  - 頁面流程看 `app_pages/market_map_page.py`
  - UI 細節看 `app_pages/market_map_page_helpers.py`
  - 資料邏輯看 `modules/market_map/`

- 想改舊產業輪動：
  - `app_pages/industry_page.py`
  - `modules/industry/`

- 想改研究 / transcript：
  - `app_pages/research_page.py`
  - `modules/research/`

- 想改回測：
  - `app_pages/backtest_page.py`
  - `modules/backtest/`

- 想改共用資料來源：
  - `modules/data_sources/`

- 想改共用工具與導航：
  - `modules/core/`
