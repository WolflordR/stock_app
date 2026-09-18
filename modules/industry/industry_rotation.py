from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from functools import lru_cache

import pandas as pd

from modules.core.project_paths import db_path
from modules.industry.company_links_db import get_company_profiles_df
from modules.core.http_utils import request_json
from modules.industry.industry_taxonomy import TECH_INDUSTRY_NAMES
from modules.industry.industry_taxonomy import TIDE_LATEST_URL
from modules.industry.industry_taxonomy import TIDE_SECTOR_TO_GROUP
from modules.industry.industry_taxonomy import TWSE_TECH_INDEX_NAMES
from modules.data_sources.market_watch import fetch_tpex_daily_quotes
from modules.data_sources.market_watch import fetch_twse_daily_quotes


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _roc_date_to_iso(value):
    raw = str(value or "").strip()
    if not raw or len(raw) < 7:
        return raw
    roc_year = int(raw[:3])
    month = int(raw[3:5])
    day = int(raw[5:7])
    return f"{roc_year + 1911:04d}-{month:02d}-{day:02d}"


def _safe_float(value):
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else None


def _safe_divide(numerator, denominator):
    if denominator in {None, 0} or pd.isna(denominator):
        return None
    return float(numerator) / float(denominator)


def _format_volume_lots(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value / 1000:,.1f} 張"


def _format_turnover_billions(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value / 100000000:,.2f} 億"


def _format_index(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:,.2f}"


def _format_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.2f}%"


def _format_ratio(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.2f}x"


def _format_score_delta(value):
    if value is None or pd.isna(value):
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}"


def _format_signed_yi(value):
    if value is None or pd.isna(value):
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}"


def _format_classification_source(value):
    return {
        "tide_latest": "Tide分類",
        "seed_code": "核心名單",
        "seed_alias": "別名擴充",
        "manual_override": "人工覆寫",
    }.get(value, value or "-")


@lru_cache(maxsize=8)
def _load_tide_latest_payload():
    payload = request_json(TIDE_LATEST_URL, timeout=30)
    if not isinstance(payload, dict):
        raise ValueError("Tide latest.json 格式不是物件")
    sectors = payload.get("sectors")
    if not isinstance(sectors, list):
        raise ValueError("Tide latest.json 缺少 sectors")
    return payload


@lru_cache(maxsize=32)
def _load_market_history_cached(anchor_date_text, history_trade_days, max_calendar_lookback):
    anchor_date = _to_date(anchor_date_text)
    history_frames = []
    collected_dates = []

    for offset in range(max_calendar_lookback + 1):
        probe_date = anchor_date - timedelta(days=offset)
        listed_df = fetch_twse_daily_quotes(probe_date)
        otc_df = fetch_tpex_daily_quotes(probe_date)
        if listed_df.empty or otc_df.empty:
            continue
        quotes_df = pd.concat([listed_df, otc_df], ignore_index=True)
        if quotes_df.empty:
            continue

        quotes_df = quotes_df.copy()
        quotes_df["trade_date"] = probe_date.strftime("%Y-%m-%d")
        quotes_df["turnover_value"] = quotes_df["close"].fillna(0) * quotes_df["volume"].fillna(0)
        history_frames.append(quotes_df)
        collected_dates.append(probe_date.strftime("%Y-%m-%d"))
        if len(collected_dates) >= history_trade_days:
            break

    if not history_frames:
        return pd.DataFrame(), tuple()

    combined_df = pd.concat(history_frames, ignore_index=True)
    combined_df["code"] = combined_df["code"].astype(str).str.zfill(4)
    combined_df["trade_date"] = pd.to_datetime(combined_df["trade_date"])
    combined_df = combined_df.sort_values(["trade_date", "code"]).reset_index(drop=True)
    return combined_df, tuple(sorted(collected_dates))


def _load_market_history(anchor_date, history_trade_days=8, max_calendar_lookback=20):
    return _load_market_history_cached(
        _to_date(anchor_date).strftime("%Y-%m-%d"),
        int(history_trade_days),
        int(max_calendar_lookback),
    )


def _build_theme_membership_df():
    profiles_df = get_company_profiles_df()[["code", "name_zh", "market", "industry"]].copy()
    profiles_df["code"] = profiles_df["code"].astype(str).str.zfill(4)
    profile_lookup = profiles_df.drop_duplicates(subset=["code"], keep="last").set_index("code")

    tide_payload = _load_tide_latest_payload()
    tide_date = str(tide_payload.get("date") or tide_payload.get("updated_at") or "").strip()
    rows = []
    for sector in tide_payload.get("sectors", []):
        if not isinstance(sector, dict):
            continue
        sector_name = str(sector.get("name") or "").strip()
        if not sector_name:
            continue
        sector_group = TIDE_SECTOR_TO_GROUP.get(sector_name, "其他")
        for raw_code in sector.get("stocks") or []:
            code = str(raw_code or "").strip().zfill(4)
            if not code:
                continue
            profile = profile_lookup.loc[code] if code in profile_lookup.index else {}
            rows.append(
                {
                    "code": code,
                    "group_name": sector_name,
                    "parent_industry": sector_group,
                    "official_industry": profile.get("industry", "") if hasattr(profile, "get") else "",
                    "name_zh": profile.get("name_zh", "") if hasattr(profile, "get") else "",
                    "market": profile.get("market", "") if hasattr(profile, "get") else "",
                    "classification_source": "tide_latest",
                    "confidence": 1.0,
                    "classification_note": f"Tide latest.json {tide_date}",
                }
            )

    if not rows:
        return pd.DataFrame(columns=["code", "group_name", "parent_industry", "official_industry", "name_zh", "market", "classification_source", "confidence", "classification_note"])

    membership_df = pd.DataFrame(rows)
    membership_df["official_industry"] = membership_df["official_industry"].fillna("").astype(str).str.strip()
    membership_df["name_zh"] = membership_df["name_zh"].fillna("").astype(str).str.strip()
    membership_df["market"] = membership_df["market"].fillna("").astype(str).str.strip()
    return membership_df.drop_duplicates(subset=["code", "group_name"], keep="first")


def _build_official_industry_membership_df():
    profiles_df = get_company_profiles_df()[["code", "name_zh", "market", "industry"]].copy()
    profiles_df["code"] = profiles_df["code"].astype(str).str.zfill(4)
    profiles_df["industry"] = profiles_df["industry"].fillna("").astype(str).str.strip()
    profiles_df = profiles_df[profiles_df["industry"].isin(TECH_INDUSTRY_NAMES)].copy()
    profiles_df["group_name"] = profiles_df["industry"]
    profiles_df["parent_industry"] = profiles_df["industry"]
    return profiles_df.drop_duplicates(subset=["code", "group_name"], keep="last")


def _build_all_official_industry_membership_df():
    profiles_df = get_company_profiles_df()[["code", "name_zh", "market", "industry"]].copy()
    profiles_df["code"] = profiles_df["code"].astype(str).str.zfill(4)
    profiles_df["industry"] = profiles_df["industry"].fillna("").astype(str).str.strip()
    profiles_df = profiles_df[profiles_df["industry"] != ""].copy()
    profiles_df["group_name"] = profiles_df["industry"]
    profiles_df["parent_industry"] = profiles_df["industry"]
    return profiles_df.drop_duplicates(subset=["code", "group_name"], keep="last")


def _build_rotation_summary(history_df, membership_df):
    if history_df.empty or membership_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    merged_df = history_df.merge(
        membership_df.drop_duplicates(subset=["code", "group_name"]),
        on="code",
        how="inner",
    )
    if merged_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    daily_summary_df = (
        merged_df.groupby(["group_name", "parent_industry", "trade_date"])
        .agg(
            stock_count=("code", "nunique"),
            total_volume=("volume", "sum"),
            total_turnover=("turnover_value", "sum"),
            avg_change_pct=("change_pct", "mean"),
            positive_count=("change_pct", lambda series: int((series > 0).sum())),
            limit_up_count=("limit_up", "sum"),
            locked_up_count=("locked_limit_up", "sum"),
        )
        .reset_index()
        .sort_values(["group_name", "trade_date"])
        .reset_index(drop=True)
    )

    latest_date = daily_summary_df["trade_date"].max()
    latest_component_df = merged_df[merged_df["trade_date"] == latest_date].copy()
    representative_df = (
        latest_component_df.sort_values(["group_name", "turnover_value"], ascending=[True, False])
        .groupby("group_name")
        .head(3)[["group_name", "name", "code"]]
    )
    representative_map = (
        representative_df.groupby("group_name")
        .apply(lambda group: " / ".join(f"{row['name']}({row['code']})" for _, row in group.iterrows()))
        .to_dict()
    )

    summary_rows = []
    series_rows = []
    for (group_name, parent_industry), group_df in daily_summary_df.groupby(["group_name", "parent_industry"]):
        group_df = group_df.sort_values("trade_date").reset_index(drop=True)
        index_level = 100.0
        index_series = []
        rotation_scores = []
        score_delta_1d_series = []
        score_delta_3d_series = []
        for _, row in group_df.iterrows():
            day_return = (_safe_float(row["avg_change_pct"]) or 0.0) / 100.0
            index_level *= (1.0 + day_return)
            index_series.append(index_level)

        group_df = group_df.copy()
        group_df["custom_index"] = index_series
        for row_index, row in group_df.iterrows():
            baseline_df = group_df.iloc[max(0, row_index - 5):row_index]
            baseline_volume = baseline_df["total_volume"].mean() if not baseline_df.empty else None
            baseline_turnover = baseline_df["total_turnover"].mean() if not baseline_df.empty else None
            volume_ratio = _safe_divide(row["total_volume"], baseline_volume)
            turnover_ratio = _safe_divide(row["total_turnover"], baseline_turnover)
            breadth_pct = _safe_divide(row["positive_count"], row["stock_count"])
            breadth_pct = (breadth_pct * 100.0) if breadth_pct is not None else None
            rotation_score = (
                min(volume_ratio or 0.0, 3.0) * 18
                + min(turnover_ratio or 0.0, 3.0) * 14
                + max(min(_safe_float(row["avg_change_pct"]) or 0.0, 6.0), -6.0) * 3.5
                + (breadth_pct or 0.0) * 0.22
                + float(row["locked_up_count"]) * 4.0
            )
            rotation_scores.append(rotation_score)

            prev_score = rotation_scores[row_index - 1] if row_index >= 1 else None
            base_score_3d = rotation_scores[row_index - 3] if row_index >= 3 else None
            score_delta_1d_series.append(
                (rotation_score - prev_score) if prev_score is not None else None
            )
            score_delta_3d_series.append(
                (rotation_score - base_score_3d) if base_score_3d is not None else None
            )

        group_df["rotation_score"] = rotation_scores
        group_df["score_delta_1d"] = score_delta_1d_series
        group_df["score_delta_3d"] = score_delta_3d_series

        latest_row = group_df.iloc[-1]
        baseline_df = group_df.iloc[:-1]
        baseline_volume = baseline_df.tail(5)["total_volume"].mean() if not baseline_df.empty else None
        baseline_turnover = baseline_df.tail(5)["total_turnover"].mean() if not baseline_df.empty else None
        volume_ratio = _safe_divide(latest_row["total_volume"], baseline_volume)
        turnover_ratio = _safe_divide(latest_row["total_turnover"], baseline_turnover)
        breadth_pct = _safe_divide(latest_row["positive_count"], latest_row["stock_count"])
        breadth_pct = (breadth_pct * 100.0) if breadth_pct is not None else None
        if len(group_df) >= 6:
            five_day_base = group_df.iloc[-6]["custom_index"]
            five_day_pct = ((latest_row["custom_index"] / five_day_base) - 1.0) * 100 if five_day_base else None
        elif len(group_df) >= 2:
            first_index = group_df.iloc[0]["custom_index"]
            five_day_pct = ((latest_row["custom_index"] / first_index) - 1.0) * 100 if first_index else None
        else:
            five_day_pct = None

        rotation_score = _safe_float(latest_row["rotation_score"])

        summary_rows.append(
            {
                "group_name": group_name,
                "parent_industry": parent_industry,
                "latest_index": latest_row["custom_index"],
                "latest_change_pct": _safe_float(latest_row["avg_change_pct"]),
                "five_day_change_pct": five_day_pct,
                "latest_volume": _safe_float(latest_row["total_volume"]),
                "avg_volume_5d": _safe_float(baseline_volume),
                "volume_ratio": volume_ratio,
                "latest_turnover": _safe_float(latest_row["total_turnover"]),
                "avg_turnover_5d": _safe_float(baseline_turnover),
                "turnover_ratio": turnover_ratio,
                "stock_count": int(latest_row["stock_count"]),
                "positive_count": int(latest_row["positive_count"]),
                "limit_up_count": int(latest_row["limit_up_count"]),
                "locked_up_count": int(latest_row["locked_up_count"]),
                "breadth_pct": breadth_pct,
                "rotation_score": rotation_score,
                "score_delta_1d": _safe_float(latest_row["score_delta_1d"]),
                "score_delta_3d": _safe_float(latest_row["score_delta_3d"]),
                "representative_stocks": representative_map.get(group_name, ""),
            }
        )

        for _, row in group_df.iterrows():
            series_rows.append(
                {
                    "group_name": group_name,
                    "parent_industry": parent_industry,
                    "trade_date": row["trade_date"].strftime("%Y-%m-%d"),
                    "custom_index": row["custom_index"],
                    "avg_change_pct": _safe_float(row["avg_change_pct"]),
                    "total_volume": _safe_float(row["total_volume"]),
                    "total_turnover": _safe_float(row["total_turnover"]),
                    "rotation_score": _safe_float(row["rotation_score"]),
                    "score_delta_1d": _safe_float(row["score_delta_1d"]),
                    "score_delta_3d": _safe_float(row["score_delta_3d"]),
                }
            )

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["rotation_score", "latest_turnover", "latest_change_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    series_df = pd.DataFrame(series_rows)
    return summary_df, series_df, latest_component_df


def _classify_fund_flow(net_5d_yi, accel_yi):
    net_5d_yi = _safe_float(net_5d_yi) or 0.0
    accel_yi = _safe_float(accel_yi) or 0.0
    if net_5d_yi > 0 and accel_yi > 0:
        return "漲潮"
    if net_5d_yi > 0 and accel_yi <= 0:
        return "輪動"
    if -0.5 < net_5d_yi <= 0:
        return "觀望"
    return "退潮"


def _format_flow_streak(streak, accel_yi):
    streak = int(streak or 0)
    accel_yi = _safe_float(accel_yi) or 0.0
    if streak == 0:
        return "資金沉寂"

    inflow = streak > 0
    accelerating = accel_yi > 0 if inflow else accel_yi < 0
    direction = "流入" if inflow else "流出"
    pace = "加速" if accelerating else "放緩"
    return f"{abs(streak)}日{direction}{pace}"


def _build_tide_sector_fund_flow_report(theme_summary_df):
    tide_payload = _load_tide_latest_payload()
    sectors = tide_payload.get("sectors") or []
    if theme_summary_df.empty or not sectors:
        return None

    sector_rows = []
    for sector in sectors:
        if not isinstance(sector, dict):
            continue
        group_name = str(sector.get("name") or "").strip()
        if not group_name:
            continue
        net_1d = _safe_float(sector.get("net_1d_yi")) or 0.0
        net_5d = _safe_float(sector.get("net_5d_yi")) or 0.0
        net_20d = _safe_float(sector.get("net_20d_yi")) or 0.0
        accel_yi = (net_5d / 5.0) - (net_20d / 20.0)
        sector_rows.append(
            {
                "group_name": group_name,
                "fund_status": _classify_fund_flow(net_5d, accel_yi),
                "net_1d_yi": net_1d,
                "net_5d_yi": net_5d,
                "net_20d_yi": net_20d,
                "accel_yi": accel_yi,
                "inflow_streak": int(_safe_float(sector.get("inflow_streak")) or 0),
                "covered_stock_count": len(sector.get("stocks") or []),
                "tide_position": _safe_float(sector.get("position")),
                "tide_chg_1d": _safe_float(sector.get("chg_1d")),
                "tide_chg_5d": _safe_float(sector.get("chg_5d")),
            }
        )

    flow_summary_df = pd.DataFrame(sector_rows)
    if flow_summary_df.empty:
        return None

    raw_df = theme_summary_df.merge(flow_summary_df, on="group_name", how="inner")
    if raw_df.empty:
        return None

    status_order = {"漲潮": 0, "輪動": 1, "觀望": 2, "退潮": 3}
    raw_df["fund_status_order"] = raw_df["fund_status"].map(status_order).fillna(9)
    raw_df["bubble_size"] = raw_df["net_20d_yi"].abs().clip(lower=1.0)
    raw_df = raw_df.sort_values(
        ["fund_status_order", "net_5d_yi", "accel_yi", "latest_turnover"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)

    display_df = raw_df.copy()
    display_df["狀態"] = display_df["fund_status"]
    display_df["細分產業"] = display_df["group_name"]
    display_df["成分股"] = display_df.apply(
        lambda row: f"{int(row['covered_stock_count'])}/{int(row['stock_count'])}",
        axis=1,
    )
    display_df["今日淨買超(億)"] = display_df["net_1d_yi"].map(_format_signed_yi)
    display_df["5日淨買超(億)"] = display_df["net_5d_yi"].map(_format_signed_yi)
    display_df["20日累計(億)"] = display_df["net_20d_yi"].map(_format_signed_yi)
    display_df["資金加速度"] = display_df["accel_yi"].map(_format_signed_yi)
    display_df["今日漲跌"] = display_df["tide_chg_1d"].map(_format_pct)
    display_df["5日漲跌"] = display_df["tide_chg_5d"].map(_format_pct)
    display_df["資金停留"] = display_df.apply(
        lambda row: _format_flow_streak(row["inflow_streak"], row["accel_yi"]),
        axis=1,
    )
    display_df["代表股"] = display_df["representative_stocks"]
    display_df = display_df[
        [
            "狀態",
            "細分產業",
            "成分股",
            "今日淨買超(億)",
            "5日淨買超(億)",
            "20日累計(億)",
            "資金加速度",
            "今日漲跌",
            "5日漲跌",
            "資金停留",
            "代表股",
        ]
    ]

    stock_data = tide_payload.get("stock_data") or {}
    profiles_df = get_company_profiles_df()[["code", "name_zh"]].copy()
    profiles_df["code"] = profiles_df["code"].astype(str).str.zfill(4)
    name_lookup = profiles_df.drop_duplicates(subset=["code"], keep="last").set_index("code")["name_zh"].to_dict()
    stock_rows = []
    for sector in sectors:
        group_name = str((sector or {}).get("name") or "").strip()
        if group_name not in set(raw_df["group_name"]):
            continue
        for raw_code in (sector or {}).get("stocks") or []:
            code = str(raw_code or "").strip().zfill(4)
            stock_metrics = stock_data.get(code) or {}
            stock_rows.append(
                {
                    "group_name": group_name,
                    "code": code,
                    "name_zh": name_lookup.get(code, ""),
                    "close": _safe_float(stock_metrics.get("price")),
                    "net_1d_yi": _safe_float(stock_metrics.get("net_1d_yi")) or 0.0,
                    "net_5d_yi": _safe_float(stock_metrics.get("net_5d_yi")) or 0.0,
                    "net_20d_yi": _safe_float(stock_metrics.get("net_20d_yi")) or 0.0,
                }
            )

    return {
        "used_date": tide_payload.get("date"),
        "history_trade_days": 20,
        "raw_df": raw_df,
        "display_df": display_df,
        "stock_flow_df": pd.DataFrame(stock_rows),
        "source": "Tide latest.json",
        "updated_at": tide_payload.get("updated_at"),
    }


@lru_cache(maxsize=64)
def _load_price_cache_for_dates(date_tuple, code_tuple):
    if not date_tuple or not code_tuple:
        return pd.DataFrame(columns=["trade_date", "code", "close"])

    placeholders_dates = ",".join("?" for _ in date_tuple)
    symbols = tuple(f"{code}.TW" for code in code_tuple)
    placeholders_symbols = ",".join("?" for _ in symbols)
    with sqlite3.connect(db_path("price_cache.db")) as conn:
        price_df = pd.read_sql_query(
            f"""
            SELECT trade_date, symbol, close
            FROM price_history
            WHERE trade_date IN ({placeholders_dates})
              AND symbol IN ({placeholders_symbols})
            """,
            conn,
            params=tuple(date_tuple) + symbols,
        )

    if price_df.empty:
        return pd.DataFrame(columns=["trade_date", "code", "close"])

    price_df["code"] = price_df["symbol"].astype(str).str.replace(r"\.TW$", "", regex=True).str.zfill(4)
    price_df["trade_date"] = pd.to_datetime(price_df["trade_date"]).dt.strftime("%Y-%m-%d")
    price_df["close"] = pd.to_numeric(price_df["close"], errors="coerce")
    return price_df[["trade_date", "code", "close"]].dropna(subset=["close"])


@lru_cache(maxsize=64)
def _load_institutional_flow_cache(anchor_date_text, trading_days):
    anchor_date_text = pd.to_datetime(anchor_date_text).strftime("%Y-%m-%d")
    with sqlite3.connect(db_path("chip_cache.db")) as conn:
        date_rows = conn.execute(
            """
            SELECT DISTINCT trade_date
            FROM institutional_trading
            WHERE market = 'TWSE'
              AND trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (anchor_date_text, int(trading_days)),
        ).fetchall()
        dates = tuple(sorted(row[0] for row in date_rows))
        if not dates:
            return pd.DataFrame(), tuple()

        placeholders = ",".join("?" for _ in dates)
        flow_df = pd.read_sql_query(
            f"""
            SELECT trade_date, code, name_zh, total_net
            FROM institutional_trading
            WHERE market = 'TWSE'
              AND trade_date IN ({placeholders})
            """,
            conn,
            params=dates,
        )

    if flow_df.empty:
        return pd.DataFrame(), dates

    flow_df["trade_date"] = pd.to_datetime(flow_df["trade_date"]).dt.strftime("%Y-%m-%d")
    flow_df["code"] = flow_df["code"].astype(str).str.zfill(4)
    flow_df["total_net"] = pd.to_numeric(flow_df["total_net"], errors="coerce").fillna(0.0)

    codes = tuple(sorted(flow_df["code"].dropna().unique()))
    price_df = _load_price_cache_for_dates(dates, codes)
    if price_df.empty:
        flow_df["close"] = pd.NA
        flow_df["net_amount_yi"] = pd.NA
    else:
        flow_df = flow_df.merge(price_df, on=["trade_date", "code"], how="left")
        flow_df["net_amount_yi"] = flow_df["total_net"] * flow_df["close"] / 100_000_000

    return flow_df, dates


def build_sector_fund_flow_report(theme_summary_df, anchor_date, trading_days=20):
    empty_result = {
        "used_date": None,
        "history_trade_days": 0,
        "raw_df": pd.DataFrame(),
        "display_df": pd.DataFrame(),
        "stock_flow_df": pd.DataFrame(),
    }
    if theme_summary_df.empty:
        return empty_result

    try:
        tide_report = _build_tide_sector_fund_flow_report(theme_summary_df)
        if tide_report is not None:
            return tide_report
    except Exception:
        pass

    flow_df, flow_dates = _load_institutional_flow_cache(
        pd.to_datetime(anchor_date).strftime("%Y-%m-%d"),
        int(trading_days),
    )
    if flow_df.empty or not flow_dates:
        return empty_result

    membership_df = _build_theme_membership_df()
    if membership_df.empty:
        return {**empty_result, "used_date": flow_dates[-1], "history_trade_days": len(flow_dates)}

    merged_df = flow_df.merge(
        membership_df[["code", "group_name", "name_zh", "market"]].drop_duplicates(subset=["code", "group_name"]),
        on="code",
        how="inner",
        suffixes=("", "_profile"),
    )
    merged_df = merged_df.dropna(subset=["net_amount_yi"])
    if merged_df.empty:
        return {**empty_result, "used_date": flow_dates[-1], "history_trade_days": len(flow_dates)}

    latest_date = flow_dates[-1]
    daily_df = (
        merged_df.groupby(["group_name", "trade_date"])
        .agg(
            institutional_stock_count=("code", "nunique"),
            net_amount_yi=("net_amount_yi", "sum"),
        )
        .reset_index()
        .sort_values(["group_name", "trade_date"])
    )

    sector_rows = []
    for group_name, group_df in daily_df.groupby("group_name"):
        group_df = group_df.set_index("trade_date").reindex(flow_dates).fillna({"net_amount_yi": 0.0, "institutional_stock_count": 0})
        amount_series = pd.to_numeric(group_df["net_amount_yi"], errors="coerce").fillna(0.0)
        covered_count = int(pd.to_numeric(group_df["institutional_stock_count"], errors="coerce").fillna(0).max())

        latest_amount = float(amount_series.iloc[-1])
        net_5d = float(amount_series.tail(min(5, len(amount_series))).sum())
        net_20d = float(amount_series.sum())
        accel_yi = (net_5d / min(5, len(amount_series))) - (net_20d / len(amount_series))
        latest_direction = 1 if latest_amount > 0 else -1 if latest_amount < 0 else 0
        streak = 0
        if latest_direction:
            for value in reversed(amount_series.tolist()):
                if (value > 0 and latest_direction > 0) or (value < 0 and latest_direction < 0):
                    streak += latest_direction
                else:
                    break

        sector_rows.append(
            {
                "group_name": group_name,
                "fund_status": _classify_fund_flow(net_5d, accel_yi),
                "net_1d_yi": latest_amount,
                "net_5d_yi": net_5d,
                "net_20d_yi": net_20d,
                "accel_yi": accel_yi,
                "inflow_streak": int(streak),
                "covered_stock_count": covered_count,
            }
        )

    flow_summary_df = pd.DataFrame(sector_rows)
    if flow_summary_df.empty:
        return {**empty_result, "used_date": latest_date, "history_trade_days": len(flow_dates)}

    raw_df = theme_summary_df.merge(flow_summary_df, on="group_name", how="inner")
    if raw_df.empty:
        return {**empty_result, "used_date": latest_date, "history_trade_days": len(flow_dates)}

    status_order = {"漲潮": 0, "輪動": 1, "觀望": 2, "退潮": 3}
    raw_df["fund_status_order"] = raw_df["fund_status"].map(status_order).fillna(9)
    raw_df["bubble_size"] = raw_df["net_20d_yi"].abs().clip(lower=1.0)
    raw_df = raw_df.sort_values(
        ["fund_status_order", "net_5d_yi", "accel_yi", "latest_turnover"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)

    display_df = raw_df.copy()
    display_df["狀態"] = display_df["fund_status"]
    display_df["細分產業"] = display_df["group_name"]
    display_df["成分股"] = display_df.apply(
        lambda row: f"{int(row['covered_stock_count'])}/{int(row['stock_count'])}",
        axis=1,
    )
    display_df["今日淨買超(億)"] = display_df["net_1d_yi"].map(_format_signed_yi)
    display_df["5日淨買超(億)"] = display_df["net_5d_yi"].map(_format_signed_yi)
    display_df["20日累計(億)"] = display_df["net_20d_yi"].map(_format_signed_yi)
    display_df["資金加速度"] = display_df["accel_yi"].map(_format_signed_yi)
    display_df["今日漲跌"] = display_df["latest_change_pct"].map(_format_pct)
    display_df["5日漲跌"] = display_df["five_day_change_pct"].map(_format_pct)
    display_df["資金停留"] = display_df.apply(
        lambda row: _format_flow_streak(row["inflow_streak"], row["accel_yi"]),
        axis=1,
    )
    display_df["代表股"] = display_df["representative_stocks"]
    display_df = display_df[
        [
            "狀態",
            "細分產業",
            "成分股",
            "今日淨買超(億)",
            "5日淨買超(億)",
            "20日累計(億)",
            "資金加速度",
            "今日漲跌",
            "5日漲跌",
            "資金停留",
            "代表股",
        ]
    ]

    stock_daily_df = (
        merged_df.groupby(["group_name", "code", "name_zh_profile", "trade_date"])
        .agg(
            net_amount_yi=("net_amount_yi", "sum"),
            close=("close", "last"),
        )
        .reset_index()
    )
    stock_rows = []
    for (group_name, code, name_zh), group_df in stock_daily_df.groupby(["group_name", "code", "name_zh_profile"]):
        group_df = group_df.set_index("trade_date").reindex(flow_dates)
        amount_series = pd.to_numeric(group_df["net_amount_yi"], errors="coerce").fillna(0.0)
        close_series = pd.to_numeric(group_df["close"], errors="coerce")
        stock_rows.append(
            {
                "group_name": group_name,
                "code": code,
                "name_zh": name_zh,
                "close": close_series.dropna().iloc[-1] if close_series.notna().any() else None,
                "net_1d_yi": float(amount_series.iloc[-1]),
                "net_5d_yi": float(amount_series.tail(min(5, len(amount_series))).sum()),
                "net_20d_yi": float(amount_series.sum()),
            }
        )
    stock_flow_df = pd.DataFrame(stock_rows)

    return {
        "used_date": latest_date,
        "history_trade_days": len(flow_dates),
        "raw_df": raw_df,
        "display_df": display_df,
        "stock_flow_df": stock_flow_df,
    }


def _build_theme_members_display_df(component_df, selected_group):
    if component_df.empty or not selected_group:
        return pd.DataFrame()

    display_df = component_df[component_df["group_name"] == selected_group].copy()
    if display_df.empty:
        return pd.DataFrame()

    if "market" not in display_df.columns and "market_x" in display_df.columns:
        display_df["market"] = display_df["market_x"]
    if "name" not in display_df.columns and "name_x" in display_df.columns:
        display_df["name"] = display_df["name_x"]

    display_df = display_df.sort_values(["turnover_value", "volume"], ascending=[False, False]).copy()
    display_df["估算成交值"] = display_df["turnover_value"].map(_format_turnover_billions)
    display_df["成交量"] = display_df["volume"].map(_format_volume_lots)
    display_df["漲跌幅(%)"] = display_df["change_pct"].map(_format_pct)
    display_df["收盤"] = display_df["close"].map(lambda value: f"{value:,.2f}" if pd.notna(value) else "-")
    display_df["classification_source"] = display_df["classification_source"].map(_format_classification_source)
    return display_df.rename(
        columns={
            "market": "市場",
            "code": "代碼",
            "name": "名稱",
            "official_industry": "官方產業",
            "classification_source": "分類來源",
        }
    )[
        ["市場", "代碼", "名稱", "官方產業", "分類來源", "收盤", "漲跌幅(%)", "成交量", "估算成交值"]
    ].reset_index(drop=True)


def _build_display_df(summary_df, group_label):
    if summary_df.empty:
        return pd.DataFrame()

    display_df = summary_df.copy()
    display_df["報價"] = display_df["latest_index"].map(_format_index)
    display_df["單日(%)"] = display_df["latest_change_pct"].map(_format_pct)
    display_df["5日(%)"] = display_df["five_day_change_pct"].map(_format_pct)
    display_df["當日成交量"] = display_df["latest_volume"].map(_format_volume_lots)
    display_df["5日均量"] = display_df["avg_volume_5d"].map(_format_volume_lots)
    display_df["量比"] = display_df["volume_ratio"].map(_format_ratio)
    display_df["當日成交值"] = display_df["latest_turnover"].map(_format_turnover_billions)
    display_df["5日均成交值"] = display_df["avg_turnover_5d"].map(_format_turnover_billions)
    display_df["成交值比"] = display_df["turnover_ratio"].map(_format_ratio)
    display_df["上漲家數"] = display_df.apply(
        lambda row: f"{int(row['positive_count'])}/{int(row['stock_count'])}",
        axis=1,
    )
    display_df["輪動分數"] = display_df["rotation_score"].map(lambda value: f"{value:.1f}")
    display_df["分數1日變化"] = display_df["score_delta_1d"].map(_format_score_delta)
    display_df["分數3日變化"] = display_df["score_delta_3d"].map(_format_score_delta)
    display_df = display_df.rename(
        columns={
            "group_name": group_label,
            "parent_industry": "官方母產業",
            "limit_up_count": "漲停家數",
            "locked_up_count": "鎖漲停家數",
            "representative_stocks": "代表股",
        }
    )
    return display_df[
        [
            group_label,
            "官方母產業",
            "報價",
            "單日(%)",
            "5日(%)",
            "當日成交量",
            "5日均量",
            "量比",
            "當日成交值",
            "5日均成交值",
            "成交值比",
            "上漲家數",
            "漲停家數",
            "鎖漲停家數",
            "代表股",
            "輪動分數",
            "分數1日變化",
            "分數3日變化",
        ]
    ]


def load_twse_tech_index_snapshot():
    rows = request_json(
        "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX",
        headers={"Accept": "application/json,text/plain,*/*"},
        encoding="utf-8",
    )
    index_df = pd.DataFrame(rows)
    if index_df.empty:
        return None

    index_df = index_df[index_df["指數"].isin(TWSE_TECH_INDEX_NAMES)].copy()
    if index_df.empty:
        return None

    index_df["日期"] = index_df["日期"].map(_roc_date_to_iso)
    index_df["收盤指數"] = index_df["收盤指數"].map(_safe_float)
    index_df["漲跌點數"] = index_df["漲跌點數"].astype(str).str.replace(",", "", regex=False).map(_safe_float)
    index_df["漲跌百分比"] = index_df["漲跌百分比"].astype(str).str.replace("%", "", regex=False).map(_safe_float)
    index_df = index_df.sort_values(
        by="指數",
        key=lambda series: series.map({name: idx for idx, name in enumerate(TWSE_TECH_INDEX_NAMES)}).fillna(999),
    ).reset_index(drop=True)

    display_df = index_df.copy()
    display_df["收盤指數"] = display_df["收盤指數"].map(lambda value: f"{value:,.2f}" if pd.notna(value) else "-")
    display_df["漲跌點數"] = display_df["漲跌點數"].map(lambda value: f"{value:,.2f}" if pd.notna(value) else "-")
    display_df["漲跌百分比"] = display_df["漲跌百分比"].map(_format_pct)
    return {
        "used_date": index_df["日期"].iloc[0],
        "raw_df": index_df,
        "display_df": display_df[["指數", "收盤指數", "漲跌點數", "漲跌百分比"]],
    }


def build_industry_rotation_bundle(anchor_date, history_trade_days=8):
    history_df, collected_dates = _load_market_history(anchor_date, history_trade_days=history_trade_days)
    if history_df.empty:
        return None

    theme_summary_df, theme_series_df, latest_theme_component_df = _build_rotation_summary(
        history_df,
        _build_theme_membership_df(),
    )
    industry_summary_df, industry_series_df, _ = _build_rotation_summary(
        history_df,
        _build_official_industry_membership_df(),
    )
    twse_index_snapshot = load_twse_tech_index_snapshot()
    fund_flow_report = build_sector_fund_flow_report(theme_summary_df, anchor_date, trading_days=20)

    latest_date = history_df["trade_date"].max().strftime("%Y-%m-%d")
    top_theme_name = theme_summary_df.iloc[0]["group_name"] if not theme_summary_df.empty else None
    top_industry_name = industry_summary_df.iloc[0]["group_name"] if not industry_summary_df.empty else None

    summary = {
        "used_date": latest_date,
        "history_trade_days": len(collected_dates),
        "theme_count": int(len(theme_summary_df)),
        "industry_count": int(len(industry_summary_df)),
        "top_theme": top_theme_name,
        "top_theme_volume_ratio": (
            float(theme_summary_df.iloc[0]["volume_ratio"])
            if (top_theme_name and pd.notna(theme_summary_df.iloc[0]["volume_ratio"]))
            else None
        ),
        "top_industry": top_industry_name,
    }

    return {
        "summary": summary,
        "theme_report": {
            "summary_df": theme_summary_df,
            "display_df": _build_display_df(theme_summary_df, "細分產業"),
            "series_df": theme_series_df,
            "component_df": latest_theme_component_df,
            "fund_flow_report": fund_flow_report,
        },
        "industry_report": {
            "summary_df": industry_summary_df,
            "display_df": _build_display_df(industry_summary_df, "官方產業"),
            "series_df": industry_series_df,
        },
        "twse_index_snapshot": twse_index_snapshot,
    }


def build_theme_member_snapshot(anchor_date, history_trade_days, theme_name):
    bundle = build_industry_rotation_bundle(anchor_date, history_trade_days=history_trade_days)
    if not bundle:
        return pd.DataFrame()
    return _build_theme_members_display_df(bundle["theme_report"]["component_df"], theme_name)


def build_theme_member_display_df(component_df, theme_name):
    return _build_theme_members_display_df(component_df, theme_name)


def build_homepage_industry_flow_bundle(anchor_date, history_trade_days=21):
    history_df, collected_dates = _load_market_history(anchor_date, history_trade_days=history_trade_days, max_calendar_lookback=45)
    if history_df.empty:
        return None

    membership_df = _build_all_official_industry_membership_df()
    if membership_df.empty:
        return None

    merged_df = history_df.merge(
        membership_df[["code", "group_name"]].drop_duplicates(subset=["code", "group_name"]),
        on="code",
        how="inner",
    )
    if merged_df.empty:
        return None

    daily_df = (
        merged_df.groupby(["group_name", "trade_date"])
        .agg(
            stock_count=("code", "nunique"),
            total_turnover=("turnover_value", "sum"),
            total_volume=("volume", "sum"),
            avg_change_pct=("change_pct", "mean"),
        )
        .reset_index()
        .sort_values(["group_name", "trade_date"])
        .reset_index(drop=True)
    )
    if daily_df.empty:
        return None

    latest_date = daily_df["trade_date"].max()
    summary_rows = []
    for group_name, group_df in daily_df.groupby("group_name"):
        group_df = group_df.sort_values("trade_date").reset_index(drop=True)
        latest_row = group_df.iloc[-1]
        baseline_df = group_df.iloc[:-1].tail(20)
        avg_turnover_20d = baseline_df["total_turnover"].mean() if not baseline_df.empty else None
        turnover_ratio_20d = _safe_divide(latest_row["total_turnover"], avg_turnover_20d)
        turnover_delta_pct = (
            ((float(latest_row["total_turnover"]) / float(avg_turnover_20d)) - 1.0) * 100.0
            if avg_turnover_20d not in {None, 0} and not pd.isna(avg_turnover_20d)
            else None
        )
        summary_rows.append(
            {
                "industry": group_name,
                "latest_turnover": _safe_float(latest_row["total_turnover"]),
                "avg_turnover_20d": _safe_float(avg_turnover_20d),
                "turnover_ratio_20d": turnover_ratio_20d,
                "turnover_delta_pct": turnover_delta_pct,
                "stock_count": int(latest_row["stock_count"]),
                "latest_volume": _safe_float(latest_row["total_volume"]),
                "latest_change_pct": _safe_float(latest_row["avg_change_pct"]),
                "history_points": int(len(group_df)),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if summary_df.empty:
        return None

    summary_df = summary_df.sort_values(
        ["turnover_ratio_20d", "latest_turnover", "stock_count"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    display_df = summary_df.copy()
    display_df["產業"] = display_df["industry"]
    display_df["當日成交金額"] = display_df["latest_turnover"].map(_format_turnover_billions)
    display_df["20日均成交金額"] = display_df["avg_turnover_20d"].map(_format_turnover_billions)
    display_df["上升比例"] = display_df["turnover_ratio_20d"].map(_format_ratio)
    display_df["高於20日均值(%)"] = display_df["turnover_delta_pct"].map(_format_pct)
    display_df["平均漲跌幅(%)"] = display_df["latest_change_pct"].map(_format_pct)
    display_df["成分股數"] = display_df["stock_count"].map(lambda value: f"{int(value)}")
    display_df = display_df[
        [
            "產業",
            "當日成交金額",
            "20日均成交金額",
            "上升比例",
            "高於20日均值(%)",
            "平均漲跌幅(%)",
            "成分股數",
        ]
    ]

    return {
        "used_date": latest_date.strftime("%Y-%m-%d"),
        "history_trade_days": len(collected_dates),
        "summary_df": summary_df,
        "display_df": display_df,
    }
