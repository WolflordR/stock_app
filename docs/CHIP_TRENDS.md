# 大盤融資融券與個股籌碼走勢

## 官方資料與口徑

- 上市：TWSE `MI_MARGN` 日報，取「信用交易統計」的融資／融券交易單位餘額與融資金額（仟元），另保存四碼普通股逐檔明細。市場總計涵蓋官方「全部」報表商品。
- 上市融資金額在 API 換算為億元：官方「仟元」數值除以 `100000`。單日金額變動以同份官方日報的「今日餘額－前日餘額」計算；近 5 日變動則比較第 5 個較早交易日的已存餘額。融券日報沒有金額餘額，因此只顯示張數。
- 上櫃：TPEx 上櫃股票融資融券餘額日報。市場張數總計由**完整官方明細**逐列加總（含 ETF 等報表商品），逐檔表只保存四碼股票。TPEx 這份日報沒有融資金額，資料庫留 `NULL`，不以張數或股價估計。
- 本頁的券資比：`融券餘額張數 / 融資餘額張數 × 100%`。分母為零或缺漏時顯示缺值，不可拿 TWSE 的融資金額（仟元）與融券張數相除。部分市場資訊稱其為「資券比」，本頁固定標明公式，避免與其他命名口徑混淆。
- 合計：只顯示同一交易日同為交易單位／張數的上市與上櫃日報；兩邊有一邊缺報即不顯示該日合計。金額不合計。
- TDCC：每週「集保戶股權分散表」開放資料 `1-5`。原始股數、持有人數、級距與報表日期完整存入。依官方 12–15、13–15、14–15、15 級，分別計算 **400,001、600,001、800,001、1,000,001 股以上**；10 張以下取 1–3 級。16 級差異調整不計入持有人級距，17 級合計股數作比例分母。UI 以「逾 N 張」呈現，避免將「N 張整」錯誤歸入。
- TDCC 開放 API 目前提供最新週快照。每日工作會持續保存新週資料。官方歷史查詢頁標示保留一年，但其查詢端點目前在本機回傳 403。歷史週次可用 `stock_env/bin/python -m scripts.backfill_chip_trends --skip-margin --skip-tdcc --tdcc-archive-year 2026` 從[公開的 TDCC 1-5 原始 CSV 歸檔](https://github.com/wirelessr/tdcc-opendata-archive)補入。這是第三方鏡像，不是 TDCC 的歷史 API；匯入前會把重疊週次逐列與已存官方快照核對，並驗證日期、17 個級距、股數及完整筆數。每筆資料保留歸檔來源連結。未累積足夠週次前，週增、4 週、12 週與比較圖依實際資料顯示空值。

## 資料庫與更新

`migrations/20261009_chip_trends.sql` 建立 `chip_trends.db` 的融資融券、股權分散與 `market_limit_daily` 四張資料表及 `chip_source_status`。主鍵為市場／股票／日期／級距；重跑會覆寫同日期官方資料，來源錯誤不刪舊快照。市場與個股日報按交易日排序，TDCC 按每週報表日期排序。

```bash
python -m scripts.backfill_chip_trends --days 370
python -m apps.worker.daily_update
```

每日工作回補最近 7 個曆日內的平日 TWSE／TPEx 日報，並擷取 TDCC 最新週快照。歷史補齊逐日請求官方日報；TWSE 偶有空白／限流回應，會重試，失敗日期留空並記錄錯誤，可重跑補齊。API 僅讀本地 SQLite，不會在使用者開頁時爬官網。

首頁漲跌停家數由同一每日工作擷取 TWSE `MI_INDEX?type=MS` 的「股票」欄（排除整體市場內其他證券）與 TPEx「上櫃股票當日彙總資訊」。兩市場資料日一致才合計；不同日各自顯示來源與日期，不以本地價格漲跌幅推估漲跌停。

## API

- `GET /api/chips/market/margin-short?market=TWSE|TPEx|combined&days=370`
- `GET /api/chips/stocks/{stock_id}/margin-short?days=370`；`days=0` 讀所有已保存日報，只在個股頁選 ALL 時請求。
- `GET /api/chips/stocks/{stock_id}/ownership?days=750`

官方來源：[TWSE 日報](https://www.twse.com.tw/zh/trading/margin/mi-margn.html)、[TPEx 日報](https://www.tpex.org.tw/zh-tw/mainboard/trading/margin-trading/transactions.html)、[TDCC OpenAPI](https://openapi.tdcc.com.tw/)、[TDCC 股權分散查詢說明](https://original-www.tdcc.com.tw/portal/zh/smWeb/qryStock)。
