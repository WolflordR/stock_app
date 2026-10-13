# NAS 券商分點資料排程

這個容器每天台灣時間 19:00 查詢證交所最新交易日，下載全部上市股票的券商 CSV。已存在且有效的 CSV 會略過；若當晚仍有下載失敗，22:00 再補抓一次。週末及休市日也會檢查前一交易日缺少的檔案。

安裝在 NAS 的 `/volume1/home/ralphchen1005/trade-app/broker_scraper`，並使用 Trade App 既有的 `data` 和 `logs` 目錄。它獨立於網站的 Compose 專案，不會改動現有 API、網頁或排程容器。

```sh
cd /volume1/home/ralphchen1005/trade-app
sudo docker compose --env-file .env -f broker_scraper/compose.yaml up -d --build
sudo docker compose --env-file .env -f broker_scraper/compose.yaml ps
sudo docker compose --env-file .env -f broker_scraper/compose.yaml logs --tail=30 scraper
```

下載資料位於 `data/raw/broker/twse/<交易日>/`。每天的紀錄位於 `logs/broker_scraper/scraper_YYYY-MM-DD.log`，排程狀態位於 `logs/broker_scraper/scheduler.json`，容器運行狀態位於 `logs/broker_scraper/heartbeat.json`。首次啟動若已過 19:00，會立即執行當天一輪；當日成功後重啟不會重跑，失敗時最多補跑一次。日期未變時，仍會補抓尚未成功的股票。

網站排程在 21:00 及 23:15 匯入已下載的 CSV；下載程式若首次失敗，22:00 會再試一次。兩個排程共用檔案鎖，不會同時讀寫同一批 CSV。

在 NAS 驗證容器可用但不下載資料：

```sh
sudo docker compose --env-file .env -f broker_scraper/compose.yaml run --rm --no-deps scraper python -m broker_scraper.scraper --dry-run
```
