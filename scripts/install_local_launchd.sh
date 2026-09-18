#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.tradelab.local-daily-update"
SOURCE_PLIST="${PROJECT_ROOT}/deploy/launchd/${LABEL}.plist"
TARGET_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${TARGET_DIR}/${LABEL}.plist"

mkdir -p "${TARGET_DIR}" "${PROJECT_ROOT}/logs/local_daily_update"

if [[ ! -f "${PROJECT_ROOT}/.env.local" ]]; then
  cp "${PROJECT_ROOT}/.env.local.example" "${PROJECT_ROOT}/.env.local"
fi

cp "${SOURCE_PLIST}" "${TARGET_PLIST}"
chmod 644 "${TARGET_PLIST}"

launchctl bootout "gui/$(id -u)" "${TARGET_PLIST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${TARGET_PLIST}"
launchctl enable "gui/$(id -u)/${LABEL}"

echo "Installed ${LABEL}"
echo "Schedule: weekdays 18:30"
echo "Config: ${PROJECT_ROOT}/.env.local"
echo "Logs: ${PROJECT_ROOT}/logs/local_daily_update"
