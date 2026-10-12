"""Official MOPS basic EPS snapshots, stored separately from price valuation data."""
from __future__ import annotations

import csv
import io
import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from modules.core.http_utils import request_text
from modules.core.project_paths import db_path


DB_PATH = db_path("financial_eps.db")
REPORT_TYPES = ("ci", "basi", "bd", "fh", "ins", "mim")
MARKETS = {"TWSE": "L", "TPEx": "O"}


def source_url(market: str, report_type: str) -> str:
    return f"https://mopsfin.twse.com.tw/opendata/t187ap06_{MARKETS[market]}_{report_type}.csv"


def _roc_date(value: str) -> str | None:
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 7:
        return None
    year, month, day = int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:])
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def parse_eps_csv(text: str, market: str, report_type: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not {"年度", "季別", "公司代號"}.issubset(reader.fieldnames):
        raise ValueError("MOPS EPS columns changed")
    eps_column = next((name for name in reader.fieldnames if name.startswith("基本每股盈餘")), None)
    if not eps_column:
        raise ValueError("MOPS basic EPS column missing")
    rows: list[dict] = []
    for row in reader:
        code = str(row.get("公司代號") or "").strip()
        year = str(row.get("年度") or "").strip()
        quarter = str(row.get("季別") or "").strip()
        raw_eps = str(row.get(eps_column) or "").strip().replace(",", "")
        if not re.fullmatch(r"\d{4}", code) or not year.isdigit() or quarter not in {"1", "2", "3", "4"}:
            continue
        try:
            eps = float(raw_eps)
        except ValueError:
            continue
        if not math.isfinite(eps) or not 90 <= int(year) <= 200:
            continue
        rows.append({
            "market": market, "code": code, "report_year": int(year) + 1911,
            "report_quarter": int(quarter), "basic_eps_ytd": eps,
            "output_date": _roc_date(row.get("出表日期") or ""),
            "source_url": source_url(market, report_type),
        })
    return rows


def _connect(path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS stock_eps_quarterly (
        market TEXT NOT NULL, code TEXT NOT NULL, report_year INTEGER NOT NULL,
        report_quarter INTEGER NOT NULL, basic_eps_ytd REAL NOT NULL,
        output_date TEXT, source_url TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (market, code, report_year, report_quarter)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_eps_latest ON stock_eps_quarterly(market, code, report_year DESC, report_quarter DESC)")
    return conn


def refresh_eps(*, path: str | Path = DB_PATH) -> dict:
    """Upsert each valid source independently; missing/new-quarter companies keep prior reports."""
    inserted = 0
    errors: list[str] = []
    for market in MARKETS:
        for report_type in REPORT_TYPES:
            url = source_url(market, report_type)
            try:
                text = request_text(url, encoding="utf-8-sig", headers={"Accept": "text/csv,*/*;q=0.8"})
                rows = parse_eps_csv(text, market, report_type)
                if report_type == "ci" and len(rows) < 100:
                    raise ValueError("ordinary-company snapshot is unexpectedly small")
                if not rows:
                    continue  # Some industries have no companies in one market.
                with _connect(path) as conn:
                    conn.executemany("""INSERT INTO stock_eps_quarterly
                        (market, code, report_year, report_quarter, basic_eps_ytd, output_date, source_url, updated_at)
                        VALUES (:market, :code, :report_year, :report_quarter, :basic_eps_ytd, :output_date, :source_url, :updated_at)
                        ON CONFLICT(market, code, report_year, report_quarter) DO UPDATE SET
                        basic_eps_ytd=excluded.basic_eps_ytd, output_date=excluded.output_date,
                        source_url=excluded.source_url, updated_at=excluded.updated_at""",
                        [{**row, "updated_at": datetime.now().isoformat(timespec="seconds")} for row in rows])
                inserted += len(rows)
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                errors.append(f"{market}/{report_type}: {exc}")
    if inserted == 0:
        raise RuntimeError("No valid MOPS EPS rows were downloaded: " + "; ".join(errors))
    return {"rows": inserted, "errors": errors}


def get_latest_eps(code: str, market: str, *, path: str | Path = DB_PATH) -> dict | None:
    if market not in MARKETS or not re.fullmatch(r"\d{4}", str(code)) or not Path(path).exists():
        return None
    with _connect(path) as conn:
        row = conn.execute("""SELECT report_year, report_quarter, basic_eps_ytd, output_date, source_url
            FROM stock_eps_quarterly WHERE market=? AND code=?
            ORDER BY report_year DESC, report_quarter DESC LIMIT 1""", (market, code)).fetchone()
    return dict(row) if row else None
