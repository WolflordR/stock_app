# Trade Worker

這裡會放 NAS 上定時執行的資料任務。

第一階段任務拆分方向：

- market data update
- broker CSV import
- ETF snapshot update
- revenue update
- database backup

worker 是唯一主要寫入者；API 以讀取為主。這樣先用 SQLite / DuckDB 也比較穩。

目前可用指令：

```bash
python apps/worker/check_paths.py
python -m apps.worker.backup_databases --label manual
python -m apps.worker.update_price_cache --stock 2330 --days 180
python -m apps.worker.update_price_cache --stock 2330 --days 180 --force
python -m apps.worker.import_broker_csv_folder --date 2026-09-04
python -m apps.worker.daily_update --dry-run
```

NAS 排程可以先從保守模式開始：

```bash
python -m apps.worker.daily_update
```

Mac 本機自動排程：

```bash
cp .env.local.example .env.local
scripts/install_local_launchd.sh
```

立刻手動跑一次：

```bash
scripts/run_local_daily_update_now.sh
```

需要網路更新時再逐步加 flag：

```bash
python -m apps.worker.daily_update --price-stock 2330 --price-days 180
```

若要更新股票主檔內所有個股價格：

```bash
python -m apps.worker.daily_update --price-all --price-days 1825
```

如果先前網路失敗造成該股票被標記為 failed，可以加上 `--price-force` 立刻重試：

```bash
python -m apps.worker.daily_update --price-stock 2330 --price-days 180 --price-force
```
