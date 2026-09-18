# Apps

這裡放產品化後的執行入口。

- `api/`: FastAPI 後端，負責提供網站資料。
- `web/`: Vite React 正式網站。
- `worker/`: 爬蟲、匯入、排程、備份。

舊 Streamlit UI 已移到 `archive/legacy_streamlit/`，只當參考，不再是正式入口。

本機開發順序：

```bash
scripts/run_api.sh
scripts/run_web.sh
```

NAS 草創部署：

```bash
scripts/init_nas_data.sh
scripts/nas_compose_up.sh
```
