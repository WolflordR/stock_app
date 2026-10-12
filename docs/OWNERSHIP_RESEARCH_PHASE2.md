# 大戶持股量化研究：探索性後端與正式資料管線（2026-10-11）

## 資料與名稱

`modules/ownership_research` 沿用原始 `chip_trends.db` 的 17 級集保資料、官方行情 `ownership_research.db`，以及既有 Yahoo 價格快取。原始來源資料未改。400／1000 張因子精確名稱為**逾 400／逾 1000 張**：官方級距 12–15／15，股數各加一次；第 16 級為差異調整，第 17 級為分母，均不加入大戶分子。散戶預設第 1–3 級（10 張以下）。閾值只接受官方級距對應的 100、200、400、600、800、1000 張，不能在官方不存在的門檻做插值。

`FactorConfig` 控制門檻、主要門檻、1／4／8 週等任意正整數週變化、散戶級距、週報間隔及歷史 Z-score 視窗。速度以相鄰週的實際間隔換算為百分點／週；加速度是速度的一週變化。遇缺週或品質未通過週報，連增、變化及速度的連續序列重置。所有因子只讀當週與之前集保資料，不讀股價。

## 1,905 份原先標示的異常週報

先前的檢查誤把第 16 級當成另一個應加總的持股級距。集保官方欄位定義是「差異數調整」，正確核對式為**第 1–15 級股數合計 − 第 16 級股數 = 第 17 級總股數**。逐份重新核對後，原先 1,905 份（2026 年、724 個代號）全部相符。`audit-tier16` 的[逐份核對 CSV](../data/ownership_research/tier16_reconciliation_audit.csv)保留舊檢查與正確檢查的差異。原始集保資料沒有修改或刪除；只修正驗證及研究樣本篩選邏輯。官方級距說明見[集保資料欄位文件](https://schema.gov.tw/gsp/frontstage/resource.download/9f7d9184-20a0-49eb-b7dd-96e23686c4ef)。

新增 2021 年鏡像週報 13 週後，資料庫共 104,153 份公司／證券週報，其中 104,151 份通過品質檢查。真正有問題的 2 份是 2021-07-23 的 3026 與 2021-08-20 的 0056：股數可正確核對，但來源檔的第 17 級比例為 101%，已列入[異常明細](../data/ownership_research/tdcc_anomalies.csv)並排除因子計算。這兩筆仍保留原始數值以待官方原檔複核。

## 探索性研究口徑

CLI `python -m scripts.ownership_research_study` 可調因子、門檻、1／4／8 週變化、公布延遲假設、5／10／20／40／60 交易日、lead-lag、分組數、事件門檻、價格來源及持股級距。未知實際公告時間的週報，以基準日加指定**曆日**作情境假設；取其後第一個股票有成交的市場交易日開盤價，最多容許 2 個市場交易日進場延遲。出場取第 N 個市場交易日收盤價；中途股票無成交或資料缺漏則整個樣本排除，不改到下一個可用日期，不把缺值當 0。預設同股票、同持有期不重用重疊未來路徑；事件門檻篩選後重新做不重疊抽樣。

Yahoo 快取只供第一批探索：原快取由 `yfinance.Ticker.history()` 寫入，價格調整慣例、公司行動覆蓋和歷史證券涵蓋未獨立核對；輸出一律稱「價格變化」，不稱總報酬或可交易績效。官方原始行情也未還原股價。公司範圍先以官方現行公司 CSV 與終止上市／上櫃名冊交集確認，ETF 等非公司證券排除，但過去完整上市狀態與轉板時間仍未逐日核實。

相關、Lead-Lag、分組及事件分析只報描述性數字，不做因果、顯著性或策略績效宣稱。跨股票共同行情、樣本選擇與除權息污染仍需後續處理。

## 第一批實測

修正第 16 級口徑後已重新執行探索研究：週報 2026-07-03 至 2026-09-11；Yahoo 價格快取 2026-07-01 至 2026-10-12。公司候選週報 21,721 份，逾 1000 張一週變化有效樣本 21,717 份。完整結果見[JSON](../data/ownership_research/exploratory_after_tier16_20261012.json)。

| 假設延遲 | 5 日 Pearson / Spearman | 5 日非重疊樣本 | 大戶一週變化 ≥0.01 pp 之 5 日平均價格變化 | 事件樣本 |
| --- | ---: | ---: | ---: | ---: |
| 3 曆日 | -0.0119 / +0.0099 | 11,155 | -0.607% | 4,571 |
| 7 曆日 | -0.0116 / +0.0267 | 11,167 | -0.680% | 4,571 |
| 14 曆日 | -0.0022 / -0.0080 | 11,140 | +1.172% | 4,572 |

相關接近零；延遲假設改變時，事件平均價格變化甚至反轉，不能據此認定有可交易的預測力。14 曆日延遲下 60 日視窗目前無完整出場資料，明列 `n=0`。

## 正式資料建置

`fetch-actions` 已接 TWSE／TPEx 除權息與減資恢復買賣**參考價**公告。2016-10 和 2026-09 均有成功回應；每筆原始欄位 JSON、來源網址、抓取時間及回應雜湊留存。除權息參考價不等於含現金股利再投入的總報酬。官方說明：[TWSE 除權息公式](https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html)、[TWSE 減資公式](https://www.twse.com.tw/zh/announcement/reduction/twtauu.html)、[TPEx 除權息](https://www.tpex.org.tw/zh-tw/announce/market/ex/cal.html)。歷史完整公司行動與還原開盤／收盤價尚未核實；`research_verified_adjusted_prices` 保持空白。

若需多年完整批量資料，TWSE [資料商店](https://eshop.twse.com.tw/zh/product/detail/000000006f6a5e3401702cea7ba20041)提供授權的除權息計算結果檔，標有起始日期與內部／外部使用條款。現有網站查詢端點可逐月查證，但不能把少數成功月份推論成 2016 年至今無缺漏、也不能將 Yahoo 的調整後價格直接升格為核實總報酬。下一步須核對除權息、減資、變更面額、轉板及現金股利再投入規則，才能填入正式還原開收盤表。

`refresh-lifecycle` 讀官方現行公司名單、[TWSE 終止上市](https://www.twse.com.tw/zh/listed/suspend-listing.html)及[TPEx 終止上櫃](https://www.tpex.org.tw/zh-tw/mainboard/listed/delisted.html)。本地讀入現行 TWSE 1,089、TPEx 893 家，以及 2016 年以來可辨識的終止掛牌 TWSE 246、TPEx 92 筆。現行名單已改用及時更新的 MOPSFIN 上櫃檔；舊 `dts.twse.com.tw` 檔查到的出表日期停在 2024-05-22，不能當本日名單。終止掛牌事件另存，不與現行公司強行合併；代號 2301、2432 在現行公司與舊終止名冊出現衝突，標為 `code_reuse_conflict` 並排除探索樣本。退市名冊通常缺原上市日期，`validation_status` 仍為 `partial_history`。正式模式要求獨立核實的週報公告時間、歷史普通股身分及還原開盤／收盤價，現階段返回 `blocked`，不輸出績效。

新增 `backfill-tdcc-archives` 可限制年份與每次下載週數，以來源 manifest 和雜湊值恢復執行；已存的原始週報若與來源不同，會記錄錯誤且不覆寫。實測回補第三方鏡像 2021-07-02 至 2021-09-24 共 13 週、565,641 個級距列；再次執行只讀 manifest，13 週全部快取命中、下載 0 份。鏡像目前列出 2021 年 13 週與 2026 年 24 週，2020、2022–2025 沒有對應年份目錄；這些空缺不能當成已有官方歷史。官方價格庫目前只有 2016 年 1 個交易日與 2026 年 25 個交易日，故 2021 新增週報尚不能用官方價格做持有期研究。

## 執行及驗收

每日 worker 只重查當月四種公司行動公告；歷史月份以 CLI 分月補齊，不讓全史下載佔用 NAS 常駐排程。

```bash
stock_env/bin/python -m scripts.ownership_research_data audit-anomalies
stock_env/bin/python -m scripts.ownership_research_data backfill-tdcc-archives --first-year 2020 --last-year 2026 --max-weeks 13
stock_env/bin/python -m scripts.ownership_research_data fetch-actions --month 2026-09-01
stock_env/bin/python -m scripts.ownership_research_data refresh-lifecycle --first-year 2016
stock_env/bin/python -m scripts.ownership_research_study --start 2026-07-01 --end 2026-09-15 --delays 3,7,14
stock_env/bin/python -m scripts.ownership_research_study --start 2026-07-01 --end 2026-09-15 --mode formal --price-source official_raw --output data/ownership_research/formal_gate.json
stock_env/bin/python -m pytest -q tests
```

測試覆蓋級距加總、過去資料限制、缺週重置、假設公布延遲、精確市場交易日、停牌缺值、正式門檻、異常明細及官方來源日期／欄位變動。尚待：官方公司行動全史補齊、核實完整含息還原開收盤價、完整歷史普通股有效區間與市場基準資料，之後才能做正式事件回測及穩健顯著性分析。
