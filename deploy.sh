#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CODE_DIR="$BASE_DIR/current"
ENV_FILE="$BASE_DIR/.env"

[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 1; }
[ -f "$CODE_DIR/compose.yaml" ] || { echo "Missing $CODE_DIR/compose.yaml" >&2; exit 1; }
set -a
. "$ENV_FILE"
set +a
[ "${TRADE_NAS_ROOT:-}" = "$BASE_DIR" ] || { echo "TRADE_NAS_ROOT must equal $BASE_DIR" >&2; exit 1; }
[ -f "$BASE_DIR/data/sector_rotation/flow_rotation_spec_v3.json" ] || { echo "Missing stock taxonomy data" >&2; exit 1; }
[ -s "$BASE_DIR/data/db/stocks.db" ] || { echo "Missing stocks.db; transfer the data snapshot first" >&2; exit 1; }

compose() {
  sudo docker compose --project-name trade --env-file "$ENV_FILE" -f "$CODE_DIR/compose.yaml" "$@"
}

mkdir -p "$BASE_DIR/logs" "$BASE_DIR/backups"
export COMPOSE_PARALLEL_LIMIT=1
sudo -v
compose config -q
compose build api
compose build web
"$BASE_DIR/backup.sh" pre-deploy
compose up -d --no-build --remove-orphans

URL="http://${TRADE_BIND_IP:-127.0.0.1}:${TRADE_WEB_PORT:-8080}"
attempt=0
while [ "$attempt" -lt 60 ]; do
  if curl -fsS --max-time 4 "$URL/health" >/dev/null && curl -fsS --max-time 8 "$URL/api/stocks/status" >/dev/null; then
    echo "Trade Lab is ready: $URL"
    compose ps
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 3
done
compose ps >&2
compose logs --tail=100 api web scheduler >&2
echo "Deployment health check failed" >&2
exit 1
