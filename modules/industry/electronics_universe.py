"""Official TWSE/TPEx electronics universe and package taxonomy import."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.core.http_utils import request_bytes
from modules.core.project_paths import data_path, db_path
from modules.data_sources.stock_db import init_stock_db

DB_PATH = db_path("sector_rotation.db")
STOCK_DB_PATH = db_path("stocks.db")
PACKAGE_DIR = data_path("sector_rotation")
TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_CSV_URL = "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv"
ELECTRONIC_CODES = frozenset(str(code) for code in range(24, 32))
INDUSTRY_NAMES = {
    "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業",
}


@contextmanager
def _connection(path: Path = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_sector_db(path: Path = DB_PATH) -> None:
    with _connection(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS official_electronics (
                market TEXT NOT NULL, stock_id TEXT NOT NULL, name TEXT NOT NULL,
                company_name TEXT, official_industry_code TEXT NOT NULL,
                website TEXT, source_date TEXT, classification_state TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, last_seen_at TEXT NOT NULL,
                PRIMARY KEY (market, stock_id)
            );
            CREATE INDEX IF NOT EXISTS idx_official_electronics_code ON official_electronics(stock_id);
            CREATE TABLE IF NOT EXISTS sector_categories (
                slug TEXT PRIMARY KEY, type TEXT NOT NULL, name_zh TEXT NOT NULL, parent_slug TEXT
            );
            CREATE TABLE IF NOT EXISTS sector_themes (
                slug TEXT PRIMARY KEY, name_zh TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS stock_sector_map (
                market TEXT NOT NULL, stock_id TEXT NOT NULL, category_slug TEXT NOT NULL,
                relation TEXT NOT NULL, source TEXT NOT NULL, confidence REAL,
                source_url TEXT, verified_at TEXT,
                PRIMARY KEY (market, stock_id, category_slug)
            );
            CREATE TABLE IF NOT EXISTS stock_theme_map (
                market TEXT NOT NULL, stock_id TEXT NOT NULL, theme_slug TEXT NOT NULL,
                source TEXT NOT NULL, confidence REAL, source_url TEXT,
                valid_from TEXT, valid_to TEXT, verified_at TEXT,
                PRIMARY KEY (market, stock_id, theme_slug)
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sector_daily_metrics (
                trade_date TEXT NOT NULL, window_days INTEGER NOT NULL,
                category_slug TEXT NOT NULL, constituent_count INTEGER NOT NULL,
                observed_count INTEGER NOT NULL, advance_ratio REAL,
                median_return REAL, equal_weight_return REAL,
                volume_expansion_ratio REAL, breakout_ratio REAL,
                relative_strength REAL, turnover_momentum REAL,
                rotation_score REAL, rank_eligible INTEGER NOT NULL,
                PRIMARY KEY(trade_date, window_days, category_slug)
            );
        """)


def _csv_file(name: str) -> list[dict[str, str]]:
    with (PACKAGE_DIR / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _download_json(url: str) -> list[dict]:
    rows = json.loads(request_bytes(url, timeout=30).decode("utf-8-sig"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Official source returned no rows: {url}")
    return rows


def _download_csv(url: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(request_bytes(url, timeout=30).decode("utf-8-sig"))))
    if not rows:
        raise ValueError(f"Official source returned no rows: {url}")
    return rows


def normalize_company(row: dict, market: str) -> dict | None:
    """Accept both MOPS Chinese CSV keys and TPEx OpenAPI English keys."""
    stock_id = str(row.get("SecuritiesCompanyCode") or row.get("公司代號") or "").strip()
    if not re.fullmatch(r"[1-9]\d{3}", stock_id):
        return None
    name = str(row.get("CompanyAbbreviation") or row.get("公司簡稱") or row.get("CompanyName") or row.get("公司名稱") or "").strip()
    if not name:
        return None
    industry_code = str(row.get("SecuritiesIndustryCode") or row.get("產業別") or "").strip().zfill(2)
    return {
        "market": market,
        "stock_id": stock_id,
        "name": name,
        "company_name": str(row.get("CompanyName") or row.get("公司名稱") or "").strip(),
        "official_industry_code": industry_code,
        "website": str(row.get("WebAddress") or row.get("網址") or "").strip(),
        "source_date": str(row.get("Date") or row.get("出表日期") or "").strip(),
    }


def fetch_official_companies() -> tuple[list[dict], dict[str, str]]:
    listed = _download_json(TWSE_URL)
    try:
        otc = _download_json(TPEX_URL)
        otc_source = TPEX_URL
        if not any(normalize_company(row, "TPEx") for row in otc):
            raise ValueError("TPEx OpenAPI schema did not contain company profiles")
    except (OSError, ValueError, json.JSONDecodeError):
        otc = _download_csv(TPEX_CSV_URL)
        otc_source = TPEX_CSV_URL
    rows = []
    for market, source in (("TWSE", listed), ("TPEx", otc)):
        normalized = [normalize_company(row, market) for row in source]
        normalized = [row for row in normalized if row is not None]
        if not normalized:
            raise ValueError(f"No common-stock company profiles from {market}")
        rows.extend(normalized)
    keys = [(row["market"], row["stock_id"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate official company identifiers")
    return rows, {"TWSE": TWSE_URL, "TPEx": otc_source}


def _export_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def import_official_companies(rows: list[dict], sources: dict[str, str], *, path: Path = DB_PATH, stock_path: Path | None = STOCK_DB_PATH, export: bool = True) -> dict:
    """Replace active membership only after both official markets validate."""
    electronic = sorted((row for row in rows if row["official_industry_code"] in ELECTRONIC_CODES), key=lambda row: (row["market"], row["stock_id"]))
    counts = {market: sum(row["market"] == market for row in electronic) for market in ("TWSE", "TPEx")}
    if min(counts.values()) == 0:
        raise ValueError(f"Incomplete official electronics source: {counts}")
    if len({(row["market"], row["stock_id"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate official company identifiers")
    if any(not re.fullmatch(r"\d{4}", row["stock_id"]) for row in rows):
        raise ValueError("Non-common-stock identifier in normalized source")

    init_sector_db(path)
    categories = _csv_file("taxonomy.csv")
    themes = _csv_file("themes.csv")
    seed = {row["stock_id"]: row for row in _csv_file("stock_seed.csv")}
    extras = _csv_file("stock_category_extra.csv")
    bootstrap = {row["official_industry_code"]: row["bootstrap_category_slug"] for row in _csv_file("official_industry_bootstrap.csv")}
    category_slugs = {row["slug"] for row in categories}
    if any(slug not in category_slugs for slug in bootstrap.values()):
        raise ValueError("Bootstrap category absent from taxonomy")
    now = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    with _connection(path) as conn:
        conn.executemany("INSERT INTO sector_categories(slug,type,name_zh,parent_slug) VALUES(?,?,?,?) ON CONFLICT(slug) DO UPDATE SET type=excluded.type,name_zh=excluded.name_zh,parent_slug=excluded.parent_slug", [(r["slug"], r["type"], r["name_zh"], r["parent_slug"] or None) for r in categories])
        conn.executemany("INSERT INTO sector_themes(slug,name_zh) VALUES(?,?) ON CONFLICT(slug) DO UPDATE SET name_zh=excluded.name_zh", [(r["theme_slug"], r["theme_name_zh"]) for r in themes])
        conn.execute("UPDATE official_electronics SET active=0")
        active_keys = {(row["market"], row["stock_id"]) for row in electronic}
        for row in electronic:
            curated = seed.get(row["stock_id"])
            manual_mapping = conn.execute("""SELECT 1 FROM stock_sector_map WHERE market=? AND stock_id=?
                AND source='manual_verified' LIMIT 1""", (row["market"], row["stock_id"])).fetchone()
            state = "taxonomy_mapped" if curated or manual_mapping else "official_only"
            conn.execute("""INSERT INTO official_electronics(market,stock_id,name,company_name,official_industry_code,website,source_date,classification_state,active,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?,1,?) ON CONFLICT(market,stock_id) DO UPDATE SET name=excluded.name,company_name=excluded.company_name,official_industry_code=excluded.official_industry_code,website=excluded.website,source_date=excluded.source_date,classification_state=excluded.classification_state,active=1,last_seen_at=excluded.last_seen_at""",
                (row["market"], row["stock_id"], row["name"], row["company_name"], row["official_industry_code"], row["website"], row["source_date"], state, now))
            conn.execute("DELETE FROM stock_sector_map WHERE market=? AND stock_id=? AND source IN ('official_bootstrap','curated_seed')", (row["market"], row["stock_id"]))
            conn.execute("DELETE FROM stock_theme_map WHERE market=? AND stock_id=? AND source='curated_seed'", (row["market"], row["stock_id"]))
            bucket = bootstrap[row["official_industry_code"]]
            conn.execute("INSERT OR IGNORE INTO stock_sector_map(market,stock_id,category_slug,relation,source) VALUES(?,?,?,'official_bucket','official_bootstrap')", (row["market"], row["stock_id"], bucket))
            if curated:
                slug = curated["primary_category_slug"]
                if slug not in category_slugs:
                    raise ValueError(f"Unknown curated category: {slug}")
                conn.execute("""INSERT INTO stock_sector_map(market,stock_id,category_slug,relation,source,confidence) VALUES(?,?,?,'primary','curated_seed',?)
                    ON CONFLICT(market,stock_id,category_slug) DO UPDATE SET relation='primary',source='curated_seed',confidence=excluded.confidence
                    WHERE stock_sector_map.source IN ('official_bootstrap','curated_seed')""",
                    (row["market"], row["stock_id"], slug, float(curated["confidence"])))
                for theme in filter(None, curated["theme_slugs"].split(";")):
                    conn.execute("INSERT OR IGNORE INTO stock_theme_map(market,stock_id,theme_slug,source,confidence) VALUES(?,?,?,'curated_seed',?)", (row["market"], row["stock_id"], theme, float(curated["confidence"])))
        for extra in extras:
            for market, stock_id in active_keys:
                if stock_id == extra["stock_id"]:
                    conn.execute("INSERT OR IGNORE INTO stock_sector_map(market,stock_id,category_slug,relation,source) VALUES(?,?,?,?,'curated_seed')", (market, stock_id, extra["category_slug"], extra["relation"]))
        for key, value in {"last_sync_at": now, "twse_source": sources["TWSE"], "tpex_source": sources["TPEx"], "twse_official_total": str(counts["TWSE"]), "tpex_official_total": str(counts["TPEx"])}.items():
            conn.execute("INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        imported = conn.execute("SELECT COUNT(*) FROM official_electronics WHERE active=1").fetchone()[0]
        if imported != len(electronic):
            raise ValueError(f"Coverage mismatch: official={len(electronic)} imported={imported}")

    if stock_path is not None:
        if stock_path == STOCK_DB_PATH:
            init_stock_db()
        with _connection(stock_path) as conn:
            conn.executemany("""INSERT INTO securities(code,name_zh,full_name_zh,market,yfinance_symbol,industry_code,updated_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(yfinance_symbol) DO UPDATE SET name_zh=excluded.name_zh,full_name_zh=excluded.full_name_zh,market=excluded.market,industry_code=excluded.industry_code,updated_at=excluded.updated_at""",
                [(r["stock_id"], r["name"], r["company_name"], r["market"], r["stock_id"] + (".TW" if r["market"] == "TWSE" else ".TWO"), r["official_industry_code"], now) for r in electronic])
    if export:
        fields = ["market", "stock_id", "name", "company_name", "official_industry_code", "website", "source_date"]
        _export_csv(data_path("all_listed_otc_companies.csv"), sorted(rows, key=lambda r: (r["market"], r["stock_id"])), fields)
        _export_csv(data_path("all_electronic_stocks.csv"), electronic, fields)
        export_electronics_classification(path)
    return get_electronics_coverage(path)


def sync_electronics_universe() -> dict:
    rows, sources = fetch_official_companies()
    source_counts = {market: sum(row["market"] == market and row["official_industry_code"] in ELECTRONIC_CODES for row in rows) for market in ("TWSE", "TPEx")}
    if any(count < 100 for count in source_counts.values()):
        raise ValueError(f"Official electronics snapshot is implausibly small: {source_counts}")
    previous = get_electronics_coverage()
    for market in ("TWSE", "TPEx"):
        prior = previous[f"{market.lower()}_official_total"]
        if prior and source_counts[market] < 0.9 * prior:
            raise ValueError(f"Official {market} electronics snapshot shrank unexpectedly: {prior} -> {source_counts[market]}")
    return import_official_companies(rows, sources)


def get_electronics_coverage(path: Path = DB_PATH) -> dict:
    init_sector_db(path)
    with _connection(path) as conn:
        metadata = dict(conn.execute("SELECT key,value FROM metadata").fetchall())
        counts = dict(conn.execute("SELECT market,COUNT(*) FROM official_electronics WHERE active=1 GROUP BY market").fetchall())
        states = dict(conn.execute("SELECT classification_state,COUNT(*) FROM official_electronics WHERE active=1 GROUP BY classification_state").fetchall())
        verified_themes = conn.execute("SELECT COUNT(DISTINCT market || ':' || stock_id) FROM stock_theme_map WHERE verified_at IS NOT NULL AND (valid_to IS NULL OR valid_to >= date('now'))").fetchone()[0]
    official_total = sum(int(metadata.get(f"{market.lower()}_official_total", 0)) for market in ("TWSE", "TPEx"))
    imported = sum(counts.values())
    return {
        "twse_official_total": int(metadata.get("twse_official_total", 0)),
        "tpex_official_total": int(metadata.get("tpex_official_total", 0)),
        "imported_total": imported,
        "taxonomy_mapped_total": states.get("taxonomy_mapped", 0),
        "taxonomy_mapped_pct": round(100 * states.get("taxonomy_mapped", 0) / imported, 2) if imported else 0,
        "official_only_total": states.get("official_only", 0),
        "official_only_pct": round(100 * states.get("official_only", 0) / imported, 2) if imported else 0,
        "needs_review_total": states.get("official_only", 0),
        "verified_theme_total": verified_themes,
        "verified_theme_pct": round(100 * verified_themes / imported, 2) if imported else 0,
        "last_sync_at": metadata.get("last_sync_at"),
        "coverage_ok": bool(official_total and imported == official_total and counts.get("TWSE", 0) == int(metadata.get("twse_official_total", 0)) and counts.get("TPEx", 0) == int(metadata.get("tpex_official_total", 0))),
    }


def export_electronics_classification(path: Path = DB_PATH) -> Path:
    """Flat review file; candidate themes remain clearly unverified."""
    with _connection(path) as conn:
        rows = [dict(row) for row in conn.execute("""SELECT e.market,e.stock_id,e.name,e.official_industry_code,
            e.classification_state,
            (SELECT GROUP_CONCAT(category_slug,';') FROM stock_sector_map m WHERE m.market=e.market AND m.stock_id=e.stock_id AND m.relation='primary') AS primary_category_slugs,
            (SELECT GROUP_CONCAT(category_slug,';') FROM stock_sector_map m WHERE m.market=e.market AND m.stock_id=e.stock_id AND m.relation!='primary' AND m.relation!='official_bucket') AS secondary_category_slugs,
            (SELECT GROUP_CONCAT(theme_slug,';') FROM stock_theme_map t WHERE t.market=e.market AND t.stock_id=e.stock_id AND t.verified_at IS NULL) AS unverified_theme_candidates,
            (SELECT GROUP_CONCAT(theme_slug,';') FROM stock_theme_map t WHERE t.market=e.market AND t.stock_id=e.stock_id AND t.verified_at IS NOT NULL) AS verified_themes,
            e.source_date FROM official_electronics e WHERE e.active=1 ORDER BY e.market,e.stock_id""")]
    for row in rows:
        row["official_industry_name"] = INDUSTRY_NAMES.get(row["official_industry_code"], "")
    destination = data_path("electronic_classification.csv")
    _export_csv(destination, rows, ["market", "stock_id", "name", "official_industry_code", "official_industry_name", "classification_state", "primary_category_slugs", "secondary_category_slugs", "unverified_theme_candidates", "verified_themes", "source_date"])
    return destination


def list_electronics(*, category_slug: str | None = None, path: Path = DB_PATH) -> list[dict]:
    init_sector_db(path)
    sql = """SELECT e.market,e.stock_id,e.name,e.official_industry_code,e.classification_state,
        GROUP_CONCAT(CASE WHEN m.relation != 'official_bucket' THEN m.category_slug END) AS category_slugs
        FROM official_electronics e LEFT JOIN stock_sector_map m ON m.market=e.market AND m.stock_id=e.stock_id
        WHERE e.active=1"""
    args: list[str] = []
    if category_slug:
        sql += " AND EXISTS(SELECT 1 FROM stock_sector_map x WHERE x.market=e.market AND x.stock_id=e.stock_id AND x.category_slug=?)"
        args.append(category_slug)
    sql += " GROUP BY e.market,e.stock_id ORDER BY e.market,e.stock_id"
    with _connection(path) as conn:
        return [dict(row) for row in conn.execute(sql, args)]


def list_sectors(path: Path = DB_PATH) -> list[dict]:
    init_sector_db(path)
    with _connection(path) as conn:
        return [dict(row) for row in conn.execute("""SELECT c.slug,c.type,c.name_zh,c.parent_slug,
            COUNT(DISTINCT e.market || ':' || e.stock_id) AS constituent_count
            FROM sector_categories c LEFT JOIN stock_sector_map m ON m.category_slug=c.slug
            LEFT JOIN official_electronics e ON e.market=m.market AND e.stock_id=m.stock_id AND e.active=1
            GROUP BY c.slug ORDER BY constituent_count DESC,c.slug""")]


def list_themes(path: Path = DB_PATH) -> list[dict]:
    init_sector_db(path)
    with _connection(path) as conn:
        return [dict(row) for row in conn.execute("""SELECT t.slug,t.name_zh,t.active,
            COUNT(DISTINCT m.market || ':' || m.stock_id) AS candidate_count,
            COUNT(DISTINCT CASE WHEN m.verified_at IS NOT NULL THEN m.market || ':' || m.stock_id END) AS verified_count
            FROM sector_themes t LEFT JOIN stock_theme_map m ON m.theme_slug=t.slug
            GROUP BY t.slug ORDER BY t.slug""")]


def set_theme_active(slug: str, active: bool, path: Path = DB_PATH) -> bool:
    init_sector_db(path)
    with _connection(path) as conn:
        cursor = conn.execute("UPDATE sector_themes SET active=? WHERE slug=?", (int(active), slug))
        return cursor.rowcount > 0
