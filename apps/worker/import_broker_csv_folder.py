from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from modules.core.project_paths import raw_data_path
from modules.data_sources.official_broker_import import import_official_broker_csv


def _extract_stock_code(path: Path) -> str | None:
    match = re.search(r"(?<!\d)(\d{4,6})(?!\d)", path.stem)
    return match.group(1) if match else None


def _extract_trade_date(path: Path) -> str | None:
    for parent in path.parents:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parent.name):
            return parent.name
    return None


def import_broker_csv_folder(
    *,
    root: str | Path | None = None,
    market: str = "TWSE",
    trade_date: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    progress_every: int = 0,
) -> dict[str, Any]:
    base_root = Path(root) if root else raw_data_path("broker") / market.lower()
    scan_root = base_root / trade_date if trade_date else base_root
    csv_files = sorted(scan_root.rglob("*.csv"))
    if limit:
        csv_files = csv_files[: int(limit)]

    imported: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for index, csv_path in enumerate(csv_files, start=1):
        stock_code = _extract_stock_code(csv_path)
        file_trade_date = trade_date or _extract_trade_date(csv_path)
        if not stock_code:
            skipped.append({"file": str(csv_path), "reason": "檔名找不到股票代碼"})
            continue
        if not file_trade_date:
            skipped.append({"file": str(csv_path), "reason": "路徑找不到 YYYY-MM-DD 日期"})
            continue
        if dry_run:
            imported.append(
                {
                    "market": market.upper(),
                    "trade_date": file_trade_date,
                    "stock_code": stock_code,
                    "raw_file_name": csv_path.name,
                    "row_count": 0,
                    "dry_run": True,
                }
            )
            continue
        try:
            imported.append(
                import_official_broker_csv(
                    csv_path,
                    market=market.upper(),
                    trade_date=file_trade_date,
                    stock_code=stock_code,
                    source="TWSE_CSV_FOLDER" if market.upper() == "TWSE" else "TPEX_CSV_FOLDER",
                )
            )
        except Exception as exc:
            failed.append({"file": str(csv_path), "reason": str(exc)})
        if progress_every and index % progress_every == 0:
            print(
                f"進度 {index}/{len(csv_files)}：匯入 {len(imported)}，"
                f"失敗 {len(failed)}，略過 {len(skipped)}",
                flush=True,
            )

    return {
        "root": str(scan_root),
        "market": market.upper(),
        "trade_date": trade_date or "",
        "file_count": len(csv_files),
        "imported_count": len(imported),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "imported": imported[:20],
        "failed": failed[:20],
        "skipped": skipped[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import manually downloaded broker branch CSV files.")
    parser.add_argument("--root", default=None, help="Folder to scan. Defaults to data/raw/broker/{market}.")
    parser.add_argument("--market", default="TWSE", choices=["TWSE", "TPEX"], help="Market code.")
    parser.add_argument("--date", default=None, help="Trade date folder, for example 2026-09-04.")
    parser.add_argument("--limit", type=int, default=None, help="Import only the first N files.")
    parser.add_argument("--dry-run", action="store_true", help="Preview files without writing the database.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N files.")
    args = parser.parse_args()

    result = import_broker_csv_folder(
        root=args.root,
        market=args.market,
        trade_date=args.date,
        limit=args.limit,
        dry_run=args.dry_run,
        progress_every=args.progress_every,
    )
    print(
        f"掃描 {result['root']}：檔案 {result['file_count']}，"
        f"匯入 {result['imported_count']}，失敗 {result['failed_count']}，略過 {result['skipped_count']}"
    )
    if result["failed"]:
        print("失敗範例：")
        for item in result["failed"][:5]:
            print(f"- {item['file']}: {item['reason']}")
    if result["skipped"]:
        print("略過範例：")
        for item in result["skipped"][:5]:
            print(f"- {item['file']}: {item['reason']}")


if __name__ == "__main__":
    main()
