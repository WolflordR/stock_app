"""Point-in-time TDCC tier factors; no market price enters a factor."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from modules.ownership_research.data import CHIP_DB, DB_PATH

# Official tiers are strict 'greater than' thresholds, not inclusive lot counts.
TIER_START = {100: 10, 200: 11, 400: 12, 600: 13, 800: 14, 1000: 15}


@dataclass(frozen=True)
class FactorConfig:
    thresholds_lots: tuple[int, ...] = (400, 1000)
    change_weeks: tuple[int, ...] = (1, 4, 8)
    primary_threshold_lots: int = 1000
    small_holder_last_tier: int = 3  # tiers 1–3 = at most 10 board lots
    min_gap_days: int = 4
    max_gap_days: int = 10
    zscore_weeks: int = 12

    def __post_init__(self) -> None:
        if (not self.thresholds_lots or any(x not in TIER_START for x in self.thresholds_lots)
                or self.primary_threshold_lots not in self.thresholds_lots
                or not self.change_weeks or any(x < 1 for x in self.change_weeks)
                or not 1 <= self.small_holder_last_tier <= 9
                or not 1 <= self.min_gap_days <= self.max_gap_days
                or self.zscore_weeks < 3):
            raise ValueError("Choose official tier cutoffs, positive lookbacks, and valid weekly-gap limits")


def _read_tier_aggregates(chip_path: Path, research_path: Path, lower: date, end: date) -> pd.DataFrame:
    with sqlite3.connect(chip_path) as chip, sqlite3.connect(research_path) as research:
        raw = pd.read_sql_query("""SELECT stock_id,report_date,tier,SUM(shares) AS shares,
            SUM(holder_count) AS holder_count FROM stock_ownership_distribution_weekly
            WHERE report_date BETWEEN ? AND ? GROUP BY stock_id,report_date,tier""",
            chip, params=(lower.isoformat(), end.isoformat()))
        meta = pd.read_sql_query("""SELECT stock_id,report_date,total_shares,valid,source_url,
            first_seen_at,published_at,publication_status FROM research_ownership_weekly_meta
            WHERE report_date BETWEEN ? AND ?""",
            research, params=(lower.isoformat(), end.isoformat()))
    if raw.empty or meta.empty:
        return pd.DataFrame()
    raw = raw.merge(meta.loc[meta["valid"].eq(1)], on=["stock_id", "report_date"], how="inner", validate="many_to_one")
    return raw


def calculate_factors(raw: pd.DataFrame, config: FactorConfig = FactorConfig()) -> pd.DataFrame:
    """Compute ratios and past-only weekly changes from validated tier rows."""
    if raw.empty:
        return pd.DataFrame()
    keys = ["stock_id", "report_date"]
    base = raw.loc[raw["tier"].eq(17), keys + ["total_shares", "source_url", "first_seen_at",
                                                  "published_at", "publication_status"]].drop_duplicates(keys)
    base = base.sort_values(keys).reset_index(drop=True)
    small = raw.loc[raw["tier"].le(config.small_holder_last_tier)].groupby(keys, sort=False)["shares"].sum()
    base["pct_small"] = [small.get((code, day), np.nan) / total * 100
                         for code, day, total in base[keys + ["total_shares"]].itertuples(index=False, name=None)]
    for threshold in config.thresholds_lots:
        tiers = raw.loc[raw["tier"].between(TIER_START[threshold], 15)]
        sums = tiers.groupby(keys, sort=False).agg(large_shares=("shares", "sum"), large_holders=("holder_count", "sum"))
        joined = base[keys].join(sums, on=keys)
        base[f"pct_gt_{threshold}"] = joined["large_shares"].to_numpy() / base["total_shares"].to_numpy() * 100
        base[f"holders_gt_{threshold}"] = joined["large_holders"].to_numpy()
        base[f"mean_shares_gt_{threshold}"] = joined["large_shares"].to_numpy() / joined["large_holders"].replace(0, np.nan).to_numpy()
    base["report_dt"] = pd.to_datetime(base["report_date"])
    previous_dt = base.groupby("stock_id")["report_dt"].shift(1)
    base["gap_days"] = (base["report_dt"] - previous_dt).dt.days
    broken = base["gap_days"].isna() | ~base["gap_days"].between(config.min_gap_days, config.max_gap_days)
    base["segment"] = broken.groupby(base["stock_id"]).cumsum()
    grouped = base.groupby(["stock_id", "segment"], sort=False)
    for threshold in config.thresholds_lots:
        prefix = f"gt_{threshold}"
        pct = f"pct_{prefix}"
        for weeks in config.change_weeks:
            base[f"delta_{weeks}w_{prefix}"] = base[pct] - grouped[pct].shift(weeks)
        weekly = base[pct] - grouped[pct].shift(1)
        speed = weekly * 7 / base["gap_days"]
        base[f"speed_pp_per_week_{prefix}"] = speed
        base[f"acceleration_pp_per_week_{prefix}"] = speed - speed.groupby([base["stock_id"], base["segment"]]).shift(1)
        base[f"consecutive_up_weeks_{prefix}"] = _consecutive_up(base, weekly)
        history = grouped[pct].transform(lambda values: values.shift(1).rolling(config.zscore_weeks, min_periods=config.zscore_weeks).mean())
        spread = grouped[pct].transform(lambda values: values.shift(1).rolling(config.zscore_weeks, min_periods=config.zscore_weeks).std())
        base[f"zscore_{prefix}"] = (base[pct] - history) / spread.replace(0, np.nan)
    small_delta = base["pct_small"] - grouped["pct_small"].shift(1)
    primary = config.primary_threshold_lots
    base["large_minus_small_delta_1w_pp"] = base[f"pct_gt_{primary}"] - grouped[f"pct_gt_{primary}"].shift(1) - small_delta
    return base.drop(columns=["report_dt", "segment"]).reset_index(drop=True)


def _consecutive_up(frame: pd.DataFrame, weekly: pd.Series) -> pd.Series:
    result = np.zeros(len(frame), dtype=int)
    last_key = None
    count = 0
    for idx, (code, segment, value) in enumerate(zip(frame["stock_id"], frame["segment"], weekly)):
        key = (code, segment)
        count = count + 1 if key == last_key and pd.notna(value) and value > 0 else (1 if pd.notna(value) and value > 0 else 0)
        result[idx] = count
        last_key = key
    return pd.Series(result, index=frame.index)


def load_factors(start: date, end: date, *, config: FactorConfig = FactorConfig(),
                 chip_path: Path = CHIP_DB, research_path: Path = DB_PATH) -> pd.DataFrame:
    if end < start:
        raise ValueError("end must be on or after start")
    lookback_days = (max((*config.change_weeks, config.zscore_weeks)) + 2) * config.max_gap_days
    raw = _read_tier_aggregates(chip_path, research_path, start - timedelta(days=lookback_days), end)
    frame = calculate_factors(raw, config)
    return frame.loc[frame["report_date"].between(start.isoformat(), end.isoformat())].reset_index(drop=True) if not frame.empty else frame
