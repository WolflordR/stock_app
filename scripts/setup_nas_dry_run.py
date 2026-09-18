#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.trade_core.data_files import ALL_DB_FILES, DATA_CONFIG_FILES  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a local NAS-like data folder for Trade Lab dry-run.")
    parser.add_argument(
        "--target",
        default="/tmp/trade_nas",
        help="Target data directory. Use ${TRADE_NAS_ROOT}/data for Docker-style NAS layout.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing target files.")
    parser.add_argument("--copy-raw", action="store_true", help="Copy data/raw files such as broker CSV archives.")
    return parser.parse_args()


def copy_file(source: Path, target: Path, *, force: bool) -> dict[str, object]:
    if not source.exists():
        return {"name": source.name, "source": str(source), "target": str(target), "status": "missing_source"}
    if target.exists() and not force:
        return {"name": source.name, "source": str(source), "target": str(target), "status": "kept_existing"}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"name": source.name, "source": str(source), "target": str(target), "status": "copied"}


def copy_tree(source: Path, target: Path, *, force: bool) -> dict[str, object]:
    if not source.exists():
        return {"name": source.name, "source": str(source), "target": str(target), "status": "missing_source"}
    if target.exists() and not force:
        return {"name": source.name, "source": str(source), "target": str(target), "status": "kept_existing"}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return {"name": source.name, "source": str(source), "target": str(target), "status": "copied"}


def main() -> int:
    args = parse_args()
    target_root = Path(args.target).expanduser().resolve()
    nas_root = target_root.parent if target_root.name == "data" else target_root
    data_dir = PROJECT_ROOT / "data"
    db_dir = target_root / "db"

    for directory in [
        target_root,
        db_dir,
        target_root / "raw",
        target_root / "processed",
        target_root / "cache",
        nas_root / "logs",
        nas_root / "backups",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    copied = []
    for filename in ALL_DB_FILES:
        copied.append(copy_file(data_dir / filename, db_dir / filename, force=args.force))
    for filename in DATA_CONFIG_FILES:
        copied.append(copy_file(data_dir / filename, target_root / filename, force=args.force))
    if args.copy_raw:
        copied.append(copy_tree(data_dir / "raw", target_root / "raw", force=args.force))

    env = {
        "TRADE_DATA_DIR": str(target_root),
        "TRADE_DB_DIR": str(db_dir),
        "TRADE_RAW_DATA_DIR": str(target_root / "raw"),
        "TRADE_PROCESSED_DATA_DIR": str(target_root / "processed"),
        "TRADE_CACHE_DIR": str(target_root / "cache"),
        "TRADE_LOGS_DIR": str(nas_root / "logs"),
        "TRADE_BACKUPS_DIR": str(nas_root / "backups"),
    }
    payload = {"target_root": str(target_root), "env": env, "files": copied}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
