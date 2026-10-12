from __future__ import annotations

from datetime import datetime, timedelta
import io
import re
import sqlite3

import pandas as pd
from bs4 import BeautifulSoup

from modules.core.project_paths import db_path
from modules.core.http_utils import request_text
from modules.industry.industry_taxonomy import TECH_INDUSTRY_NAMES

DB_PATH = db_path("revenue_cache.db")
MONTHLY_REVENUE_URLS = {
    "上市": "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv",
    "上櫃": "https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv",
}
HISTORICAL_REVENUE_MARKETS = {"上市": "sii", "上櫃": "otc"}


def _get_connection():
    return sqlite3.connect(DB_PATH)


def init_revenue_cache():
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_revenue (
                report_month TEXT NOT NULL,
                output_date TEXT,
                market TEXT NOT NULL,
                code TEXT NOT NULL,
                name_zh TEXT,
                industry TEXT,
                current_revenue REAL,
                previous_revenue REAL,
                last_year_revenue REAL,
                mom_pct REAL,
                yoy_pct REAL,
                cumulative_revenue REAL,
                cumulative_last_year_revenue REAL,
                cumulative_yoy_pct REAL,
                remark TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (report_month, market, code)
            )
            """
        )


def _safe_float(value):
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else None


def _roc_month_to_iso(value):
    if value is None or pd.isna(value):
        return None

    raw = str(int(float(value)))
    if len(raw) < 4:
        return None

    roc_year = int(raw[:-2])
    month = int(raw[-2:])
    return f"{roc_year + 1911:04d}-{month:02d}"


def _roc_date_to_iso(value):
    if value is None or pd.isna(value):
        return None

    raw = str(int(float(value)))
    if len(raw) < 5:
        return None

    roc_year = int(raw[:-4])
    month = int(raw[-4:-2])
    day = int(raw[-2:])
    return f"{roc_year + 1911:04d}-{month:02d}-{day:02d}"


def _download_csv_text(url):
    return request_text(
        url,
        headers={
            "Accept": "text/csv,*/*;q=0.8",
        },
        encoding="utf-8-sig",
    )


def _fetch_market_snapshot(market, url):
    raw_text = _download_csv_text(url)
    source_df = pd.read_csv(io.StringIO(raw_text))
    source_df["公司代號"] = source_df["公司代號"].astype(str).str.extract(r"(\d+)")[0].str.zfill(4)
    source_df = source_df[source_df["公司代號"].notna()].copy()

    normalized_df = pd.DataFrame(
        {
            "report_month": source_df["資料年月"].apply(_roc_month_to_iso),
            "output_date": source_df["出表日期"].apply(_roc_date_to_iso),
            "market": market,
            "code": source_df["公司代號"],
            "name_zh": source_df["公司名稱"].astype(str).str.strip(),
            "industry": source_df["產業別"].astype(str).str.strip(),
            "current_revenue": source_df["營業收入-當月營收"].apply(_safe_float),
            "previous_revenue": source_df["營業收入-上月營收"].apply(_safe_float),
            "last_year_revenue": source_df["營業收入-去年當月營收"].apply(_safe_float),
            "mom_pct": source_df["營業收入-上月比較增減(%)"].apply(_safe_float),
            "yoy_pct": source_df["營業收入-去年同月增減(%)"].apply(_safe_float),
            "cumulative_revenue": source_df["累計營業收入-當月累計營收"].apply(_safe_float),
            "cumulative_last_year_revenue": source_df["累計營業收入-去年累計營收"].apply(_safe_float),
            "cumulative_yoy_pct": source_df["累計營業收入-前期比較增減(%)"].apply(_safe_float),
            "remark": source_df["備註"].fillna("").astype(str).str.strip(),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    normalized_df = normalized_df.dropna(subset=["report_month", "code"])
    return normalized_df


def _save_snapshot(revenue_df):
    if revenue_df.empty:
        return

    records = revenue_df.to_dict(orient="records")
    with _get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO monthly_revenue (
                report_month,
                output_date,
                market,
                code,
                name_zh,
                industry,
                current_revenue,
                previous_revenue,
                last_year_revenue,
                mom_pct,
                yoy_pct,
                cumulative_revenue,
                cumulative_last_year_revenue,
                cumulative_yoy_pct,
                remark,
                updated_at
            ) VALUES (
                :report_month,
                :output_date,
                :market,
                :code,
                :name_zh,
                :industry,
                :current_revenue,
                :previous_revenue,
                :last_year_revenue,
                :mom_pct,
                :yoy_pct,
                :cumulative_revenue,
                :cumulative_last_year_revenue,
                :cumulative_yoy_pct,
                :remark,
                :updated_at
            )
            """,
            records,
        )


def _load_latest_snapshot():
    init_revenue_cache()
    with _get_connection() as conn:
        latest_month_row = conn.execute(
            "SELECT MAX(report_month) FROM monthly_revenue"
        ).fetchone()
        latest_month = latest_month_row[0] if latest_month_row else None
        if not latest_month:
            return pd.DataFrame()

        snapshot_df = pd.read_sql_query(
            """
            SELECT report_month, output_date, market, code, name_zh, industry,
                   current_revenue, previous_revenue, last_year_revenue,
                   mom_pct, yoy_pct, cumulative_revenue,
                   cumulative_last_year_revenue, cumulative_yoy_pct,
                   remark, updated_at
            FROM monthly_revenue
            WHERE report_month = ?
            ORDER BY code
            """,
            conn,
            params=(latest_month,),
        )
    return snapshot_df


def _load_cached_history():
    init_revenue_cache()
    with _get_connection() as conn:
        history_df = pd.read_sql_query(
            """
            SELECT report_month, output_date, market, code, name_zh, industry,
                   current_revenue, previous_revenue, last_year_revenue,
                   mom_pct, yoy_pct, cumulative_revenue,
                   cumulative_last_year_revenue, cumulative_yoy_pct,
                   remark, updated_at
            FROM monthly_revenue
            ORDER BY report_month, code
            """,
            conn,
        )
    return history_df


def refresh_monthly_revenue_snapshot():
    init_revenue_cache()
    revenue_frames = [
        _fetch_market_snapshot(market, url)
        for market, url in MONTHLY_REVENUE_URLS.items()
    ]
    # The open-data CSV is a complete monthly snapshot and may lag the MOPS
    # current-month archive while companies publish their reports one by one.
    previous_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    latest_csv_month = max((frame["report_month"].max() for frame in revenue_frames if not frame.empty), default="")
    if latest_csv_month < previous_month:
        for market in HISTORICAL_REVENUE_MARKETS:
            try:
                revenue_frames.append(_fetch_historical_revenue_month(market, previous_month))
            except Exception as exc:
                # Keep the complete CSV snapshot when the partial archive is not ready.
                import logging
                logging.getLogger(__name__).warning("Current month revenue archive unavailable for %s: %s", market, exc)
    combined_df = pd.concat(revenue_frames, ignore_index=True).drop_duplicates(
        subset=["report_month", "market", "code"],
        keep="last",
    )
    _save_snapshot(combined_df)
    return combined_df


def _fetch_historical_revenue_month(market: str, report_month: str) -> pd.DataFrame:
    year, month = (int(part) for part in report_month.split("-"))
    roc_year = year - 1911
    market_path = HISTORICAL_REVENUE_MARKETS[market]
    records = []
    for group in (0, 1):
        url = (
            f"https://mopsov.twse.com.tw/nas/t21/{market_path}/"
            f"t21sc03_{roc_year}_{month}_{group}.html"
        )
        html = request_text(url, encoding="big5")
        soup = BeautifulSoup(html, "html.parser")
        industry = ""
        group_count = 0
        for tr in soup.find_all("tr"):
            for th in tr.find_all("th", recursive=False):
                heading = th.get_text(" ", strip=True)
                if heading.startswith("產業別："):
                    industry = heading.partition("：")[2]
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td", recursive=False)]
            if len(cells) != 11 or not re.fullmatch(r"\d{4,6}", cells[0]):
                continue
            numbers = [_safe_float(value.replace(",", "")) for value in cells[2:10]]
            records.append(
                {
                    "report_month": report_month,
                    "output_date": None,
                    "market": market,
                    "code": cells[0],
                    "name_zh": cells[1],
                    "industry": industry,
                    "current_revenue": numbers[0],
                    "previous_revenue": numbers[1],
                    "last_year_revenue": numbers[2],
                    "mom_pct": numbers[3],
                    "yoy_pct": numbers[4],
                    "cumulative_revenue": numbers[5],
                    "cumulative_last_year_revenue": numbers[6],
                    "cumulative_yoy_pct": numbers[7],
                    "remark": "" if cells[10] == "-" else cells[10],
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            group_count += 1
        if not group_count:
            raise ValueError(f"Historical revenue has no stock rows: {url}")
    return pd.DataFrame.from_records(records).drop_duplicates(
        subset=["report_month", "market", "code"], keep="last"
    )


def backfill_recent_monthly_revenue(months: int = 12) -> int:
    """Fill missing market-month archives for the latest available year."""
    init_revenue_cache()
    with _get_connection() as conn:
        latest_month = conn.execute("SELECT MAX(report_month) FROM monthly_revenue").fetchone()[0]
        cached_months = {
            (report_month, market)
            for report_month, market in conn.execute(
                "SELECT DISTINCT report_month, market FROM monthly_revenue"
            )
        }
    if not latest_month:
        return 0

    year, month = (int(part) for part in latest_month.split("-"))
    latest_index = year * 12 + month - 1
    inserted = 0
    for month_index in range(latest_index - max(1, months) + 1, latest_index + 1):
        report_month = f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"
        for market in HISTORICAL_REVENUE_MARKETS:
            if (report_month, market) in cached_months:
                continue
            history = _fetch_historical_revenue_month(market, report_month)
            _save_snapshot(history)
            inserted += len(history)
    return inserted


def get_latest_monthly_revenue(force_refresh=False, max_cache_age_hours=12):
    cached_df = _load_latest_snapshot()
    if not cached_df.empty and not force_refresh:
        updated_at = pd.to_datetime(cached_df["updated_at"], errors="coerce").max()
        if pd.notna(updated_at) and updated_at >= datetime.now() - timedelta(hours=max_cache_age_hours):
            return cached_df

    try:
        return refresh_monthly_revenue_snapshot()
    except Exception:
        if not cached_df.empty:
            return cached_df
        raise


def build_revenue_momentum_rankings(
    top_n=10,
    min_yoy_pct=3.0,
    min_mom_pct=-10.0,
    min_cumulative_yoy_pct=-5.0,
    min_current_revenue=50000.0,
    min_reference_revenue=20000.0,
    required_consecutive_months=3,
    exclude_february_from_average=True,
    technology_only=True,
    min_overall_growth_pct=3.0,
):
    latest_snapshot_df = get_latest_monthly_revenue()
    if latest_snapshot_df.empty:
        return None

    revenue_df = latest_snapshot_df.copy()
    if technology_only:
        revenue_df = revenue_df[revenue_df["industry"].isin(TECH_INDUSTRY_NAMES)].copy()
    if revenue_df.empty:
        return None

    # 月營收很容易被低基期扭曲，先加參考營收門檻，再把排序分數做裁切，避免排行榜被極端值洗掉。
    revenue_df["score_yoy_pct"] = revenue_df["yoy_pct"].clip(lower=-100, upper=120)
    revenue_df["score_mom_pct"] = revenue_df["mom_pct"].clip(lower=-100, upper=40)
    revenue_df["score_cumulative_yoy_pct"] = revenue_df["cumulative_yoy_pct"].clip(lower=-100, upper=80)

    base_filtered_df = revenue_df[
        (revenue_df["yoy_pct"].fillna(-9999) >= min_yoy_pct)
        & (revenue_df["mom_pct"].fillna(-9999) >= min_mom_pct)
        & (revenue_df["cumulative_yoy_pct"].fillna(-9999) >= min_cumulative_yoy_pct)
        & (revenue_df["current_revenue"].fillna(0) >= min_current_revenue)
        & (revenue_df["previous_revenue"].fillna(0) >= min_reference_revenue)
        & (revenue_df["last_year_revenue"].fillna(0) >= min_reference_revenue)
    ].copy()

    history_df = _load_cached_history()
    distinct_months = sorted(history_df["report_month"].dropna().unique().tolist())
    recent_months = distinct_months[-required_consecutive_months:]
    history_mode = "fallback"

    if len(recent_months) >= required_consecutive_months:
        history_mode = "consecutive"
        recent_history_df = history_df[history_df["report_month"].isin(recent_months)].copy()
        pivot_df = (
            recent_history_df.pivot_table(
                index=["code", "market", "name_zh", "industry"],
                columns="report_month",
                values="current_revenue",
                aggfunc="last",
            )
            .reset_index()
        )
        revenue_columns = [month for month in recent_months if month in pivot_df.columns]
        if len(revenue_columns) >= required_consecutive_months:
            has_all_months_mask = pivot_df[revenue_columns].notna().all(axis=1)
            diffs_df = pivot_df[revenue_columns].diff(axis=1)
            positive_step_count = diffs_df.iloc[:, 1:].gt(0).sum(axis=1)
            required_positive_steps = max(1, len(revenue_columns) - 2)
            latest_column = revenue_columns[-1]
            earliest_column = revenue_columns[0]
            previous_columns = revenue_columns[:-1]

            pivot_df["positive_step_count"] = positive_step_count
            pivot_df["overall_growth_pct"] = (
                (pivot_df[latest_column] / pivot_df[earliest_column] - 1.0) * 100.0
            )
            pivot_df["latest_vs_first_pct"] = pivot_df["overall_growth_pct"]
            pivot_df["latest_vs_recent_average_pct"] = (
                (pivot_df[latest_column] / pivot_df[previous_columns].mean(axis=1) - 1.0) * 100.0
            )
            pivot_df["latest_is_recent_high"] = pivot_df[latest_column] >= pivot_df[previous_columns].max(axis=1)

            average_mask = pd.Series(True, index=pivot_df.index)
            comparable_columns = revenue_columns[:-1]
            if exclude_february_from_average:
                comparable_columns = [month for month in comparable_columns if not month.endswith("-02")]

            if comparable_columns:
                recent_average = pivot_df[comparable_columns].mean(axis=1)
                average_mask = pivot_df[latest_column] >= recent_average

            trend_mask = (
                (pivot_df["positive_step_count"] >= required_positive_steps)
                & (pivot_df["overall_growth_pct"].fillna(-9999) >= min_overall_growth_pct)
                & pivot_df["latest_is_recent_high"]
            )
            consecutive_codes = set(
                pivot_df[has_all_months_mask & trend_mask & average_mask]["code"].astype(str)
            )
            filtered_df = base_filtered_df[base_filtered_df["code"].astype(str).isin(consecutive_codes)].copy()
            trend_features_df = pivot_df[
                [
                    "code",
                    "positive_step_count",
                    "overall_growth_pct",
                    "latest_vs_recent_average_pct",
                ]
            ].copy()
            filtered_df = filtered_df.merge(trend_features_df, on="code", how="left")
        else:
            filtered_df = base_filtered_df.copy()
            history_mode = "fallback"
    else:
        # 還沒累積足夠月份時，先退回成「本月優於上月」的保守版本，
        # 之後每月資料累積進資料庫後會自動升級成真正的連續月營收模式。
        filtered_df = base_filtered_df[
            base_filtered_df["current_revenue"].fillna(0) > base_filtered_df["previous_revenue"].fillna(0)
        ].copy()

    filtered_df["overall_growth_pct"] = pd.to_numeric(filtered_df.get("overall_growth_pct"), errors="coerce")
    filtered_df["positive_step_count"] = pd.to_numeric(filtered_df.get("positive_step_count"), errors="coerce")
    filtered_df["latest_vs_recent_average_pct"] = pd.to_numeric(
        filtered_df.get("latest_vs_recent_average_pct"),
        errors="coerce",
    )
    filtered_df["score_overall_growth_pct"] = filtered_df["overall_growth_pct"].clip(lower=-100, upper=80)
    filtered_df["score_latest_vs_recent_average_pct"] = filtered_df["latest_vs_recent_average_pct"].clip(lower=-100, upper=40)
    filtered_df["momentum_score"] = (
        filtered_df["score_overall_growth_pct"].fillna(0) * 0.45
        + filtered_df["score_latest_vs_recent_average_pct"].fillna(0) * 0.20
        + filtered_df["score_yoy_pct"].fillna(0) * 0.20
        + filtered_df["score_cumulative_yoy_pct"].fillna(0) * 0.10
        + filtered_df["positive_step_count"].fillna(0) * 5.0
        + filtered_df["score_mom_pct"].fillna(0) * 0.05
    )

    filtered_df = filtered_df.sort_values(
        by=["momentum_score", "overall_growth_pct", "positive_step_count", "yoy_pct", "current_revenue"],
        ascending=[False, False, False, False, False],
    )

    top_df = filtered_df.head(top_n)[
        [
            "code",
            "name_zh",
            "market",
            "industry",
            "report_month",
            "output_date",
            "current_revenue",
            "mom_pct",
            "yoy_pct",
            "cumulative_yoy_pct",
            "overall_growth_pct",
            "positive_step_count",
            "latest_vs_recent_average_pct",
            "momentum_score",
        ]
    ].reset_index(drop=True)

    latest_report_month = revenue_df["report_month"].dropna().mode().iloc[0]
    latest_output_date = revenue_df["output_date"].dropna().mode().iloc[0]

    return {
        "report_month": latest_report_month,
        "output_date": latest_output_date,
        "data_count": len(revenue_df),
        "screened_count": len(filtered_df),
        "top_df": top_df,
        "min_yoy_pct": min_yoy_pct,
        "min_mom_pct": min_mom_pct,
        "min_cumulative_yoy_pct": min_cumulative_yoy_pct,
        "min_current_revenue": min_current_revenue,
        "min_reference_revenue": min_reference_revenue,
        "required_consecutive_months": required_consecutive_months,
        "exclude_february_from_average": exclude_february_from_average,
        "technology_only": technology_only,
        "min_overall_growth_pct": min_overall_growth_pct,
        "history_mode": history_mode,
        "cached_months": distinct_months,
        "used_months": recent_months,
    }
