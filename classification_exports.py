from __future__ import annotations

import csv

import pandas as pd

from classification_queries import get_company_profiles_df, get_company_theme_membership_df
from classification_refresh import THEME_OVERRIDE_PATH, _load_existing_override_row_details


def build_theme_coverage_report():
    profiles_df = get_company_profiles_df()
    tech_industry_names = {
        "半導體業",
        "電腦及週邊設備業",
        "光電業",
        "通信網路業",
        "電子零組件業",
        "電子通路業",
        "資訊服務業",
        "其他電子業",
        "數位雲端",
    }

    tech_df = profiles_df[profiles_df["industry"].isin(tech_industry_names)].copy()
    tech_df["theme_count"] = tech_df["themes"].apply(len)
    covered_df = tech_df[tech_df["theme_count"] > 0].copy()
    uncovered_df = tech_df[tech_df["theme_count"] == 0].copy()

    source_summary_df = get_company_theme_membership_df()
    if source_summary_df.empty:
        source_counts_df = pd.DataFrame(columns=["分類來源", "檔數"])
    else:
        source_counts_df = (
            source_summary_df.groupby("source")["code"]
            .nunique()
            .reset_index(name="檔數")
            .rename(columns={"source": "分類來源"})
            .sort_values("檔數", ascending=False)
            .reset_index(drop=True)
        )

    uncovered_summary_df = (
        uncovered_df.groupby("industry")["code"]
        .count()
        .reset_index(name="未分類檔數")
        .rename(columns={"industry": "官方產業"})
        .sort_values(["未分類檔數", "官方產業"], ascending=[False, True])
        .reset_index(drop=True)
    )

    return {
        "tech_total": int(len(tech_df)),
        "covered_count": int(len(covered_df)),
        "uncovered_count": int(len(uncovered_df)),
        "coverage_pct": (float(len(covered_df)) / float(len(tech_df)) * 100.0) if len(tech_df) else 0.0,
        "source_counts_df": source_counts_df,
        "uncovered_summary_df": uncovered_summary_df,
        "uncovered_examples_df": uncovered_df[["code", "name_zh", "industry"]]
        .rename(columns={"code": "代碼", "name_zh": "名稱", "industry": "官方產業"})
        .head(80)
        .reset_index(drop=True),
    }


def export_full_market_theme_override_csv():
    profiles_df = get_company_profiles_df().copy()
    if profiles_df.empty:
        return {"rows": 0, "market_total": 0, "path": str(THEME_OVERRIDE_PATH)}

    profiles_df["code"] = profiles_df["code"].astype(str).str.zfill(4)
    profiles_df["industry"] = profiles_df["industry"].fillna("").astype(str).str.strip()
    market_df = profiles_df.sort_values(["industry", "code"]).reset_index(drop=True)

    theme_df = get_company_theme_membership_df().copy()
    if not theme_df.empty:
        theme_df["code"] = theme_df["code"].astype(str).str.zfill(4)

    existing_row_details = _load_existing_override_row_details()
    csv_rows = []

    for _, profile in market_df.iterrows():
        code = profile["code"]
        name_zh = str(profile["name_zh"] or "").strip()
        market = str(profile["market"] or "").strip()
        official_industry = str(profile["industry"] or "").strip()

        company_theme_df = theme_df[theme_df["code"] == code].copy() if not theme_df.empty else pd.DataFrame()
        current_themes = sorted(company_theme_df["theme"].astype(str).str.strip().unique().tolist()) if not company_theme_df.empty else []
        current_theme_text = "｜".join(current_themes)

        if current_themes:
            for theme_name in current_themes:
                detail = existing_row_details.get((code, theme_name), {})
                csv_rows.append(
                    {
                        "code": code,
                        "theme": theme_name,
                        "enabled": detail.get("enabled") or "1",
                        "note": detail.get("note") or "current classified theme",
                        "name_zh": detail.get("name_zh") or name_zh,
                        "market": detail.get("market") or market,
                        "official_industry": detail.get("official_industry") or official_industry,
                        "current_themes": detail.get("current_themes") or current_theme_text,
                    }
                )
        else:
            detail = existing_row_details.get((code, ""), {})
            csv_rows.append(
                {
                    "code": code,
                    "theme": "",
                    "enabled": detail.get("enabled") or "0",
                    "note": detail.get("note") or "unassigned placeholder",
                    "name_zh": detail.get("name_zh") or name_zh,
                    "market": detail.get("market") or market,
                    "official_industry": detail.get("official_industry") or official_industry,
                    "current_themes": detail.get("current_themes") or "",
                }
            )

    fieldnames = ["code", "theme", "enabled", "note", "name_zh", "market", "official_industry", "current_themes"]
    with THEME_OVERRIDE_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    return {
        "rows": int(len(csv_rows)),
        "market_total": int(len(market_df)),
        "path": str(THEME_OVERRIDE_PATH),
    }


def export_full_tech_theme_override_csv():
    return export_full_market_theme_override_csv()
