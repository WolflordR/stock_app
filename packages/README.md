# Packages

這裡放可被 `apps/api`、`apps/web`、`apps/worker` 共用的程式碼。

第一階段先保留既有 `modules/`，之後再逐步搬到：

- `trade_core`: domain logic、策略設定、共用 models。
- `trade_data`: repositories、資料來源、DB 存取。
- `trade_jobs`: 爬蟲、排程、匯入流程。
