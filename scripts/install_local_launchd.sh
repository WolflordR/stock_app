#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.tradelab.local-daily-update"
SOURCE_PLIST="${PROJECT_ROOT}/deploy/launchd/${LABEL}.plist"
TARGET_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${TARGET_DIR}/${LABEL}.plist"

LAUNCHD_LOG_DIR="${HOME}/Library/Logs/TradeLab"
mkdir -p "${TARGET_DIR}" "${LAUNCHD_LOG_DIR}" "${PROJECT_ROOT}/logs/local_daily_update"

if [[ ! -f "${PROJECT_ROOT}/.env.local" ]]; then
  cp "${PROJECT_ROOT}/.env.local.example" "${PROJECT_ROOT}/.env.local"
fi

"/usr/bin/python3" - "${SOURCE_PLIST}" "${TARGET_PLIST}" "${PROJECT_ROOT}" "${HOME}" <<'PY'
import pathlib
import sys

source, target, project_root, home = map(pathlib.Path, sys.argv[1:])
contents = source.read_text(encoding="utf-8")
contents = contents.replace("__TRADE_PROJECT_ROOT__", str(project_root))
contents = contents.replace("__TRADE_HOME__", str(home))
target.write_text(contents, encoding="utf-8")
PY
plutil -lint "${TARGET_PLIST}" >/dev/null
chmod 644 "${TARGET_PLIST}"

launchctl bootout "gui/$(id -u)" "${TARGET_PLIST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${TARGET_PLIST}"
launchctl enable "gui/$(id -u)/${LABEL}"

echo "Installed ${LABEL}"
echo "Schedule: weekdays 18:30"
echo "Config: ${PROJECT_ROOT}/.env.local"
echo "Run logs: ${PROJECT_ROOT}/logs/local_daily_update"
echo "Launch errors: ${LAUNCHD_LOG_DIR}/launchd.err.log"
