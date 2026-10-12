"""Bounded, resumable third-party TDCC archive import for exploratory research."""
from __future__ import annotations

import csv
import hashlib
import io
import sqlite3
from collections import Counter
from pathlib import Path

import requests

from modules.data_sources.chip_trends import TDCC_ARCHIVE_API, TDCC_ARCHIVE_RAW, parse_tdcc
from modules.ownership_research.data import CHIP_DB, DB_PATH, connect, now_iso


def archive_files(year: int, client: requests.Session) -> list[str]:
    response = client.get(f"{TDCC_ARCHIVE_API}/{year}", timeout=25)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    listing = response.json()
    if not isinstance(listing, list):
        raise ValueError("TDCC mirror directory format changed")
    return sorted(item["name"] for item in listing if item.get("type") == "file"
                  and item.get("name", "").startswith(f"{year}-")
                  and item["name"].endswith(".csv"))


def parse_archive_content(content: bytes, requested: str) -> list[dict]:
    day, rows = parse_tdcc(list(csv.DictReader(io.StringIO(content.decode("utf-8-sig")))))
    if day != requested:
        raise ValueError(f"archive date mismatch: {day} != {requested}")
    tier_counts = Counter(row["stock_id"] for row in rows)
    tier_keys = {(row["stock_id"], row["tier"]) for row in rows}
    if (len(tier_counts) < 1000 or set(tier_counts.values()) != {17}
            or len(tier_keys) != len(rows)):
        raise ValueError("incomplete TDCC archive week")
    if any(row["shares"] < 0 for row in rows):
        raise ValueError("negative TDCC share quantity")
    return rows


def backfill_tdcc_archives(*, first_year: int = 2020, last_year: int = 2026,
                           max_weeks: int = 20, chip_path: Path = CHIP_DB,
                           research_path: Path = DB_PATH,
                           session: requests.Session | None = None) -> dict:
    """Import missing complete weeks; record SHA/status. Never replace stored raw rows."""
    if first_year > last_year or first_year < 2016 or max_weeks < 1:
        raise ValueError("invalid year range or week budget")
    client = session or requests.Session()
    outcome: dict = {"available_years": {}, "unavailable_years": [], "downloaded_weeks": 0,
                     "imported_weeks": 0, "rows": 0, "cached_weeks": 0, "errors": []}
    with sqlite3.connect(chip_path) as chip, connect(research_path) as research:
        chip.row_factory = sqlite3.Row
        for year in range(first_year, last_year + 1):
            try:
                files = archive_files(year, client)
            except Exception as exc:
                outcome["errors"].append({"year": year, "error": str(exc)})
                continue
            if not files:
                outcome["unavailable_years"].append(year)
                continue
            outcome["available_years"][str(year)] = len(files)
            for filename in files:
                day = filename[:-4]
                manifest = research.execute("""SELECT status,row_count FROM research_source_fetches
                    WHERE source_key='TDCC_ARCHIVE' AND market='ALL' AND requested_date=?""", (day,)).fetchone()
                if manifest and manifest["status"] == "ok":
                    outcome["cached_weeks"] += 1
                    continue
                if outcome["downloaded_weeks"] >= max_weeks:
                    return outcome
                outcome["downloaded_weeks"] += 1
                url = f"{TDCC_ARCHIVE_RAW}/{year}/{filename}"
                fetched_at = now_iso()
                digest = None
                rows = []
                try:
                    response = client.get(url, timeout=50)
                    response.raise_for_status()
                    digest = hashlib.sha256(response.content).hexdigest()
                    rows = parse_archive_content(response.content, day)
                    existing = chip.execute("""SELECT stock_id,tier,holder_count,shares,reported_pct
                        FROM stock_ownership_distribution_weekly WHERE report_date=?""", (day,)).fetchall()
                    if existing:
                        stored = {(row["stock_id"], row["tier"]): (row["holder_count"], row["shares"], row["reported_pct"])
                                  for row in existing}
                        incoming = {(row["stock_id"], row["tier"]): (row["holder_count"], row["shares"], row["reported_pct"])
                                    for row in rows}
                        if stored != incoming:
                            raise ValueError("existing week differs from archive; raw rows preserved")
                        outcome["cached_weeks"] += 1
                    else:
                        with chip:
                            chip.executemany("""INSERT INTO stock_ownership_distribution_weekly
                                (stock_id,report_date,tier,holder_count,shares,reported_pct,source_url,updated_at)
                                VALUES (?,?,?,?,?,?,?,?)""",
                                [(row["stock_id"], day, row["tier"], row["holder_count"], row["shares"],
                                  row["reported_pct"], url, fetched_at) for row in rows])
                        outcome["imported_weeks"] += 1
                        outcome["rows"] += len(rows)
                    status, error = "ok", None
                except Exception as exc:
                    status, error = "error", f"{type(exc).__name__}: {exc}"
                    outcome["errors"].append({"week": day, "error": error})
                with research:
                    research.execute("""INSERT INTO research_source_fetches
                        (source_key,market,requested_date,source_url,fetched_at,status,row_count,content_sha256,error)
                        VALUES ('TDCC_ARCHIVE','ALL',?,?,?,?,?,?,?)
                        ON CONFLICT(source_key,market,requested_date) DO UPDATE SET
                        source_url=excluded.source_url,fetched_at=excluded.fetched_at,status=excluded.status,
                        row_count=excluded.row_count,content_sha256=excluded.content_sha256,error=excluded.error""",
                        (day, url, fetched_at, status, len(rows), digest, error))
                    research.execute("""INSERT INTO research_source_fetch_attempts
                        (source_key,market,requested_date,source_url,fetched_at,status,row_count,content_sha256,error)
                        VALUES ('TDCC_ARCHIVE','ALL',?,?,?,?,?,?,?)""",
                        (day, url, fetched_at, status, len(rows), digest, error))
    return outcome
