# 台灣上市櫃電子股細產業輪動 V3

## 入口與執行

網站左側選單「輪動」即為細產業觀測台。現有 FastAPI + React/Vite + SQLite 架構保持不變。

介面截圖：[`rotation_v3_screenshot.png`](rotation_v3_screenshot.png)。

```bash
# 建立資料表（可重複執行）
stock_env/bin/python -m scripts.rotation_v3_pipeline migrate
# 更新官方上市／上櫃普通公司名單、細產業映射、覆核清單、CSV
stock_env/bin/python -m scripts.rotation_v3_pipeline sync
# 官方指數與法人買賣超、最近 20 個交易日輪動序列
stock_env/bin/python -m scripts.rotation_v3_pipeline backfill --trade-days 20
# 只更新今日資料；既有 apps.worker.daily_update 亦已包含 V3 步驟
stock_env/bin/python -m scripts.rotation_v3_pipeline daily
stock_env/bin/python -m apps.worker.daily_update
```

API：`/api/rotation/coverage`、`/api/rotation/filters`、`/api/rotation/ranking?level=3`、`/api/rotation/detail/{sector_key}`。排名支援 `date`、`level=1|2|3`、`l1`、`l2`、`include_small`。明細提供成分股、五種候選名單、Rotation Diff 與近 20 日 Timeline。舊 `/api/sectors/*` 維持相容。

## 資料來源與分類

- 公司母體：臺灣證交所 `t187ap03_L` 與櫃買中心 `t187ap03_O` 公開資訊，僅匯入四位數普通公司代號。以官方產業碼 24–31 為電子基底，另外納入 FINAL 包中電子細分類及櫃買官方產業鏈確證的相鄰公司。包內金融、航運、餐飲等跨市場種子不納入電子輪動母體。
- 營業項目：櫃買產業價值鏈的 `company_basic.php` 官方公司資料；`MAIN_BUSINESS1–3` 與描述文字有來源網址及抓取狀態。分類規則只讀營業文字，絕不從公司名稱推斷產品。一般敘述不足以確定具體產品時留在覆核清單。
- FINAL 包的 205 筆 `fine_taxonomy_v2.csv` 為基本 taxonomy。官方產業鏈 319 筆成員，以及 139 筆產品覆寫有部分 L1/L2/L3 組合不在該表中，因此增加**來源原文延伸節點**並在 `fine_taxonomy.origin` 標記，不將不同節點強制合併。
- `fine_memberships` 保存多對多產業鏈成員及來源網址；每家公司當期至多一筆 `primary_for_flow=1`，由 SQLite 唯一索引約束。優先序：人工確認 > 產品覆寫 > 官方細項 > 明確的營業項目規則。題材在 `fine_themes`，不參與加總。同一家公司有多個官方細項且無產品覆寫時，主要歸屬為暫定且進覆核清單。
- 細分類會在更新名單後保留；較低優先序的新結果不會覆蓋既有高優先序主要分類。`valid_from/valid_to` 與來源時間記錄於資料表。歷史 20 日視圖沿用目前分類，僅供描述，**不得當作無前視偏誤回測**。

產出：[`all_twse_tpex_electronics_fine.csv`](../data/all_twse_tpex_electronics_fine.csv)、[`review_queue.csv`](../data/review_queue.csv)、[`unresolved_official_memberships.csv`](../data/unresolved_official_memberships.csv)。原始包完整保存在 [`data/sector_rotation/final`](../data/sector_rotation/final)。
細分類 CSV 每筆是「公司 × 分類」成員關係，包含次要官方產業鏈，因此資料列數會高於目標公司數；只有 `primary_for_flow=1` 可用於不重複加總。

## 分數與資金流

每檔有效股價至少 26 筆交易資料、當日成交量大於零；停牌／缺價不進觀測分母，畫面顯示有效／成分筆數及品質。個股報酬以中位數彙總，單檔報酬截在 ±60%，避免極端值支配產業。L3 預設至少 5 檔有效且涵蓋率達 60% 才排行。

V3 權重取自提供的 `flow_rotation_spec_v3.json`：相對強度 25%、廣度 20%、成交擴張 20%、價格動能 15%、突破參與 10%、承接壓力 10%。相對強度為個股 20 日報酬減去所屬上市／上櫃官方指數 20 日報酬後取中位數；RS 動能比較 5 日 RS 與 20 日 RS 平均速度。成交擴張以當日估算成交額對前 5 日均值；突破為收盤超越前 20 日最高價；承接壓力結合 CMF20 與 MFI14。分數將各訊號限界到 0–100，再依權重加總。階段按分數、RS、動能、廣度與集中度給出沉寂、改善中、早期輪動、領先、擁擠、轉弱。當前 1 檔成交占比達 40%，或至少 5 檔組合的前 3 檔達 70%，標記 Concentrated。

官方三大法人資料來自證交所 T86 與櫃買每日三大法人表。原始資料是**股數**，畫面除以 1,000 顯示「張」，並顯示資料涵蓋率。沒有逐筆實際成交金額，因此**不計算或顯示法人新台幣淨流入**。收盤價 × 成交股數只是估計成交額，僅用於成交占比與擴張；CMF/MFI 只是市場壓力估計，與官方法人股數分層呈現。

個股「初升」調用現有 [`modules/backtest/signals/initial_rise.py`](../modules/backtest/signals/initial_rise.py) 的 `matched` 結果；其他早期輪動／跟漲候選只是畫面篩選，不表示同一回測訊號。

## 覆核流程與限制

在 `review_queue.csv` 查看未能從營業項目確定 L3、產品覆寫自標待細分，以及官方多重歸屬的股票；在 `unresolved_official_memberships.csv` 查看公司名稱或市場提示無法唯一對到現行普通公司的來源列。請用來源資料核實後，再在資料庫加入 `source='manual_verified'` 的主要分類或擴充經審核的規則。前台涵蓋率會如實顯示未完成的部分。

截至 2026-10-07 的即時建檔：上市普通公司 1,089、上櫃普通公司 893；官方電子業碼 24–31 為上市 458／上櫃 453，共 911 檔；加上可追溯的相鄰公司後目標 939（上市 474／上櫃 465）；L3 主要分類 420（44.7%）；覆核 591（62.9%，其中部分已有暫定 L3）；未解決官方成員名 3 筆。數字會隨官方名單與覆核進度更新。最近 20 個交易日為 2026-09-08 至 2026-10-07。

此版本的限制：大量營業項目過於籠統，仍需人工逐檔補細分類；包內分類日期不是歷史有效日，不可據此回測；官方來源只有法人買賣超股數，無可核實逐股淨金額；缺價或缺法人資料會降低樣本涵蓋率；估計成交額使用收盤價而非逐筆成交金額。

## 驗證

```bash
stock_env/bin/python -m unittest discover -s tests -v
npm run build --prefix apps/web
```
