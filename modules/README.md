# Modules Folder Guide

這裡放的是專案真正的功能實作本體。

## Folder Map

- `core/`
  - 共用常數、HTTP helper、內部導航、持久化快取、交易日工具

- `data_sources/`
  - 股票主檔、行情、月營收、券商分點、籌碼、價格快取

- `home/`
  - 首頁專用的資料整理、簡報摘要、tab section renderers

- `etf/`
  - 主動 ETF 資料、歷史快照、異動整理

- `market_map/`
  - 產業地圖 taxonomy、db、snapshot、value chain、events

- `industry/`
  - 舊產業輪動、分類、company links

- `news/`
  - 新聞彙整、事件、AI 分析

- `research/`
  - 研究工作台、法說、transcript 搜尋與分析

- `backtest/`
  - 回測、策略訊號、績效計算

- `ui/`
  - 共用 UI、背景任務、sidebar、backtest 視覺組件

## Editing Rule

- 想改頁面流程：去 `app_pages/`
- 想改真正邏輯：回 `modules/`
- 新功能請優先放進對應的 `modules/<domain>/`

這樣大家分工時，比較不會在 repo root 裡迷路。
