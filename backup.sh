#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CODE_DIR="$BASE_DIR/current"
ENV_FILE="$BASE_DIR/.env"
[ -f "$ENV_FILE" ] && [ -f "$CODE_DIR/compose.yaml" ] || { echo "Missing NAS .env or current release" >&2; exit 1; }
LABEL="${1:-manual}"
case "$LABEL" in
  *[!a-zA-Z0-9_-]*|'') echo "Invalid backup label" >&2; exit 1 ;;
esac
sudo docker compose --project-name trade --env-file "$ENV_FILE" -f "$CODE_DIR/compose.yaml" \
  run --rm --no-deps --entrypoint python api -m apps.worker.backup_databases --label "$LABEL"
