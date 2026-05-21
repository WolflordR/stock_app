from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

import pandas as pd

from company_links_db import get_company_profiles_df
from company_links_db import get_company_theme_membership_df
from http_utils import request_json
from industry_taxonomy import TECH_INDUSTRY_NAMES
from industry_taxonomy import THEME_DEFINITIONS
from industry_taxonomy import TWSE_TECH_INDEX_NAMES
from market_watch import fetch_tpex_daily_quotes
from market_watch import fetch_twse_daily_quotes


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


def _format_classification_source(value):
    return {
        "seed_code": "核心名單",
        "seed_alias": "別名擴充",
        "manual_override": "人工覆寫",
    }.get(value, value or "-")


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
    theme_df = get_company_theme_membership_df().copy()
    if theme_df.empty:
        return pd.DataFrame(columns=["code", "group_name", "parent_industry", "official_industry", "name_zh", "market", "source", "confidence", "note"])

    parent_industry_map = {
        definition["theme"]: definition.get("parent_industry") or ""
        for definition in THEME_DEFINITIONS
    }
    theme_df["code"] = theme_df["code"].astype(str).str.zfill(4)
    theme_df["group_name"] = theme_df["theme"].astype(str).str.strip()
    theme_df["official_industry"] = theme_df["industry"].fillna("").astype(str).str.strip()
    theme_df["parent_industry"] = theme_df["group_name"].map(parent_industry_map).fillna(theme_df["industry"]).fillna("未分類")
    return theme_df.rename(
        columns={
            "source": "classification_source",
            "note": "classification_note",
        }
    )[
        ["code", "group_name", "parent_industry", "official_industry", "name_zh", "market", "classification_source", "confidence", "classification_note"]
    ].drop_duplicates(subset=["code", "group_name"], keep="first")


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
