from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime

from modules.core.project_paths import backups_path, db_path
from packages.trade_core.data_files import ALL_DB_FILES


def backup_databases(*, label: str | None = None) -> dict[str, object]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"{timestamp}-{label}" if label else timestamp
    backup_dir = backups_path(backup_name)
    backup_dir.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    for filename in ALL_DB_FILES:
        source = db_path(filename)
        target = backup_dir / filename
        if not source.exists():
            missing.append({"name": filename, "path": str(source)})
            continue
        shutil.copy2(source, target)
        copied.append({"name": filename, "source": str(source), "target": str(target)})

    return {
        "backup_dir": str(backup_dir),
        "copied_count": len(copied),
        "missing_count": len(missing),
        "copied": copied,
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up configured Trade database files.")
    parser.add_argument("--label", default=None, help="Optional suffix for the backup folder name.")
    args = parser.parse_args()

    result = backup_databases(label=args.label)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
