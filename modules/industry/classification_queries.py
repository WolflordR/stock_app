from __future__ import annotations

import json
import re
from functools import lru_cache

import pandas as pd

from modules.industry.classification_refresh import ensure_company_links_db, _get_connection, refresh_company_links_db
from modules.industry.industry_taxonomy import THEME_DEFINITIONS


@lru_cache(maxsize=1)
def _load_company_profiles_df():
    ensure_company_links_db()
    with _get_connection() as conn:
        profiles_df = pd.read_sql_query(
            """
            SELECT p.code, p.name_zh, p.full_name_zh, p.market, p.yfinance_symbol, p.industry,
                   COALESCE(json_group_array(DISTINCT t.theme), '[]') AS themes_json
            FROM company_profiles p
            LEFT JOIN company_theme_assignments t ON p.code = t.code
            GROUP BY p.code, p.name_zh, p.full_name_zh, p.market, p.yfinance_symbol, p.industry
            ORDER BY p.code
            """,
            conn,
        )
    profiles_df["themes"] = profiles_df["themes_json"].apply(
        lambda value: [theme for theme in json.loads(value or "[]") if theme]
    )
    return profiles_df.drop(columns=["themes_json"])


@lru_cache(maxsize=1)
def _load_company_index():
    ensure_company_links_db()
    profiles_df = _load_company_profiles_df()
    profiles_map = {row["code"]: row for row in profiles_df.to_dict(orient="records")}

    with _get_connection() as conn:
        alias_df = pd.read_sql_query(
            """
            SELECT code, alias, alias_normalized, language
            FROM company_aliases
            ORDER BY LENGTH(alias) DESC, alias
            """,
            conn,
        )

    alias_records = alias_df.to_dict(orient="records")
    return profiles_map, alias_records


def clear_query_caches():
    _load_company_index.cache_clear()
    _load_company_profiles_df.cache_clear()


def get_company_profiles_df(force_refresh=False):
    if force_refresh:
        refresh_company_links_db()
    return _load_company_profiles_df().copy()


def get_company_official_industry_df(force_refresh=False):
    profiles_df = get_company_profiles_df(force_refresh=force_refresh)
    if profiles_df.empty:
        return pd.DataFrame(columns=["code", "industry"])

    mapping_df = profiles_df[["code", "industry"]].copy()
    mapping_df["code"] = mapping_df["code"].astype(str).str.zfill(4)
    mapping_df["industry"] = mapping_df["industry"].fillna("").astype(str).str.strip()
    mapping_df = mapping_df[mapping_df["industry"] != ""].drop_duplicates(subset=["code"], keep="last")
    return mapping_df.reset_index(drop=True)


def get_company_theme_membership_df(force_refresh=False):
    if force_refresh:
        refresh_company_links_db()
    ensure_company_links_db()
    with _get_connection() as conn:
        theme_df = pd.read_sql_query(
            """
            SELECT a.code, p.name_zh, p.full_name_zh, p.market, p.industry,
                   a.theme, a.source, a.confidence, a.note, a.updated_at
            FROM company_theme_assignments a
            JOIN company_profiles p ON p.code = a.code
            ORDER BY a.theme, a.code
            """,
            conn,
        )
    return theme_df


def extract_company_links_from_text(*texts, max_matches=8):
    profiles_map, alias_records = _load_company_index()
    combined_text = " ".join(str(text or "") for text in texts if text).strip()
    if not combined_text:
        return []

    lowered_text = combined_text.lower()
    seen_codes = set()
    matched_aliases = []
    matches = []

    for alias_record in alias_records:
        if len(matches) >= max_matches:
            break

        code = alias_record["code"]
        if code in seen_codes:
            continue

        alias = alias_record["alias"]
        alias_normalized = alias_record["alias_normalized"]
        language = alias_record["language"]
        if language == "en":
            if len(alias_normalized) < 4:
                continue
            if not re.search(rf"(?<![A-Za-z]){re.escape(alias_normalized)}(?![A-Za-z])", lowered_text):
                continue
        else:
            if len(alias) < 2 or alias not in combined_text:
                continue
            if any(alias in matched_alias or matched_alias in alias for matched_alias in matched_aliases):
                continue

        profile = profiles_map.get(code)
        if not profile:
            continue

        seen_codes.add(code)
        matched_aliases.append(alias)
        matches.append(
            {
                "code": code,
                "name_zh": profile["name_zh"],
                "full_name_zh": profile["full_name_zh"],
                "market": profile["market"],
                "industry": profile["industry"] or "未分類",
                "themes": profile["themes"],
                "matched_alias": alias,
            }
        )

    return matches


def infer_themes_from_text(*texts, company_links=None, max_themes=6):
    combined_text = " ".join(str(text or "") for text in texts if text).strip()
    lowered_text = combined_text.lower()
    theme_scores = {}

    if company_links:
        for company in company_links:
            for theme in company.get("themes", []):
                theme_scores[theme] = theme_scores.get(theme, 0) + 3

    for definition in THEME_DEFINITIONS:
        theme_name = definition["theme"]
        for keyword in definition.get("keywords", []):
            raw_keyword = str(keyword or "").strip()
            if not raw_keyword:
                continue
            if re.search(r"[A-Za-z]", raw_keyword):
                found = raw_keyword.lower() in lowered_text
            else:
                found = raw_keyword in combined_text
            if found:
                theme_scores[theme_name] = theme_scores.get(theme_name, 0) + 1

    ranked_themes = sorted(theme_scores.items(), key=lambda item: (-item[1], item[0]))
    return [theme for theme, _ in ranked_themes[:max_themes]]
