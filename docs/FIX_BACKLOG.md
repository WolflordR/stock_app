# Fix Backlog

這份清單以目前正式架構為準：React web + FastAPI API + worker + NAS data folder。

## P0 Deployment Stability

1. Confirm real NAS path in `.env.nas`.
2. Run `scripts/init_nas_data.sh`.
3. Run `scripts/nas_compose_up.sh`.
4. Run `scripts/nas_health_check.sh`.
5. Confirm browser can open `http://<NAS-IP>:8080`.

## P1 Data Pipeline

1. Add a web-triggered broker CSV import job.
2. Add scheduled daily DB backup on NAS.
3. Add price cache update presets for common scopes.
4. Add import logs for broker CSV batches.

## P2 Product Pages

1. Improve stock detail broker branch table with multi-day controls.
2. Improve ETF snapshot date picker and empty-state text.
3. Expand strong-stock ranking filters.
4. Replace mock US economic calendar with a real source.

## P3 Cleanup

1. Move more shared logic from `modules/` into `packages/`.
2. Remove archived Streamlit code after all behavior is fully covered by React/API.
3. Split API read models into smaller files once endpoints stabilize.
