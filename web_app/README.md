# Web App Beta

這個資料夾是給未來 HTML / 前後端分離版本用的，不會影響目前的 Streamlit 主站。

目前先提供：

- `api.py`
  - FastAPI 入口
  - 先開主動 ETF 的 API
- `templates/index.html`
  - 極簡前端殼
  - 後面可以慢慢長成真正的 HTML / React 前端
- `static/app.js`
  - 首頁 client-side router 骨架

## 啟動方式

```bash
cd /Users/ralph/Desktop/code/trade
stock_env/bin/python -m uvicorn web_app.api:app --reload --port 8010
```

打開：

- `http://localhost:8010/`
- `http://localhost:8010/api/health`
- `http://localhost:8010/api/active-etf/overview`

## 原則

1. 不取代 Streamlit，先平行存在
2. 先搬 `主動ETF`
3. API 直接重用現有 Python 資料整理邏輯
4. 前端導航先模仿 `internal_nav.py` 的路由概念
