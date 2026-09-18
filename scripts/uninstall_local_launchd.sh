#!/usr/bin/env bash
set -euo pipefail

LABEL="com.tradelab.local-daily-update"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if [[ -f "${TARGET_PLIST}" ]]; then
  launchctl bootout "gui/$(id -u)" "${TARGET_PLIST}" >/dev/null 2>&1 || true
  rm -f "${TARGET_PLIST}"
fi

echo "Uninstalled ${LABEL}"
