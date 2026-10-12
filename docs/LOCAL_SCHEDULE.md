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
- Import broker branch CSV files not yet in the broker database from every dated folder under `data/raw/broker/twse/`.
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

The project is under `~/Desktop`, which macOS protects. The scheduled job runs
through `/bin/bash`; macOS must allow that executable to read Desktop files.
If `~/Library/Logs/TradeLab/launchd.err.log` says `Operation not permitted`,
open **System Settings → Privacy & Security → Full Disk Access**, add `/bin/bash`
(use Command-Shift-G in the file chooser), and enable it. This is a macOS setting
that must be changed by the Mac user. Then run:

```bash
scripts/install_local_launchd.sh
launchctl kickstart -k "gui/$(id -u)/com.tradelab.local-daily-update"
```

Check that `launchd.err.log` has no new permission error and that today's run
log records `finished_at`. Do not kickstart while a manual update is running,
because that would start a second update against the same databases.

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
tail -n 80 "$HOME/Library/Logs/TradeLab/launchd.err.log"
```

or:

```bash
make log
```

## Uninstall Schedule

```bash
scripts/uninstall_local_launchd.sh
```
