# Stability Checklist

這份清單只收錄會影響正式 React/FastAPI/worker 架構穩定性的事項。

## Completed

1. React web is the active UI.
2. FastAPI owns all frontend-facing data APIs.
3. Worker scripts own data updates, imports, and backups.
4. NAS data paths are centralized through `modules.core.project_paths`.
5. Broker branch CSV import is independent from page rendering.
6. Legacy Streamlit UI is archived under `archive/legacy_streamlit/`.

## Next

1. Confirm the real NAS path and create `.env.nas`.
2. Run the first Docker Compose deployment on NAS.
3. Add a web-triggered broker CSV import job.
4. Add a scheduled daily backup task.
5. Split large API read models after page behavior stabilizes.
