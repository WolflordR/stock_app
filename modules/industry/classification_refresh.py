from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime

import pandas as pd

from modules.core.project_paths import data_path
from modules.industry.industry_taxonomy import THEME_DEFINITIONS
from modules.industry.industry_taxonomy import THEME_DEFINITIONS_VERSION
from modules.data_sources.revenue_data import get_latest_monthly_revenue
from modules.data_sources.stock_db import DB_PATH as STOCK_DB_PATH
from modules.data_sources.stock_db import ensure_stock_db

DB_PATH = data_path("company_links.db")
THEME_OVERRIDE_PATH = data_path("industry_theme_overrides.csv")

ENGLISH_ALIAS_OVERRIDES = {
    "2330": ["TSMC", "Taiwan Semiconductor"],
    "2317": ["Foxconn", "Hon Hai"],
    "2382": ["Quanta"],
    "3231": ["Wistron"],
    "2356": ["Inventec"],
    "6669": ["Wiwynn"],
    "3017": ["AVC"],
    "3324": ["Auras"],
    "3037": ["Unimicron"],
    "3189": ["Kinsus"],
    "8046": ["Nan Ya PCB"],
    "2337": ["Macronix"],
    "2408": ["Nanya Technology"],
    "2344": ["Winbond"],
    "8299": ["Phison"],
    "2451": ["Transcend"],
    "3260": ["ADATA"],
    "2308": ["Delta Electronics"],
    "2345": ["Accton"],
    "4908": ["Photonics", "Enablence"],
    "3711": ["ASE"],
}

FALLBACK_THEME_BY_INDUSTRY = {
    "水泥工業": "水泥建材 / 綜合",
    "食品工業": "食品民生 / 綜合",
    "塑膠工業": "塑化製品 / 綜合",
    "紡織纖維": "紡織纖維 / 綜合",
    "電機機械": "電機機械 / 綜合",
    "電器電纜": "電器電纜 / 綜合",
    "化學工業": "化學材料 / 綜合",
    "生技醫療業": "生技醫療 / 綜合",
    "玻璃陶瓷": "玻璃陶瓷 / 綜合",
    "鋼鐵工業": "鋼鐵材料 / 綜合",
    "橡膠工業": "橡膠製品 / 綜合",
    "汽車工業": "汽車零組件 / 綜合",
    "電子零組件業": "電子零組件 / 綜合",
    "電腦及週邊設備業": "電腦週邊設備 / 綜合",
    "半導體業": "半導體 / 綜合",
    "通信網路業": "通信網路 / 綜合",
    "電子通路業": "電子通路 / 綜合",
    "資訊服務業": "資訊服務 / 綜合",
    "其他電子業": "電子設備整合 / 綜合",
    "建材營造": "建材營造 / 綜合",
    "航運業": "航運物流 / 綜合",
    "觀光餐旅": "觀光餐旅 / 綜合",
    "金融保險業": "金融保險 / 綜合",
    "貿易百貨": "零售貿易 / 綜合",
    "油電燃氣業": "能源公用 / 綜合",
    "居家生活": "居家生活 / 綜合",
    "數位雲端": "數位雲端 / 綜合",
    "綠能環保": "綠能環保 / 綜合",
    "運動休閒": "運動休閒 / 綜合",
    "文化創意業": "文化創意 / 綜合",
    "農業科技": "農業科技 / 綜合",
    "存託憑證": "存託憑證 / 綜合",
    "金融業": "金融服務 / 綜合",
    "造紙工業": "造紙紙器 / 綜合",
    "其他": "綜合產業 / 綜合",
}

LEGACY_THEME_RENAMES = {
    "水泥工業 / 其他": "水泥建材 / 綜合",
    "食品工業 / 其他": "食品民生 / 綜合",
    "塑膠工業 / 其他": "塑化製品 / 綜合",
    "紡織纖維 / 其他": "紡織纖維 / 綜合",
    "電機機械 / 其他": "電機機械 / 綜合",
    "電器電纜 / 其他": "電器電纜 / 綜合",
    "化學工業 / 其他": "化學材料 / 綜合",
    "生技醫療業 / 其他": "生技醫療 / 綜合",
    "玻璃陶瓷 / 其他": "玻璃陶瓷 / 綜合",
    "鋼鐵工業 / 其他": "鋼鐵材料 / 綜合",
    "橡膠工業 / 其他": "橡膠製品 / 綜合",
    "汽車工業 / 其他": "汽車零組件 / 綜合",
    "電子零組件業 / 其他": "電子零組件 / 綜合",
    "電腦及週邊設備業 / 其他": "電腦週邊設備 / 綜合",
    "半導體業 / 其他": "半導體 / 綜合",
    "通信網路業 / 其他": "通信網路 / 綜合",
    "電子通路業 / 其他": "電子通路 / 綜合",
    "資訊服務業 / 其他": "資訊服務 / 綜合",
    "其他電子業 / 其他": "電子設備整合 / 綜合",
    "建材營造 / 其他": "建材營造 / 綜合",
    "航運業 / 其他": "航運物流 / 綜合",
    "觀光餐旅 / 其他": "觀光餐旅 / 綜合",
    "金融保險業 / 其他": "金融保險 / 綜合",
    "貿易百貨 / 其他": "零售貿易 / 綜合",
    "油電燃氣業 / 其他": "能源公用 / 綜合",
    "居家生活 / 其他": "居家生活 / 綜合",
    "數位雲端 / 其他": "數位雲端 / 綜合",
    "綠能環保 / 其他": "綠能環保 / 綜合",
    "運動休閒 / 其他": "運動休閒 / 綜合",
    "文化創意業 / 其他": "文化創意 / 綜合",
    "農業科技 / 其他": "農業科技 / 綜合",
    "存託憑證 / 其他": "存託憑證 / 綜合",
    "金融業 / 其他": "金融服務 / 綜合",
    "造紙工業 / 其他": "造紙紙器 / 綜合",
    "其他 / 其他": "綜合產業 / 綜合",
}


def _fallback_theme_name(industry):
    normalized_industry = str(industry or "").strip()
    if not normalized_industry:
        return "待確認 / 綜合標的"
    return FALLBACK_THEME_BY_INDUSTRY.get(normalized_industry, f"{normalized_industry} / 綜合")


def _normalize_theme_name(theme_name):
    normalized_theme = str(theme_name or "").strip()
    if not normalized_theme:
        return normalized_theme
    return LEGACY_THEME_RENAMES.get(normalized_theme, normalized_theme)


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_company_links_db():
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_profiles (
                code TEXT PRIMARY KEY,
                name_zh TEXT NOT NULL,
                full_name_zh TEXT,
                market TEXT,
                yfinance_symbol TEXT,
                industry TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_aliases (
                code TEXT NOT NULL,
                alias TEXT NOT NULL,
                alias_normalized TEXT NOT NULL,
                language TEXT NOT NULL,
                PRIMARY KEY (code, alias_normalized)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_theme_links (
                code TEXT NOT NULL,
                theme TEXT NOT NULL,
                PRIMARY KEY (code, theme)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_theme_assignments (
                code TEXT NOT NULL,
                theme TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL,
                note TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (code, theme)
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


def _normalize_alias(alias):
    raw = str(alias or "").strip()
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw).strip()


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


def _load_theme_override_rows():
    if not THEME_OVERRIDE_PATH.exists():
        return []

    valid_theme_names = {definition["theme"] for definition in THEME_DEFINITIONS}
    rows = []
    with THEME_OVERRIDE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = str(row.get("code") or "").strip().zfill(4)
            theme = _normalize_theme_name(row.get("theme"))
            enabled_text = str(row.get("enabled") or "1").strip().lower()
            note = str(row.get("note") or "").strip()
            if enabled_text in {"0", "false", "no", "n"}:
                continue
            if not (len(code) == 4 and code.isdigit() and theme):
                continue
            if theme not in valid_theme_names:
                continue
            rows.append(
                {
                    "code": code,
                    "theme": theme,
                    "note": note,
                }
            )
    return rows


def _load_existing_override_row_details():
    if not THEME_OVERRIDE_PATH.exists():
        return {}

    row_details = {}
    with THEME_OVERRIDE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = str(row.get("code") or "").strip().zfill(4)
            theme = _normalize_theme_name(row.get("theme"))
            enabled = str(row.get("enabled") or "").strip()
            note = str(row.get("note") or "").strip()
            name_zh = str(row.get("name_zh") or "").strip()
            market = str(row.get("market") or "").strip()
            official_industry = str(row.get("official_industry") or "").strip()
            current_themes = str(row.get("current_themes") or "").strip()
            if current_themes:
                current_themes = "｜".join(
                    _normalize_theme_name(theme_part)
                    for theme_part in current_themes.split("｜")
                    if str(theme_part).strip()
                )
            if not (len(code) == 4 and code.isdigit()):
                continue
            row_details[(code, theme)] = {
                "enabled": enabled or "1",
                "note": note,
                "name_zh": name_zh,
                "market": market,
                "official_industry": official_industry,
                "current_themes": current_themes,
            }
    return row_details


def refresh_company_links_db():
    init_company_links_db()
    securities_df = _load_securities_df()
    securities_df["market_priority"] = securities_df["market"].map({"TWSE": 0, "TPEx": 1}).fillna(9)
    securities_df = (
        securities_df.sort_values(["code", "market_priority", "yfinance_symbol"])
        .drop_duplicates(subset=["code"], keep="first")
        .drop(columns=["market_priority"])
    )
    revenue_df = get_latest_monthly_revenue()

    if revenue_df.empty:
        industry_df = pd.DataFrame(columns=["code", "industry"])
    else:
        industry_df = revenue_df[["code", "industry"]].copy()
        industry_df["code"] = industry_df["code"].astype(str).str.zfill(4)
        industry_df["industry"] = industry_df["industry"].fillna("").astype(str).str.strip()
        industry_df = industry_df[industry_df["industry"] != ""].drop_duplicates(subset=["code"], keep="last")

    profiles_df = securities_df.merge(industry_df, on="code", how="left")
    profiles_df["industry"] = profiles_df["industry"].fillna("").astype(str).str.strip()
    updated_at = datetime.now().isoformat(timespec="seconds")
    profiles_df["updated_at"] = updated_at

    alias_rows = []
    alias_lookup = {}
    for _, row in profiles_df.iterrows():
        code = str(row["code"]).zfill(4)
        aliases = {
            _normalize_alias(row["name_zh"]),
            _normalize_alias(row["full_name_zh"]),
        }
        aliases.update(_normalize_alias(alias) for alias in ENGLISH_ALIAS_OVERRIDES.get(code, []))
        aliases = {alias for alias in aliases if alias}
        for alias in aliases:
            has_english = bool(re.search(r"[A-Za-z]", alias))
            alias_rows.append(
                (
                    code,
                    alias,
                    alias.lower() if has_english else alias,
                    "en" if has_english else "zh",
                )
            )
            alias_lookup[(alias.lower() if has_english else alias)] = code

    theme_assignment_map = {}

    def _upsert_theme_assignment(code, theme_name, source, confidence, note):
        normalized_code = str(code).zfill(4)
        key = (normalized_code, theme_name)
        current = theme_assignment_map.get(key)
        candidate = {
            "code": normalized_code,
            "theme": theme_name,
            "source": source,
            "confidence": float(confidence),
            "note": note,
            "updated_at": updated_at,
        }
        if current is None or candidate["confidence"] > current["confidence"]:
            theme_assignment_map[key] = candidate

    for definition in THEME_DEFINITIONS:
        theme_name = definition["theme"]
        for code in definition.get("codes", []):
            _upsert_theme_assignment(
                code,
                theme_name,
                "seed_code",
                1.0,
                "taxonomy seed code",
            )
        for alias in definition.get("aliases", []):
            normalized_alias = _normalize_alias(alias)
            if not normalized_alias:
                continue
            lookup_key = normalized_alias.lower() if re.search(r"[A-Za-z]", normalized_alias) else normalized_alias
            matched_code = alias_lookup.get(lookup_key)
            if matched_code:
                _upsert_theme_assignment(
                    matched_code,
                    theme_name,
                    "seed_alias",
                    0.95,
                    normalized_alias,
                )

    for override_row in _load_theme_override_rows():
        _upsert_theme_assignment(
            override_row["code"],
            override_row["theme"],
            "manual_override",
            1.2,
            override_row.get("note") or "manual override",
        )

    assigned_codes = {assignment["code"] for assignment in theme_assignment_map.values()}
    for _, profile_row in profiles_df.iterrows():
        code = str(profile_row["code"]).zfill(4)
        if code in assigned_codes:
            continue
        fallback_theme = _fallback_theme_name(profile_row.get("industry"))
        if not fallback_theme:
            continue
        _upsert_theme_assignment(
            code,
            fallback_theme,
            "official_bucket",
            0.2,
            "fallback official industry bucket",
        )

    theme_rows = sorted((assignment["code"], assignment["theme"]) for assignment in theme_assignment_map.values())
    theme_assignment_rows = [
        (
            assignment["code"],
            assignment["theme"],
            assignment["source"],
            assignment["confidence"],
            assignment["note"],
            assignment["updated_at"],
        )
        for assignment in sorted(theme_assignment_map.values(), key=lambda item: (item["theme"], item["code"]))
    ]

    with _get_connection() as conn:
        conn.execute("DELETE FROM company_profiles")
        conn.execute("DELETE FROM company_aliases")
        conn.execute("DELETE FROM company_theme_links")
        conn.execute("DELETE FROM company_theme_assignments")
        conn.executemany(
            """
            INSERT INTO company_profiles (
                code, name_zh, full_name_zh, market, yfinance_symbol, industry, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            profiles_df[
                ["code", "name_zh", "full_name_zh", "market", "yfinance_symbol", "industry", "updated_at"]
            ].itertuples(index=False, name=None),
        )
        conn.executemany(
            """
            INSERT INTO company_aliases (code, alias, alias_normalized, language)
            VALUES (?, ?, ?, ?)
            """,
            alias_rows,
        )
        conn.executemany(
            """
            INSERT INTO company_theme_links (code, theme)
            VALUES (?, ?)
            """,
            theme_rows,
        )
        conn.executemany(
            """
            INSERT INTO company_theme_assignments (code, theme, source, confidence, note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            theme_assignment_rows,
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
            INSERT INTO metadata(key, value) VALUES ('theme_definitions_version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (THEME_DEFINITIONS_VERSION,),
        )
        conn.commit()

    from classification_queries import clear_query_caches

    clear_query_caches()
    return {
        "count": int(len(profiles_df)),
        "last_sync_at": updated_at,
    }


def ensure_company_links_db():
    init_company_links_db()
    with _get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM company_profiles").fetchone()
        count = int(row["count"]) if row else 0
        meta = conn.execute("SELECT value FROM metadata WHERE key = 'last_sync_at'").fetchone()
        theme_meta = conn.execute("SELECT value FROM metadata WHERE key = 'theme_definitions_version'").fetchone()

    if count == 0:
        return refresh_company_links_db()

    stock_status = ensure_stock_db()
    last_sync_at = meta["value"] if meta else None
    stale = True
    if last_sync_at:
        try:
            synced_dt = datetime.fromisoformat(last_sync_at)
            stale = synced_dt < datetime.now() - pd.Timedelta(hours=12)
        except Exception:
            stale = True

    theme_version = theme_meta["value"] if theme_meta else None
    if int(stock_status.get("count", 0)) != count or stale or theme_version != THEME_DEFINITIONS_VERSION:
        return refresh_company_links_db()
    return get_company_links_status()


def get_company_links_status():
    init_company_links_db()
    with _get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM company_profiles").fetchone()["count"]
        meta = conn.execute("SELECT value FROM metadata WHERE key = 'last_sync_at'").fetchone()
    return {
        "count": int(count),
        "last_sync_at": meta["value"] if meta else None,
    }
