from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from modules.industry.classification_refresh import ENGLISH_ALIAS_OVERRIDES
from modules.industry.industry_taxonomy import THEME_DEFINITIONS
from modules.market_map.market_map_taxonomy import GROUP_DEFINITIONS
from modules.market_map.market_map_taxonomy import MARKET_MAP_TAXONOMY_VERSION
from modules.market_map.market_map_taxonomy import build_seed_topics
from modules.market_map.market_map_taxonomy import resolve_fallback_topic_name
from modules.market_map.market_map_taxonomy import resolve_group_name
from modules.data_sources.revenue_data import get_latest_monthly_revenue
from modules.data_sources.stock_db import DB_PATH as STOCK_DB_PATH
from modules.data_sources.stock_db import ensure_stock_db


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "market_map.db"
THEME_OVERRIDE_PATH = PROJECT_ROOT / "industry_theme_overrides.csv"
TAIWAN_MARKETS = {"TWSE", "TPEx"}
REGION_SCOPE = "TW_ONLY"


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_market_map_db():
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_groups (
                group_name TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                is_tech INTEGER NOT NULL,
                description TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_topics (
                topic_name TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                group_name TEXT NOT NULL,
                parent_industry TEXT,
                topic_type TEXT NOT NULL,
                is_tech INTEGER NOT NULL,
                description TEXT,
                news_query TEXT,
                sort_order INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_topic_keywords (
                topic_name TEXT NOT NULL,
                keyword TEXT NOT NULL,
                keyword_normalized TEXT NOT NULL,
                keyword_type TEXT NOT NULL,
                PRIMARY KEY (topic_name, keyword_normalized)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_companies (
                code TEXT PRIMARY KEY,
                name_zh TEXT NOT NULL,
                full_name_zh TEXT,
                market TEXT,
                yfinance_symbol TEXT,
                official_industry TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_company_aliases (
                code TEXT NOT NULL,
                alias TEXT NOT NULL,
                alias_normalized TEXT NOT NULL,
                language TEXT NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY (code, alias_normalized)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_topic_company_assignments (
                code TEXT NOT NULL,
                topic_name TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL,
                note TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (code, topic_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_topic_daily_snapshots (
                snapshot_date TEXT NOT NULL,
                group_name TEXT NOT NULL,
                topic_name TEXT NOT NULL,
                parent_industry TEXT,
                description TEXT,
                news_query TEXT,
                topic_type TEXT,
                company_count INTEGER NOT NULL,
                up_count INTEGER NOT NULL,
                down_count INTEGER NOT NULL,
                flat_count INTEGER NOT NULL,
                avg_change_pct REAL,
                five_day_change_pct REAL,
                total_volume REAL,
                total_turnover REAL,
                volume_ratio REAL,
                turnover_ratio REAL,
                heat_score REAL,
                representative_stocks TEXT,
                top_leaders TEXT,
                top_laggards TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_date, topic_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_group_daily_snapshots (
                snapshot_date TEXT NOT NULL,
                group_name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                is_tech INTEGER NOT NULL,
                topic_count INTEGER NOT NULL,
                company_count INTEGER NOT NULL,
                avg_change_pct REAL,
                five_day_change_pct REAL,
                avg_volume_ratio REAL,
                avg_turnover_ratio REAL,
                total_turnover REAL,
                heat_score REAL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_date, group_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_component_daily_snapshots (
                snapshot_date TEXT NOT NULL,
                topic_name TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                market TEXT,
                yfinance_symbol TEXT,
                official_industry TEXT,
                source TEXT,
                confidence REAL,
                change_pct REAL,
                volume REAL,
                turnover_value REAL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_date, topic_name, code)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_topic_event_snapshots (
                snapshot_date TEXT NOT NULL,
                topic_name TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                company_count INTEGER NOT NULL,
                risk_event_count INTEGER NOT NULL,
                board_event_count INTEGER NOT NULL,
                capital_event_count INTEGER NOT NULL,
                conference_event_count INTEGER NOT NULL,
                operational_event_count INTEGER NOT NULL,
                latest_event_at TEXT,
                top_event_titles TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_date, topic_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_topic_event_items (
                snapshot_date TEXT NOT NULL,
                topic_name TEXT NOT NULL,
                event_key TEXT NOT NULL,
                source TEXT NOT NULL,
                source_type TEXT NOT NULL,
                company_code TEXT,
                company_name TEXT,
                market TEXT,
                event_date TEXT,
                event_time TEXT,
                event_at TEXT,
                title TEXT NOT NULL,
                detail TEXT,
                event_type TEXT NOT NULL,
                severity_score REAL NOT NULL,
                url TEXT,
                matched_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_date, topic_name, event_key)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_topics_group ON map_topics(group_name, sort_order, topic_name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_assignments_topic ON map_topic_company_assignments(topic_name, code)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_company_aliases_norm ON map_company_aliases(alias_normalized)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_topic_daily_group ON map_topic_daily_snapshots(snapshot_date, group_name, heat_score)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_component_daily_topic ON map_component_daily_snapshots(snapshot_date, topic_name, turnover_value)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_topic_event_snapshot_date ON map_topic_event_snapshots(snapshot_date, event_count)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_topic_event_items_topic ON map_topic_event_items(snapshot_date, topic_name, event_at)"
        )


def _normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _load_securities_df():
    ensure_stock_db()
    with sqlite3.connect(STOCK_DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT code, name_zh, full_name_zh, market, yfinance_symbol
            FROM securities
            ORDER BY code
            """,
            conn,
        )


def _load_company_profiles_df():
    securities_df = _load_securities_df()
    securities_df = securities_df[securities_df["market"].isin(TAIWAN_MARKETS)].copy()
    securities_df["market_priority"] = securities_df["market"].map({"TWSE": 0, "TPEx": 1}).fillna(9)
    securities_df = (
        securities_df.sort_values(["code", "market_priority", "yfinance_symbol"])
        .drop_duplicates(subset=["code"], keep="first")
        .drop(columns=["market_priority"])
    )

    revenue_df = get_latest_monthly_revenue()
    if revenue_df.empty:
        industry_df = pd.DataFrame(columns=["code", "official_industry"])
    else:
        industry_df = revenue_df[["code", "industry"]].copy()
        industry_df["code"] = industry_df["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(4)
        industry_df["official_industry"] = industry_df["industry"].fillna("").astype(str).str.strip()
        industry_df = industry_df[industry_df["official_industry"] != ""].drop_duplicates(subset=["code"], keep="last")
        industry_df = industry_df.drop(columns=["industry"])

    profiles_df = securities_df.merge(industry_df, on="code", how="left")
    profiles_df["code"] = profiles_df["code"].astype(str).str.zfill(4)
    profiles_df["official_industry"] = profiles_df["official_industry"].fillna("").astype(str).str.strip()
    return profiles_df


def _load_manual_override_rows(valid_topic_names):
    if not THEME_OVERRIDE_PATH.exists():
        return []

    rows = []
    with THEME_OVERRIDE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = str(row.get("code") or "").strip().zfill(4)
            topic_name = _normalize_text(row.get("theme"))
            enabled_text = str(row.get("enabled") or "1").strip().lower()
            note = _normalize_text(row.get("note"))

            if enabled_text in {"0", "false", "no", "n"}:
                continue
            if not (len(code) == 4 and code.isdigit() and topic_name):
                continue
            if topic_name not in valid_topic_names:
                continue

            rows.append(
                {
                    "code": code,
                    "topic_name": topic_name,
                    "note": note,
                }
            )
    return rows


def refresh_market_map_db():
    init_market_map_db()
    profiles_df = _load_company_profiles_df()
    updated_at = datetime.now().isoformat(timespec="seconds")
    profiles_df["updated_at"] = updated_at

    seed_topics = build_seed_topics()
    topic_map = {topic["topic_name"]: dict(topic) for topic in seed_topics}

    for industry in sorted(profiles_df["official_industry"].dropna().astype(str).unique()):
        if not industry:
            continue
        fallback_topic_name = resolve_fallback_topic_name(industry)
        if fallback_topic_name in topic_map:
            continue
        group_name = resolve_group_name(fallback_topic_name, industry, False)
        topic_map[fallback_topic_name] = {
            "topic_name": fallback_topic_name,
            "display_name": fallback_topic_name,
            "group_name": group_name,
            "parent_industry": industry,
            "topic_type": "fallback",
            "is_tech": False,
            "description": "由官方產業別自動補上的綜合題材。",
            "news_query": "",
            "sort_order": 9000 + len(topic_map),
            "keywords": [],
            "aliases": [],
            "codes": [],
        }

    valid_topic_names = set(topic_map.keys())
    manual_override_rows = _load_manual_override_rows(valid_topic_names)

    alias_rows = []
    alias_lookup = {}
    for _, row in profiles_df.iterrows():
        code = str(row["code"]).zfill(4)
        aliases = {
            _normalize_text(row["name_zh"]),
            _normalize_text(row["full_name_zh"]),
        }
        aliases.update(_normalize_text(alias) for alias in ENGLISH_ALIAS_OVERRIDES.get(code, []))
        aliases = {alias for alias in aliases if alias}
        for alias in aliases:
            has_english = bool(re.search(r"[A-Za-z]", alias))
            alias_normalized = alias.lower() if has_english else alias
            alias_rows.append(
                (
                    code,
                    alias,
                    alias_normalized,
                    "en" if has_english else "zh",
                    "name_seed",
                )
            )
            alias_lookup[alias_normalized] = code

    assignment_map = {}

    def upsert_assignment(code, topic_name, source, confidence, note):
        normalized_code = str(code).zfill(4)
        key = (normalized_code, topic_name)
        candidate = {
            "code": normalized_code,
            "topic_name": topic_name,
            "source": source,
            "confidence": float(confidence),
            "note": note,
            "updated_at": updated_at,
        }
        current = assignment_map.get(key)
        if current is None or candidate["confidence"] > current["confidence"]:
            assignment_map[key] = candidate

    for topic in seed_topics:
        topic_name = topic["topic_name"]
        for code in topic["codes"]:
            upsert_assignment(code, topic_name, "seed_code", 1.0, "taxonomy seed code")
        for alias in topic["aliases"]:
            normalized_alias = _normalize_text(alias)
            if not normalized_alias:
                continue
            lookup_key = normalized_alias.lower() if re.search(r"[A-Za-z]", normalized_alias) else normalized_alias
            matched_code = alias_lookup.get(lookup_key)
            if matched_code:
                upsert_assignment(matched_code, topic_name, "seed_alias", 0.95, normalized_alias)

    for override_row in manual_override_rows:
        upsert_assignment(
            override_row["code"],
            override_row["topic_name"],
            "manual_override",
            1.2,
            override_row.get("note") or "manual override",
        )

    assigned_codes = {item["code"] for item in assignment_map.values()}
    for _, row in profiles_df.iterrows():
        code = str(row["code"]).zfill(4)
        if code in assigned_codes:
            continue
        fallback_topic_name = resolve_fallback_topic_name(row.get("official_industry"))
        if not fallback_topic_name:
            continue
        upsert_assignment(
            code,
            fallback_topic_name,
            "official_bucket",
            0.2,
            "fallback official industry bucket",
        )

    groups_by_name = {}
    for group in GROUP_DEFINITIONS:
        groups_by_name[group["name"]] = dict(group)
    for topic in topic_map.values():
        group_name = topic["group_name"]
        if group_name not in groups_by_name:
            groups_by_name[group_name] = {
                "name": group_name,
                "sort_order": 9000,
                "is_tech": bool(topic["is_tech"]),
                "description": "自動補上的產業分組。",
            }

    topic_rows = sorted(topic_map.values(), key=lambda item: (groups_by_name[item["group_name"]]["sort_order"], item["sort_order"], item["topic_name"]))
    keyword_rows = []
    for topic in topic_rows:
        for keyword in topic.get("keywords", []):
            keyword_rows.append(
                (
                    topic["topic_name"],
                    keyword,
                    keyword.lower() if re.search(r"[A-Za-z]", keyword) else keyword,
                    "keyword",
                )
            )
        for alias in topic.get("aliases", []):
            keyword_rows.append(
                (
                    topic["topic_name"],
                    alias,
                    alias.lower() if re.search(r"[A-Za-z]", alias) else alias,
                    "alias",
                )
            )

    assignment_rows = [
        (
            item["code"],
            item["topic_name"],
            item["source"],
            item["confidence"],
            item["note"],
            item["updated_at"],
        )
        for item in sorted(assignment_map.values(), key=lambda item: (item["topic_name"], item["code"]))
    ]

    with _get_connection() as conn:
        conn.execute("DELETE FROM map_groups")
        conn.execute("DELETE FROM map_topics")
        conn.execute("DELETE FROM map_topic_keywords")
        conn.execute("DELETE FROM map_companies")
        conn.execute("DELETE FROM map_company_aliases")
        conn.execute("DELETE FROM map_topic_company_assignments")
        conn.executemany(
            """
            INSERT INTO map_groups (group_name, display_name, sort_order, is_tech, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["name"],
                    item["name"],
                    int(item["sort_order"]),
                    1 if item["is_tech"] else 0,
                    item.get("description") or "",
                    updated_at,
                )
                for item in sorted(groups_by_name.values(), key=lambda item: (item["sort_order"], item["name"]))
            ],
        )
        conn.executemany(
            """
            INSERT INTO map_topics (
                topic_name, display_name, group_name, parent_industry, topic_type,
                is_tech, description, news_query, sort_order, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    topic["topic_name"],
                    topic["display_name"],
                    topic["group_name"],
                    topic["parent_industry"],
                    topic["topic_type"],
                    1 if topic["is_tech"] else 0,
                    topic.get("description") or "",
                    topic.get("news_query") or "",
                    int(topic["sort_order"]),
                    updated_at,
                )
                for topic in topic_rows
            ],
        )
        conn.executemany(
            """
            INSERT INTO map_topic_keywords (topic_name, keyword, keyword_normalized, keyword_type)
            VALUES (?, ?, ?, ?)
            """,
            keyword_rows,
        )
        conn.executemany(
            """
            INSERT INTO map_companies (
                code, name_zh, full_name_zh, market, yfinance_symbol, official_industry, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            profiles_df[
                ["code", "name_zh", "full_name_zh", "market", "yfinance_symbol", "official_industry", "updated_at"]
            ].itertuples(index=False, name=None),
        )
        conn.executemany(
            """
            INSERT INTO map_company_aliases (code, alias, alias_normalized, language, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            alias_rows,
        )
        conn.executemany(
            """
            INSERT INTO map_topic_company_assignments (code, topic_name, source, confidence, note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            assignment_rows,
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('last_sync_at', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (updated_at,),
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('taxonomy_version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (MARKET_MAP_TAXONOMY_VERSION,),
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('seed_theme_count', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(len(THEME_DEFINITIONS)),),
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('region_scope', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (REGION_SCOPE,),
        )
        conn.commit()

    return get_market_map_status()


def get_market_map_status():
    init_market_map_db()
    with _get_connection() as conn:
        counts = {
            "group_count": conn.execute("SELECT COUNT(*) FROM map_groups").fetchone()[0],
            "topic_count": conn.execute("SELECT COUNT(*) FROM map_topics").fetchone()[0],
            "company_count": conn.execute("SELECT COUNT(*) FROM map_companies").fetchone()[0],
            "assignment_count": conn.execute("SELECT COUNT(*) FROM map_topic_company_assignments").fetchone()[0],
        }
        meta = conn.execute("SELECT key, value FROM metadata").fetchall()

    metadata = {row["key"]: row["value"] for row in meta}
    return counts | {
        "last_sync_at": metadata.get("last_sync_at"),
        "taxonomy_version": metadata.get("taxonomy_version"),
        "region_scope": metadata.get("region_scope"),
    }


def ensure_market_map_db(max_cache_age_hours=12):
    init_market_map_db()
    status = get_market_map_status()
    if int(status["company_count"]) == 0 or int(status["topic_count"]) == 0:
        return refresh_market_map_db()

    last_sync_at = status.get("last_sync_at")
    stale = True
    if last_sync_at:
        try:
            stale = datetime.fromisoformat(last_sync_at) < datetime.now() - timedelta(hours=max_cache_age_hours)
        except Exception:
            stale = True

    if status.get("taxonomy_version") != MARKET_MAP_TAXONOMY_VERSION or stale:
        return refresh_market_map_db()
    return status
