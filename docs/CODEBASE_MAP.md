# Trade Lab Codebase Map

這份是給共同開發者看的快速導覽。

## 先看哪裡

- 想改主導航或頁面切換：
  - `main.py`

- 想改某一頁的排版、流程、分頁、按鈕：
  - `app_pages/`

- 想改資料抓取、計算邏輯、查詢、快取：
  - `modules/`

- 想改本地資料、快取、匯入檔：
  - `data/`

- 想看部署和工作站更新：
  - `scripts/`
  - `deploy/`

## 主要頁面對照

- 首頁
  - 頁面入口：`app_pages/home_page.py`
  - 資料整理：`modules/home/`
  - 共用 UI / jobs：`modules/ui/`

- 主動 ETF
  - 頁面入口：`app_pages/active_etf_page.py`
  - ETF 邏輯：`modules/etf/`
  - 若牽涉到券商/籌碼/行情：`modules/data_sources/`

- 個股詳頁
  - 頁面入口：`app_pages/stock_detail_page.py`
  - 股票主檔 / 股本 / 法人：`modules/data_sources/stock_db.py`
  - 今日價量 / 日行情：`modules/data_sources/market_watch.py`
  - 券商分點摘要：`modules/data_sources/broker_branch_data.py`
  - 短衝主力分析：`modules/data_sources/broker_branch_short_term.py`
  - 官方券商 CSV 匯入：`modules/data_sources/official_broker_import.py`

- 產業地圖 Beta
  - 頁面入口：`app_pages/market_map_page.py`
  - 頁面輔助：`app_pages/market_map_page_helpers.py`
  - 資料邏輯：`modules/market_map/`

- 舊產業輪動
  - 頁面入口：`app_pages/industry_page.py`
  - 資料邏輯：`modules/industry/`

- 新聞分析
  - 頁面入口：`app_pages/news_page.py`
  - 資料邏輯：`modules/news/`

- 研究工作台
  - 頁面入口：`app_pages/research_page.py`
  - 資料邏輯：`modules/research/`

- 回測 / 選股
  - 頁面入口：`app_pages/backtest_page.py`
  - 資料邏輯：`modules/backtest/`
  - 圖表與 UI：`modules/ui/`

## modules/ 分工地圖

- `modules/core/`
  - 專案共用工具
  - 例如：常數、HTTP、導航、快取、交易日、路徑

- `modules/data_sources/`
  - 原始資料來源層
  - 例如：股票主檔、行情、月營收、籌碼、券商分點

- `modules/home/`
  - 首頁專用資料整理與摘要

- `modules/etf/`
  - 主動 ETF 快照、持股、變動歷史

- `modules/market_map/`
  - 新版產業地圖的 topic / group / company / snapshot

- `modules/industry/`
  - 舊版產業輪動 / 分類系統 / company links

- `modules/news/`
  - 新聞清洗、事件、AI 分析

- `modules/research/`
  - 法說、逐字稿、研究工作台

- `modules/backtest/`
  - 回測策略、績效、選股信號

- `modules/ui/`
  - 共用 UI 組件、背景任務、sidebar、結果視圖

## data/ 放什麼

- `stocks.db`
  - 股票主檔、法人、股本等核心資料

- `company_links.db`
  - 舊題材分類資料

- `market_map.db`
  - 新版產業地圖資料

- `active_etf_history.db`
  - ETF 歷史快照

- `ui_persistent_cache.db`
  - UI 快取

- `broker_daily_trades.db`
  - 官方券商日報匯入資料

- `industry_theme_overrides.csv`
  - 題材覆寫

- `short_term_broker_tags.csv`
  - 短衝 / 隔日沖分點標籤

## 最常見的修改路徑

- 想改「今天這個頁面怎麼長」
  - 先看 `app_pages/...`

- 想改「這個數字怎麼算」
  - 再看對應 `modules/...`

- 想改「資料從哪裡來」
  - 看 `modules/data_sources/...`

- 想改「網站更新腳本」
  - 看 `scripts/update_server.sh`

## 協作建議

- 不要直接把新邏輯塞回 root。
- 新功能先決定 domain，再放進對應 `modules/<domain>/`。
- 頁面檔負責 orchestration，不要把大量商業邏輯塞進 `app_pages/`。
- 需要新資料表或快取時，優先放 `data/`，不要再丟回 root。
