# Local Mac Schedule

This project uses `launchd` for Mac local scheduled updates.

## What It Runs

The local schedule runs:

```bash
scripts/local_daily_update.sh
```

Default behavior:

- Back up configured DB files.
- Refresh price cache for every stock when `TRADE_DAILY_PRICE_SCOPE=all`.
- Import broker branch CSV files if `data/raw/broker/twse/YYYY-MM-DD/` exists.
- Write logs to `logs/local_daily_update/`.

Taiwan daily prices are guarded against intraday writes: before 18:00 Taipei time, today's daily K row is not treated as confirmed.

## Configure

Create local config:

```bash
cp .env.local.example .env.local
```

Edit `.env.local`:

```text
TRADE_DAILY_PRICE_SCOPE=all
TRADE_DAILY_PRICE_STOCKS=2330,2317,2454
TRADE_DAILY_PRICE_DAYS=1825
TRADE_DAILY_PRICE_FORCE=0
TRADE_DAILY_IMPORT_BROKER=1
```

If full-market updates take too long, switch back to a small list:

```text
TRADE_DAILY_PRICE_SCOPE=list
TRADE_DAILY_PRICE_STOCKS=2330,2317,2454
```

## Install Schedule

```bash
scripts/install_local_launchd.sh
```

Default schedule:

```text
Monday-Friday 18:30
```

## Run Once Now

```bash
scripts/run_local_daily_update_now.sh
```

or:

```bash
make update
```

## Check Logs

```bash
ls logs/local_daily_update
tail -n 80 logs/local_daily_update/$(date +%F).log
```

or:

```bash
make log
```

## Uninstall Schedule

```bash
scripts/uninstall_local_launchd.sh
```
