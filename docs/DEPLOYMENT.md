# Trade Lab on ASUSTOR AS5104T

## Layout and services

The NAS installation root is `/volume1/home/ralphchen1005/trade-app`:

```text
trade-app/
  .env                 # private, retained across releases
  deploy.sh update.sh backup.sh
  current -> releases/<version>
  releases/             # application code only
  data/db/              # persistent SQLite databases
  data/sector_rotation/ # required taxonomy data
  logs/ backups/
```

React/Vite builds into nginx. nginx proxies `/api/` to FastAPI. The API uses one
uvicorn process and has no published host port. One scheduled worker container
runs updates after 18:45 Asia/Taipei on weekdays. It keeps a last-attempt marker
in `logs/` so restarts do not trigger the same update twice. The conservative
daily run skips expensive company reclassification but refreshes official stock
prices, sector rotation, ETF, margin, and TDCC data. It does not run all-stock
yfinance backfills, ML models, or backtests.

Broker CSV downloads and database imports are separate steps. The broker
scraper writes to `data/raw/broker/twse/<trade-date>/`. The scheduled worker
starts a missing-only import after 21:00 Taiwan time each day, waiting for the
scraper's download lock to be released. It writes import status to
`logs/nas_broker_import.json`. The stock page reads
`data/db/broker_daily_trades.db`, so downloaded CSVs alone do not change the
displayed broker rankings. New reports for a date are imported without
reprocessing reports already in the database.

API, worker, and nginx memory limits are 1400 MB, 1100 MB, and 128 MB. Docker
logs rotate at 10 MB x 3 per service. Services have health checks and
`restart: unless-stopped`.

## Initial deployment

The Mac working tree contains local changes and large untracked databases. A
Git clone alone is insufficient. Use `scripts/snapshot_nas_data.py --target
/path/to/empty/staging/data` to make a consistent SQLite snapshot, then rsync
the code and data snapshot separately. Only the initial deployment transfers
all databases. Create `.env` at the NAS installation root from `.env.example`;
verify `TRADE_NAS_ROOT`, `TRADE_BIND_IP`, and `TRADE_WEB_PORT`.

From an interactive SSH Terminal in the NAS installation root:

```bash
./deploy.sh
```

The script uses `sudo docker compose`; enter the sudo password in your Terminal.
It validates data, builds the images, backs up SQLite, starts the services, and
checks HTTP plus the stock master API. It never changes Docker socket
permissions or runs `docker compose down -v`.

## Updates and logs

Commit and push Mac changes to GitHub before updating the NAS. The initial
rsync release can be newer than GitHub. Then on the NAS:

```bash
cd /volume1/home/ralphchen1005/trade-app
./update.sh
sudo docker compose --env-file .env -f current/compose.yaml ps
sudo docker compose --env-file .env -f current/compose.yaml logs --tail=100 -f api web scheduler
cat logs/nas_scheduler.json
cat logs/nas_broker_import.json
```

`update.sh` downloads the GitHub branch archive (NAS Git is not installed),
creates a new release, builds images, backs up
databases, and switches the `current` symlink. It retains `.env`, `data`,
`logs`, and `backups`. If new services fail health checks, it restores the
previous code release and images. Code rollback cannot undo a schema change;
the pre-update database backup is retained for restoration.

## Backup and restoration

```bash
./backup.sh manual
```

Backups are under `backups/<timestamp>-<label>/`. They use SQLite's online
backup API and `PRAGMA quick_check` to include WAL data consistently. Taxonomy
packages and small configuration CSVs are also copied. Replicate this backup
folder to a second device; an on-NAS backup does not protect against NAS loss.

To restore, stop containers using `sudo docker compose ... stop`, save a copy of
the current `data/db`, copy database files from the selected backup to
`data/db/` and its taxonomy directory to `data/sector_rotation/`, then run
`./deploy.sh`. Never restore while SQLite is being written.

## Access and checks

After a successful deployment the expected Tailnet URL is
`http://100.101.52.91:8080`; confirm with a live check. The API has no direct
host port. Several API endpoints can write data and the app has no login, so do
not forward a router port or enable a public Cloudflare Tunnel yet. Public
access requires authentication, rate limiting, and write/job route restrictions.

```bash
curl -fsS http://100.101.52.91:8080/health
curl -fsS http://100.101.52.91:8080/api/stocks/status
curl -fsS 'http://100.101.52.91:8080/api/stocks/search?q=2330'
sudo docker compose --env-file .env -f current/compose.yaml \
  run --rm --no-deps --entrypoint python scheduler -m apps.worker.daily_update --dry-run
```

The dry run does not change market data. The real run writes
`logs/daily_update.jsonl`; its last state is `logs/nas_scheduler.json`.

To inspect broker import backlog after an update:

```bash
sudo docker compose --env-file .env -f current/compose.yaml \
  exec scheduler python -m apps.worker.import_broker_csv_folder --missing-only --dry-run
curl -fsS http://100.101.52.91:8080/api/broker/overview
```
