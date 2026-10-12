# 大戶持股與股價量化研究：來源、資料品質與分階段驗收

## 現有架構與實際覆蓋（2026-10-11 本機）

正式網站為 React/Vite、FastAPI、SQLite、daily worker；舊 Streamlit 不是正式 UI。既有 `modules/backtest` 是交易策略掃描及回測，價格透過 `price_cache.db.price_history` 的 Yahoo OHLCV 讀取，不能直接當成有還原價與歷史可用時間的事件研究資料。新研究模組放在 `modules/ownership_research`，使用獨立的 `ownership_research.db`；不改既有回測引擎，也不讓網頁請求爬官方來源。

| 現有資料 | 本機可觀察範圍 | 關鍵限制 |
| --- | --- | --- |
| `chip_trends.db.stock_ownership_distribution_weekly` | 2026-04-30 至 2026-10-08；24 週、70,880 個股票週報 | 64,943 筆來自非官方歷史鏡像，缺實際公布時間；原始級距為 1–17 級 |
| `price_cache.db.price_history` | 2021-09-07 至 2026-10-08；2,240,403 列 | Yahoo 價格，沒有還原價與原始來源快照 |
| `chip_trends.db.stock_margin_short_daily` | 2025-10-07 至 2026-10-08；446,114 列 | 官方日報，沒有歷史實際公布時間；次日可能修訂前日餘額 |
| `chip_cache.db.institutional_trading` | 2025-11-12 至 2026-10-08；95,918 列 | 官方交易日資料，本地開始累積較晚 |
| `stocks.db.securities` | 目前 1,944 家 | 目前主檔，不是歷史上市／下櫃名單或歷史股本 |
| `sector_rotation.db` | 主要 2026-09 至 2026-10 | 產業 membership 有有效日期，歷史深度不足 2016 年研究 |

## 官方來源與可用限制

- [TDCC 集保戶股權分散表](https://www.tdcc.com.tw/portal/zh/smWeb/qryStock)：每週最後營業日收盤持股，官方歷史查詢保留一年。`openapi.tdcc.com.tw/v1/opendata/1-5` 用於最新快照；不能假設能從官方一次下載 2016 年至今全歷史。現有較早 2026 週次來自第三方鏡像，須保留此來源身份。
- [TWSE 每日收盤行情](https://www.twse.com.tw/zh/trading/historical/mi-index.html)、[TPEx 上櫃股票行情](https://www.tpex.org.tw/zh-tw/mainboard/trading/info/pricing.html)：官方頁面提供歷史查詢。本機已用兩市場端點驗證 2016-10-07 與 2026-10-08 單日資料；這不能證明中間每一天完整。批次抓取必須限制日期範圍、記錄空日／錯誤、可重試。
- [TWSE 三大法人日報](https://www.twse.com.tw/zh/trading/foreign/t86.html)、[TPEx 法人買賣明細](https://www.tpex.org.tw/zh-tw/mainboard/trading/major-institutional/detail/week.html)、[TWSE 融資融券](https://www.twse.com.tw/zh/trading/margin/mi-margn.html)、[TPEx 融資融券](https://www.tpex.org.tw/zh-tw/mainboard/trading/margin-trading/transactions.html)：網站已有日更程式；歷史逐日補齊需另做限速與缺漏審計。TWSE 指出融資融券前日餘額可能次日修正。
- [TWSE 除權息參考價](https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html) 與[減資恢復買賣參考價](https://www.twse.com.tw/zh/announcement/reduction/twtauu.html)：官方提供事件與參考價，不等於完整、已核對的總報酬還原序列。`adjusted_close` 在驗證前保持 `NULL`。

## 資料庫與時點規則

`migrations/20261011_ownership_research.sql` 新建來源查詢紀錄、官方每日價格、TDCC 週報 metadata、歷史證券狀態與公司行動預留表，以及品質檢查紀錄。原始 17 級資料仍只存於 `chip_trends.db`。研究表保留報表基準日、來源網址、首次本地觀測時間；`published_at` 只有能獨立確認實際公告時間時才填。首次本地觀測時間**不是**官方公布時間。第三方歷史鏡像一律標記 `unverified_archive`，嚴格的預測／回測不得把週報基準日當成訊號可用日。

集保級距須逐級只加一次：逾 100 張取 10–15 級，逾 400 張取 12–15 級，逾 1,000 張取 15 級；16 級是差異調整，17 級是總股數分母，均不可當成持有人級距再加。官方級距無法將「恰好 100／400／1,000 張」從前一級拆出，因此精確研究名稱應使用「**逾** N 張」（100,001／400,001／1,000,001 股以上），不可將其冒稱為含門檻當日的「N 張以上」。

歷史股票範圍不可用目前 `stocks.db` 回填過去：退市、轉板、新上市需按當時官方股票身分確認。官方單日價格先保存全部四碼證券，未確認普通股身分者不進正式樣本。原始價格與調整後價格分欄，缺調整事件不得直接將未還原價格稱為總報酬。

## 第四步：已實作的受控資料作業

```bash
stock_env/bin/python -m scripts.ownership_research_data sync-ownership
stock_env/bin/python -m scripts.ownership_research_data backfill-prices --start 2026-10-08 --end 2026-10-08
stock_env/bin/python -m scripts.ownership_research_data quality
```

`backfill-prices` 每次最多 31 個曆日、逐日兩市場並保留查詢狀態；成功日預設跳過，空回應與失敗不刪已保存資料。只在有成交且 OHLCV 合理時寫入。`sync-ownership` 可重跑，不改原始資料；每天既有 TDCC 更新後做輕量同步，並重試最近 8 個曆日的官方價格（成功日跳過）。大型歷史回補在 Mac 分批執行，不放入 4GB NAS 的常駐排程。新資料庫已加入既有備份清單。

驗收：新資料可重跑而不重複、錯誤日不覆蓋好資料、拒絕錯報日期、17 級完整性及各級股數合計與總股數一致、來源狀態可查、還原價與公告時間缺值保留缺值。現有 70,880 份週報中有 68,975 份通過此結構檢查；1,905 份的級距合計與總股數不一致，保留原始資料並標記不通過，不自動校正。已實測 2016-10-07、2026-10-08 和 2026 年 9 月兩市場日行情，共 42,698 筆原始價格；還原價仍為 0 筆。執行 `stock_env/bin/python -m pytest -q tests/test_ownership_research_data.py`。

## 後續階段與驗收門檻

1. **資料補齊與調整。** 官方價、法人、信用交易按月分批驗證；建立除權息／減資與歷史股本、上市狀態，對照官方日期。資料品質表須揭露逐年覆蓋率與缺漏；任何一來源不足不能補零。
2. **因子與事件研究。** 先以可證明的最早可用時間生成 100／400／1000 張級距、1／4／8 週變化、連增週數、速度／加速度、散戶差、人數、平均股數及歷史 Z-score。進場為資料可用後下一個**有成交**交易日的可交易價格，5／10／20／40／60 日結果按股票、市場、月份聚類或使用不重疊抽樣及穩健標準誤；分開報告相關、預測、樣本數及多重檢定風險。缺經驗證還原價格時不宣稱總報酬或顯著性。
3. **參數化實驗與 UI。** 實驗設定及結果以版本化 JSON 存檔，先在 Mac 執行有界研究工作；FastAPI 只讀已完成結果，React 沿用深色卡片、圖表與空狀態，清楚標示來源期間、樣本數和未通過品質門檻原因。既有回測不受影響。
4. **模型擴充。** 僅保留特徵表與 walk-forward 切分介面；本階段不安裝或訓練 LightGBM／XGBoost。
