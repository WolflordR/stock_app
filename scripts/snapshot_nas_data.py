"""Create a transactionally consistent copy of local data for first NAS transfer."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    target = args.target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"Snapshot target must be empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in sorted(SOURCE.rglob("*")):
        if not source.is_file() or source.is_symlink():
            continue
        if source.name.endswith((".db-wal", ".db-shm")):
            continue
        relative = source.relative_to(SOURCE)
        if source.suffix == ".db":
            if source.stat().st_size == 0:
                continue
            destination = target / "db" / relative.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(source) as original, sqlite3.connect(destination) as snapshot:
                original.backup(snapshot)
                if snapshot.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError(f"SQLite integrity check failed: {source}")
        else:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        copied.append(str(destination.relative_to(target)))
    print(json.dumps({"target": str(target), "file_count": len(copied), "files": copied}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
