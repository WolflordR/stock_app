"""Read-only reconciliation audit of the original TDCC tier rows."""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd

from modules.ownership_research.data import CHIP_DB, DB_PATH


def anomalous_reports(*, chip_path: Path = CHIP_DB, research_path: Path = DB_PATH) -> pd.DataFrame:
    """Return one row per malformed report without changing either database."""
    with sqlite3.connect(chip_path) as chip, sqlite3.connect(research_path) as research:
        raw = pd.read_sql_query("""SELECT stock_id,report_date,COUNT(*) AS tier_count,
            MIN(tier) AS min_tier,MAX(tier) AS max_tier,
            SUM(CASE WHEN tier BETWEEN 1 AND 15 THEN shares ELSE 0 END) AS holder_tier_shares,
            MAX(CASE WHEN tier=16 THEN shares END) AS adjustment_shares,
            MAX(CASE WHEN tier=17 THEN shares END) AS total_shares,
            SUM(CASE WHEN tier BETWEEN 1 AND 16 THEN reported_pct ELSE 0 END) AS tier_pct_sum,
            MIN(shares) AS min_shares,MIN(reported_pct) AS min_pct,
            MAX(reported_pct) AS max_pct,MIN(source_url) AS source_url
            FROM stock_ownership_distribution_weekly GROUP BY stock_id,report_date""", chip)
        meta = pd.read_sql_query("SELECT stock_id,report_date,valid,quality_reason FROM research_ownership_weekly_meta", research)
    if raw.empty:
        return pd.DataFrame(columns=["stock_id", "report_date", "year", "source_type", "error_type", "share_difference"])
    frame = raw.merge(meta, on=["stock_id", "report_date"], how="left", validate="one_to_one")
    frame["share_difference"] = frame["holder_tier_shares"] - frame["adjustment_shares"] - frame["total_shares"]
    frame["difference_pct_of_total"] = frame["share_difference"] / frame["total_shares"] * 100
    frame["year"] = frame["report_date"].str[:4]
    frame["source_type"] = frame["source_url"].str.contains("tdcc-opendata-archive", regex=False).map(
        {True: "third_party_archive", False: "tdcc_first_observed"})
    frame["error_type"] = "shares_do_not_reconcile"
    frame.loc[(frame["tier_count"] != 17) | (frame["min_tier"] != 1) | (frame["max_tier"] != 17), "error_type"] = "incomplete_tiers"
    frame.loc[(frame["total_shares"].isna()) | (frame["total_shares"] <= 0) | (frame["min_shares"] < 0), "error_type"] = "invalid_quantity"
    frame.loc[(frame["min_pct"] < 0) | (frame["max_pct"] > 100), "error_type"] = "invalid_reported_percentage"
    frame.loc[frame["valid"].isna(), "error_type"] = "not_indexed"
    return frame.loc[frame["valid"].ne(1)].sort_values(["report_date", "stock_id"]).reset_index(drop=True)


def anomaly_summary(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {"report_count": 0, "years": {}, "sources": {}, "error_types": {}, "top_stocks": []}
    counts = Counter(frame["stock_id"])
    return {
        "report_count": len(frame),
        "years": frame.groupby("year").size().astype(int).to_dict(),
        "sources": frame.groupby("source_type").size().astype(int).to_dict(),
        "error_types": frame.groupby("error_type").size().astype(int).to_dict(),
        "positive_difference": int(frame["share_difference"].gt(0).sum()),
        "negative_difference": int(frame["share_difference"].lt(0).sum()),
        "difference_over_0_01pct": int(frame["difference_pct_of_total"].abs().gt(0.01).sum()),
        "top_stocks": [{"stock_id": code, "reports": count} for code, count in counts.most_common(20)],
    }


def tier16_reconciliation_audit(*, chip_path: Path = CHIP_DB) -> pd.DataFrame:
    """Explain the old 1–16 sum false positives without altering source rows."""
    with sqlite3.connect(chip_path) as conn:
        frame = pd.read_sql_query("""SELECT stock_id,report_date,
            SUM(CASE WHEN tier BETWEEN 1 AND 15 THEN shares ELSE 0 END) AS holder_tier_shares,
            MAX(CASE WHEN tier=16 THEN shares END) AS adjustment_shares,
            MAX(CASE WHEN tier=17 THEN shares END) AS total_shares,
            COUNT(*) AS tier_count,MIN(source_url) AS source_url
            FROM stock_ownership_distribution_weekly GROUP BY stock_id,report_date""", conn)
    if frame.empty:
        return frame
    frame["legacy_excess_shares"] = frame["holder_tier_shares"] + frame["adjustment_shares"] - frame["total_shares"]
    frame["corrected_residual_shares"] = frame["holder_tier_shares"] - frame["adjustment_shares"] - frame["total_shares"]
    frame["source_type"] = frame["source_url"].str.contains("tdcc-opendata-archive", regex=False).map(
        {True: "third_party_archive", False: "tdcc_first_observed"})
    frame["year"] = frame["report_date"].str[:4]
    return frame.loc[frame["legacy_excess_shares"].gt(0)].sort_values(["report_date", "stock_id"]).reset_index(drop=True)
