#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE="$BASE_DIR/.env"
[ -f "$ENV_FILE" ] && [ -L "$BASE_DIR/current" ] || { echo "Run this from an existing NAS installation" >&2; exit 1; }
set -a
. "$ENV_FILE"
set +a
[ "${TRADE_NAS_ROOT:-}" = "$BASE_DIR" ] || { echo "Unexpected TRADE_NAS_ROOT" >&2; exit 1; }

REF="${TRADE_UPDATE_REF:-main}"
case "$REF" in
  *[!a-zA-Z0-9._/-]*|*..*|'') echo "Invalid update ref" >&2; exit 1 ;;
esac
mkdir -p "$BASE_DIR/releases"
ARCHIVE=$(mktemp "$BASE_DIR/releases/.download.XXXXXX")
trap 'rm -f "$ARCHIVE"' EXIT
curl -fLsS --retry 3 --max-time 180 \
  "https://github.com/WolflordR/stock_app/archive/refs/heads/$REF.tar.gz" -o "$ARCHIVE"
SHORT=$(sha256sum "$ARCHIVE" | cut -c1-12)
RELEASE="$BASE_DIR/releases/$(date +%Y%m%d-%H%M%S)-$SHORT"
mkdir -p "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE" --strip-components=1
[ -f "$RELEASE/compose.yaml" ] || { echo "GitHub revision lacks NAS deployment files; push Mac changes first" >&2; exit 1; }

OLD_RELEASE=$(readlink "$BASE_DIR/current")
new_compose() {
  sudo docker compose --project-name trade --env-file "$ENV_FILE" -f "$RELEASE/compose.yaml" "$@"
}
old_compose() {
  sudo docker compose --project-name trade --env-file "$ENV_FILE" -f "$BASE_DIR/current/compose.yaml" "$@"
}
rollback() {
  echo "Update failed; restoring $OLD_RELEASE" >&2
  ln -sfn "$OLD_RELEASE" "$BASE_DIR/current"
  old_compose build api
  old_compose build web
  old_compose up -d --no-build --remove-orphans
}

export COMPOSE_PARALLEL_LIMIT=1
sudo -v
new_compose config -q
new_compose build api
new_compose build web
"$BASE_DIR/backup.sh" pre-update
ln -sfn "$RELEASE" "$BASE_DIR/current"
if ! new_compose up -d --no-build --remove-orphans; then
  rollback
  exit 1
fi
URL="http://${TRADE_BIND_IP:-127.0.0.1}:${TRADE_WEB_PORT:-8080}"
attempt=0
while [ "$attempt" -lt 40 ]; do
  if curl -fsS --max-time 4 "$URL/health" >/dev/null && curl -fsS --max-time 8 "$URL/api/stocks/status" >/dev/null; then
    for script in deploy.sh update.sh backup.sh; do
      if [ -f "$RELEASE/$script" ]; then
        cp "$RELEASE/$script" "$BASE_DIR/$script"
        chmod 755 "$BASE_DIR/$script"
      fi
    done
    echo "Updated to GitHub $REF archive $SHORT: $URL"
    new_compose ps
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 3
done
rollback
echo "Update failed health checks; previous code restored. Review the pre-update database backup before schema rollback." >&2
exit 1
