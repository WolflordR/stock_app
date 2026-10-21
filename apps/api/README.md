# Trade API

FastAPI 後端骨架。第一階段目標是 read-only API，讓正式網站透過 HTTP 取資料。

初始 API：

- `GET /health`
- `GET /api/runtime/paths`
- `GET /api/runtime/data-status`
- `GET /api/stocks/status`
- `GET /api/stocks/{stock_id}`
- `GET /api/stocks/{stock_id}/overview`
- `GET /api/stocks/{stock_id}/quotes`
- `GET /api/market-map/status`
- `GET /api/market-map/groups`
- `GET /api/market-map/topics`
- `GET /api/market-map/topics/{topic_name}/members`
- `GET /api/broker/overview`
- `GET /api/broker/branches?trade_date=2026-10-08` — branches active on a selected imported date (defaults to the latest date per market).
- `GET /api/broker/trade-dates?market=all` — imported trading dates for `all`, `TWSE`, or `TPEx`.
- `GET /api/broker/branch-stocks?broker_name=凱基台北&trade_date=2026-10-08&side=buy&sort_by=volume_ratio&descending=true&limit=50&offset=0` — one branch's daily net buy/sell stocks, weighted buy/sell execution prices, and same-date cached stock liquidity/price metrics. Supported `sort_by`: `net_shares`, `volume`, `turnover_value`, `volume_ratio`, `change_pct`.
- `GET /api/dashboard/overview`

之後再逐步加入：

- `GET /api/market/overview`
- `GET /api/etf/active`
- `GET /api/backtest/...`

本機啟動：

```bash
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

可用 `TRADE_API_CORS_ORIGINS` 設定前端來源，多個來源用逗號分隔。
