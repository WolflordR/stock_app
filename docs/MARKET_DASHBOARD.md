# Market Dashboard

首頁沿用 React/Vite、FastAPI、SQLite 和原有的深色卡片樣式。`GET /api/dashboard` 是首頁的單一讀取端點；`GET /api/events` 支援日期、事件類型、狀態、股票代號／名稱、自選股篩選和分頁。側邊欄「法說會與財報日期」提供完整事件列表及來源更新狀態。原 `/api/dashboard/overview` 保留給系統狀態功能。

## 資料流程

1. `price_cache.db` 的當日 OHLCV 計算可觀測股票的漲跌家數、20/60MA 廣度、20 日新高／新低；股價乘股數僅顯示為「追蹤股估算成交額」。
2. `sector_rotation.db` 的 `benchmark_daily` 和 V4 `rotation_daily` 提供指數及 L3 排行。產業強度公式仍集中於 `modules/industry/rotation_v3.py`，首頁不重算或自行稱成交金額增加為資金淨流入。
3. `services/dashboard_signals.py` 對快取 OHLCV 執行原有 `analyze_initial_rise_candidate`、`analyze_near_breakout_candidate` 和 `analyze_bowl_bottom_volume_candidate`。同一股票同一技術策略的前一交易日不符合、最新交易日符合時，`is_new=1`。首頁另有獨立的「大戶持股增加」策略頁籤：符合集保「逾 1,000 張」持股比例較前一週增加的上市櫃普通股可入選，無須同時觸發技術策略。所有策略均須**成交股數 > 1,000,000 股／1,000 張，或收盤價 × 成交股數 > 200,000,000 元**。成交量使用訊號同日的股數；成交值是估算值，並非交易所公布的實際成交金額。持股比例按 `chip_trends.db.stock_ownership_distribution_weekly` 第 15 級股數 ÷ 第 17 級總股數 × 100% 計算，要求兩個完整週報、週報日期不晚於訊號日、最新週報距訊號日不超過 14 天、相鄰週報間隔不超過 14 天。缺報或比例未增加者不會出現在該策略，比例增加不等於主力買超。大戶策略採週報，不使用每日技術訊號的 NEW 判定。篩選不刪除策略快照，也不影響使用者自選股。
4. `services/events/company_events.py` 取 TWSE 與 TPEx 官方每日重大訊息，並按月份查詢臺灣指數公司 IR 議合服務平台的上市櫃法說會行事曆，補足較早公告但已不在每日資料中的場次。同公司、日期、時間的來源會去重，優先保留 MOPS 重大訊息；成功查詢後移除行事曆中已取消或改期的舊場次。明確公告的法說日期為 `confirmed`；「財務報告董事會預計召開日期」為 `estimated`；董事會決議通過財務報告的重大訊息，按官方發言日期記為 `completed`。董事會決議公告不等同完整財報電子書已申報。只接受可解析的事件日期，保存來源網址及驗證時間；來源失敗時保留前次事件並記錄錯誤。後續董事會日期修正或決議公告會取代同公司同季的舊預計日期。
5. 自選股與事件、訊號在 API 端合併；策略績效沒有持久化、可比較的回測統計時回傳 `null`，首頁顯示 No data。

## 更新與驗證

`apps.worker.daily_update` 已增加 `refresh_company_events` 和 `refresh_dashboard_signals` 兩步。也可分別執行：

```bash
stock_env/bin/python -c 'from services.events.company_events import refresh_events; print(refresh_events())'
stock_env/bin/python -m apps.worker.refresh_company_events
stock_env/bin/python -c 'from services.dashboard_signals import refresh_signals; print(refresh_signals())'
```

NAS scheduler 另外於台北時間每天 08:30、20:30 執行輕量事件同步，時間可用 `TRADE_EVENTS_TIME`、`TRADE_EVENTS_EVENING_TIME` 設定。平日 18:45 的既有完整更新也會刷新事件。瀏覽頁面只讀 SQLite，不在使用者請求時抓官方站。IR 行事曆查當月及後續三個月（尚未開放的年度停止查詢）；MOPS 每日重大訊息持續累積。較早且兩者均未涵蓋的日期不能視為「沒有法說／財報」。來源失敗會保留上次資料並在頁面顯示錯誤。此部署設定需在下一次 NAS 程式更新後才會在 NAS 生效。

Migration 在 `migrations/20261009_company_events.sql` 和 `migrations/20261009_dashboard_signals.sql`，服務啟動時以 `CREATE TABLE/INDEX IF NOT EXISTS` 執行。新資料庫已加入備份清單。首頁 API 的市場廣度計算快取五分鐘；事件匯入和全股票策略掃描在 worker 執行，不阻塞頁面。

測試：`tests/test_market_dashboard.py` 檢查 ROC 日期、事件類型、估計狀態、去重、無資料和 API 無效篩選。前端以 `npm run build` 驗證；窄螢幕表格可橫向捲動，頁面本身不水平溢出。
# 大盤成交值量比

首頁「市場總覽」的成交值量比 = **當日股票成交金額 ÷ 前 5 個已保存交易日的平均股票成交金額**。分母不含當日，資料不足 5 日時顯示缺值。上市、上櫃分別計算；合計只採兩市場都有資料的相同日期，且前 5 日也必須各有兩市場資料。

- 上市：[TWSE 每日收盤行情](https://www.twse.com.tw/zh/trading/historical/mi-index.html) 的「成交統計 → 證券合計(1+6+14+15) → 成交金額(元)」，涵蓋股票，不含 ETF 與權證。
- 上櫃：[TPEx 市場現況](https://www.tpex.org.tw/zh-tw/mainboard/trading/info/highlight.html) 的「上櫃股票當日彙總資訊 → 本日總成交值(佰萬元)」，乘以 1,000,000 換算為元；原始值以佰萬元公布，保留其精度，不與股數相除。
- 每日 worker 的 `refresh_market_turnover` 會補最近 18 個曆日的官方日報，儲存到 `chip_trends.db.market_turnover_daily`。頁面只讀資料庫，來源失敗時保留舊值及資料日期，不補 0。
