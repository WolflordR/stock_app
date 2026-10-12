# 台灣電子與相鄰產業輪動 V4

## 資料模型

- `fine_companies`：TWSE / TPEx 普通公司 universe。電子及相鄰主題共 939 檔；每次同步從官方名單更新。
- `fine_taxonomy`：L1 / L2 / L3 節點。`official_only` 不會寫入 L3。
- `stock_sector_memberships`：每家公司可有多筆已驗證 L3；來源包含 v4 人工校訂、TPEx 產業價值鏈、逐檔公司產業鏈、MOPS 營業項目及 TPEx 公司產品清單。查詢成分股、廣度及輪動分數使用此表。
- `stock_primary_sector`：每家公司至多一筆有效主要 L3。成交額與法人買賣超的加總只使用此表；主分類缺乏可靠依據時留空。
- `official_chain_snapshot` 與 `official_product_evidence`：保留逐檔官方原始證據與網址。主題、籠統的「其他」及同時涵蓋多種產品的鏈條，保留在原始證據，不強行視為已完成 L3。
- `classification_review_v4` 與 `data/review_queue_after_v4.csv`：需要人工確認主要產品／收入歸屬的股票。

## 判定與計算

匯入 `fine_classification_v4.csv` 作主要 L3 的最高優先校訂，匯入 `official_value_chain_memberships_v4.csv` 作多重成分。接著逐檔讀取 TPEx 公司產業鏈與產品清單、MOPS mainBusiness；只有具體產品或服務才轉成 L3。多個 L3 均保留，主 L3 在官方產品／營業項目可判定時才指派。已有人工作業的 `manual_verified` 保持最高優先。

輪動的報酬、廣度、突破、成交擴張及相對強度使用所有 L3 成分。`turnover`、`turnover_share`、`institutional_net_shares` 僅加總主要歸屬於該產業的股票，避免同一檔股票在跨產業統計重複計算。單一公司跨多個 L3 時，L3 的成分數與輪動訊號允許重疊。

## 執行與驗證

```sh
stock_env/bin/python -m scripts.rotation_v3_pipeline sync
stock_env/bin/python -m scripts.rotation_v3_pipeline backfill --trade-days 20
stock_env/bin/python -m unittest discover -s tests -v
npm run build --prefix apps/web
```

`sync` 依序更新 universe、官方逐檔證據、MOPS 營業項目、v4 主分類與多重成分，並強制執行 `sanity_audit_v4.csv` 的 11 項檢查。日常 worker 使用同一順序。API `/api/rotation/coverage` 提供各級 coverage，`/api/rotation/stock/{stock_id}/classification` 提供主要分類和全部 L3，`/api/rotation/detail/{sector_key}` 列出完整成分股。

個股查詢的 `/api/stocks/{stock_id}/overview` 同時回傳 `classification`，包含主要 L3、全部 L3 歸屬、L1/L2 方向、覆核狀態、官方營業項目與證據網址。個股頁分開顯示官方大產業、主要 L3 與跨產業歸屬；主 L3 待覆核時保留已確認的 L3 成分，不填入推測的主要分類。非目標股票的 `classification` 為 `null`。

覆核 CSV 的 `current_l1` / `current_l2` 只顯示唯一可確定的層級；`current_l3` 留白表示尚未選定主要 L3，即使它已有一個或多個已驗證的 L3 membership。`possible_category` 列出可追查的細分類候選，不能直接當作主分類。
