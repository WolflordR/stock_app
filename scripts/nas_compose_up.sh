#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${PROJECT_ROOT}/scripts/load_nas_env.sh"

cd "${PROJECT_ROOT}/infra"
exec docker compose up -d --build
