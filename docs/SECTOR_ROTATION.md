# 全上市櫃電子股產業輪動資料

## 資料範圍

`data/sector_rotation.db` 以 [TWSE 上市公司基本資料](https://openapi.twse.com.tw/v1/opendata/t187ap03_L)及 [TPEx 上櫃公司基本資料](https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O)建立官方電子股全集。TPEx OpenAPI 失敗時改讀 [MOPS CSV](https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv)。僅納入四碼普通公司代號、官方產業代碼 24–31；上市與上櫃分開計數。同步前先驗證兩個市場均有電子股，失敗時保留上次資料。

2026-10-07 同步結果：上市 458、上櫃 453，合計 911 檔；其中 94 檔有 package seed 的精細分類（10.32%），817 檔保留官方大類並列入待分類。seed 裡的非官方電子股沒有計入這 911 檔。seed 題材是未驗證候選，不列入已驗證題材覆蓋率，也沒有推估營收比重。TWSE 來源出表日為民國 1151006，TPEx 為 1151007。

原 package 的 `official_industry_bootstrap.csv` 使用了四個未出現在 `taxonomy.csv` 的大類代碼；本專案的 `data/sector_rotation/taxonomy.csv` 已按 bootstrap 補入 `optoelectronics`、`electronics_components`、`electronics_distribution`、`other_electronics`。其餘 taxonomy、seed、theme 保留 package 內容。

package 的 `taxonomy.csv` 另有 11 個 `parent_slug` 尚無對應的父節點（例如 `electronics`、`technology`）。目前分類查詢與排行使用分類代碼及成分股，不依賴這些父節點；在擴充完整樹狀瀏覽前需先由分類維護者補齊。

## 檔案與資料表

- `data/all_listed_otc_companies.csv`：兩個市場的官方公司基本資料快照。
- `data/all_electronic_stocks.csv`：代碼 24–31 的官方電子股快照。
- `data/electronic_classification.csv`：每檔的官方產業、主／次分類、待驗證題材，方便人工複核。
- `data/sector_rotation.db`：`official_electronics`、`sector_categories`、`sector_themes`、`stock_sector_map`、`stock_theme_map`、`sector_daily_metrics`。分類與題材都支援一檔多筆；題材有有效日期欄位。
- `data/stocks.db`：同步時補入／更新電子股主檔，保留原本的股本、流通股數與其他股票。

`classification_state=official_only` 表示只有官方大類，不能解讀成精細產業已查證。`taxonomy_mapped` 表示 package seed 提供了細分類，仍應依公司揭露逐步覆核。`verified_theme_total` 只計算有 `verified_at` 的題材。

## 執行

```bash
stock_env/bin/python -c 'from modules.industry.electronics_universe import sync_electronics_universe; print(sync_electronics_universe())'
stock_env/bin/python -c 'from modules.industry.sector_metrics import refresh_sector_metrics; print(refresh_sector_metrics())'
stock_env/bin/python -m scripts.backfill_sector_rotation --trade-days 20
stock_env/bin/python -m apps.worker.daily_update --dry-run
stock_env/bin/python -m apps.worker.daily_update --stop-on-error
stock_env/bin/python -m unittest discover -s tests -v
```

既有本機每日排程會呼叫 `apps.worker.daily_update`，現在預設先同步電子股全集，再補入最近 7 個日曆日的 TWSE/TPEx 官方確認行情，最後計算輪動指標。官方行情同步包含全市場公司股票，以提供相對強度的比較基準。需要暫時略過時可用 `--skip-electronic-universe`、`--skip-sector-metrics`。資料庫檔已納入備份清單。

## 分數與資料日期

輪動分數使用 package `rotation_spec.json` 的六項權重：上漲家數、中位報酬、量增家數、突破家數、相對強度與成交動能。個股報酬先限幅至 ±10%，以中位數和家數比例降低單一小型股的影響。產業至少 5 檔且有 5 檔有效價格才進排行；各指標連同總分存入 `sector_daily_metrics`。1／3／5 日視窗以資料庫內交易日計算。成交動能由收盤價乘成交量估算，是價量代理指標，不是法人或市場「淨流入金額」。

目前已補入 2026-10-01、10-02、10-05 至 10-07 的官方行情，輪動排行最新交易日為 2026-10-07。當日 911 檔官方電子股中有 910 檔取得有效價量；沒有有效價量資料的停牌股票不納入當日分數，仍保留於官方電子股名單。真實法人資金、20 日視窗與題材歷史回測還需資料來源和驗證流程。

## API

- `GET /api/sectors/coverage`：兩市場官方筆數、匯入筆數、分類覆蓋率與同步時間；不一致時 `coverage_ok=false`，網站顯示警告。
- `GET /api/sectors`、`GET /api/sectors/{slug}`、`GET /api/sectors/{slug}/stocks`：分類與成分股。
- `GET /api/sectors/ranking?window_days=1|3|5&date=YYYY-MM-DD`：輪動分數與所有分項。
- `GET /api/themes`：題材字典與候選／已驗證筆數。

網站左側「輪動」頁提供覆蓋率、1／3／5 日排行、各分項和成分股。點成分股可進既有個股頁。
