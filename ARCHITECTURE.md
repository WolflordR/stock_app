# Trade Lab Architecture Notes

## App Entry

- `main.py`
  - Streamlit entrypoint
  - Handles top-level navigation and shared dialogs

## Page Layer

- `app_pages/`
  - `home_page.py`: 首頁
  - `industry_page.py`: 產業輪動頁入口
  - `market_map_page.py`: 產業地圖頁 orchestration only
  - `market_map_page_helpers.py`: 產業地圖 UI helpers、CSS、section renderers
  - `research_page.py`, `news_page.py`, `stock_detail_page.py`, `backtest_page.py`, `active_etf_page.py`

## Market Map Layer

- `market_map_taxonomy.py`
  - 台股題材與大類定義

- `market_map_db.py`
  - `market_map.db` schema setup
  - taxonomy / assignment refresh

- `market_map_queries.py`
  - page bundle assembly
  - topic/group snapshot calculation
  - market quote aggregation

- `market_map_snapshot_store.py`
  - cached snapshot read/write
  - component snapshot normalization

## Legacy / Existing Industry Layer

- `industry_rotation.py`
  - 舊產業輪動主流程

- `industry_page_sections.py`
  - 舊產業頁 UI sections

- `industry_page_helpers.py`
  - 舊產業頁 formatting / shared helpers

- `industry_taxonomy.py`
  - 舊產業分類定義

## Data Sources

- `stock_db.py`
  - 台股主檔與公司資料

- `market_watch.py`
  - TWSE / TPEx quotes

- `revenue_data.py`
  - 月營收資料

- `classification_refresh.py`, `classification_queries.py`
  - 舊分類資料整理與查詢

## Current Refactor Boundaries

- `app_pages/market_map_page.py`
  - should stay thin
  - only coordinate controls, selection state, and helper calls

- `app_pages/market_map_page_helpers.py`
  - owns market map presentation details
  - safe place for future UI polish

- `market_map_queries.py`
  - should not take on snapshot persistence again
  - focus on calculation and bundle assembly

- `market_map_snapshot_store.py`
  - single place for snapshot cache IO

## Next Good Cleanup Targets

1. `ui_backtest_charts.py`
   - very large and likely wants chart-specific helper splitting

2. `industry_rotation.py`
   - likely wants the same orchestration-vs-rendering split now used by market map

3. `industry_taxonomy.py`
   - may benefit from splitting raw taxonomy data from helper logic

4. `main.py`
   - eventually move top nav config into a small registry structure if more pages are added
