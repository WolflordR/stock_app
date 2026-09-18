#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.core.project_paths import (  # noqa: E402
    BACKUPS_DIR,
    CACHE_DIR,
    DATA_DIR,
    DB_DIR,
    LOGS_DIR,
    PROCESSED_DATA_DIR,
    PROJECT_ROOT,
    RAW_DATA_DIR,
    data_path,
    db_path,
)
from packages.trade_core.data_files import ALL_DB_FILES, DATA_CONFIG_FILES  # noqa: E402


def main() -> int:
    payload = {
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(DATA_DIR),
        "raw_data_dir": str(RAW_DATA_DIR),
        "processed_data_dir": str(PROCESSED_DATA_DIR),
        "db_dir": str(DB_DIR),
        "cache_dir": str(CACHE_DIR),
        "logs_dir": str(LOGS_DIR),
        "backups_dir": str(BACKUPS_DIR),
        "db_files": {
            name: {
                "path": str(db_path(name)),
                "exists": db_path(name).exists(),
            }
            for name in ALL_DB_FILES
        },
        "data_files": {
            name: {
                "path": str(data_path(name)),
                "exists": data_path(name).exists(),
            }
            for name in DATA_CONFIG_FILES
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
