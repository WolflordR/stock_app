from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
from functools import lru_cache

import pandas as pd

from modules.market_map.market_map_db import _get_connection
from modules.market_map.market_map_db import ensure_market_map_db
from modules.market_map.market_map_db import refresh_market_map_db
from modules.market_map.market_map_events import ensure_market_map_topic_events
from modules.market_map.market_map_snapshot_store import get_latest_cached_snapshot_date
from modules.market_map.market_map_snapshot_store import load_cached_snapshot_bundle
from modules.market_map.market_map_snapshot_store import normalize_component_snapshot_df
from modules.market_map.market_map_snapshot_store import persist_snapshot_bundle
from modules.data_sources.market_watch import fetch_tpex_daily_quotes
from modules.data_sources.market_watch import fetch_twse_daily_quotes


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _load_assignment_base_df():
    ensure_market_map_db()
    with _get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                a.code,
                a.topic_name,
                a.source,
                a.confidence,
                t.group_name,
                t.parent_industry,
                t.description,
                t.news_query,
                t.topic_type,
                c.name_zh,
                c.market,
                c.yfinance_symbol,
                c.official_industry
            FROM map_topic_company_assignments a
            JOIN map_topics t ON a.topic_name = t.topic_name
            JOIN map_companies c ON a.code = c.code
            ORDER BY t.group_name, t.topic_name, a.code
            """,
            conn,
        )
    df["code"] = df["code"].astype(str).str.zfill(4)
    return df




@lru_cache(maxsize=16)
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


def _build_topic_snapshot(summary_df, component_df):
    if summary_df.empty:
        return pd.DataFrame()

    latest_date = summary_df["trade_date"].max()
    latest_component_df = component_df[component_df["trade_date"] == latest_date].copy()
    representative_map = (
        latest_component_df.sort_values(["topic_name", "turnover_value"], ascending=[True, False])
        .groupby("topic_name")
        .head(3)
        .groupby("topic_name")
        .apply(lambda group: " / ".join(f"{row['name']}({row['code']})" for _, row in group.iterrows()))
        .to_dict()
    )
    leader_map = (
        latest_component_df.sort_values(["topic_name", "change_pct", "turnover_value"], ascending=[True, False, False])
        .groupby("topic_name")
        .head(2)
        .groupby("topic_name")
        .apply(lambda group: " / ".join(f"{row['name']} {row['change_pct']:.2f}%" for _, row in group.iterrows() if pd.notna(row["change_pct"])))
        .to_dict()
    )
    laggard_map = (
        latest_component_df.sort_values(["topic_name", "change_pct", "turnover_value"], ascending=[True, True, False])
        .groupby("topic_name")
        .head(2)
        .groupby("topic_name")
        .apply(lambda group: " / ".join(f"{row['name']} {row['change_pct']:.2f}%" for _, row in group.iterrows() if pd.notna(row["change_pct"])))
        .to_dict()
    )

    rows = []
    for topic_name, topic_df in summary_df.groupby("topic_name"):
        topic_df = topic_df.sort_values("trade_date").reset_index(drop=True)
        latest_row = topic_df.iloc[-1]
        previous_df = topic_df.iloc[:-1]

        baseline_volume = previous_df["total_volume"].mean() if not previous_df.empty else None
        baseline_turnover = previous_df["total_turnover"].mean() if not previous_df.empty else None
        volume_ratio = (
            float(latest_row["total_volume"]) / float(baseline_volume)
            if baseline_volume not in {None, 0} and pd.notna(baseline_volume)
            else None
        )
        turnover_ratio = (
            float(latest_row["total_turnover"]) / float(baseline_turnover)
            if baseline_turnover not in {None, 0} and pd.notna(baseline_turnover)
            else None
        )

        index_level = 100.0
        index_levels = []
        for _, row in topic_df.iterrows():
            index_level *= 1.0 + (float(row["avg_change_pct"] or 0.0) / 100.0)
            index_levels.append(index_level)
        start_level = index_levels[0] if index_levels else None
        end_level = index_levels[-1] if index_levels else None
        five_day_change_pct = ((end_level / start_level) - 1.0) * 100.0 if start_level not in {None, 0} else None

        breadth_ratio = (
            float(latest_row["up_count"]) / float(latest_row["company_count"])
            if latest_row["company_count"] not in {None, 0}
            else 0.0
        )
        heat_score = (
            max(min(float(latest_row["avg_change_pct"] or 0.0), 6.0), -6.0) * 7.0
            + min(volume_ratio or 0.0, 3.0) * 12.0
            + min(turnover_ratio or 0.0, 3.0) * 10.0
            + breadth_ratio * 20.0
        )

        rows.append(
            {
                "group_name": latest_row["group_name"],
                "topic_name": topic_name,
                "parent_industry": latest_row["parent_industry"],
                "description": latest_row["description"],
                "news_query": latest_row["news_query"],
                "topic_type": latest_row["topic_type"],
                "used_date": latest_row["trade_date"].strftime("%Y-%m-%d"),
                "company_count": int(latest_row["company_count"]),
                "up_count": int(latest_row["up_count"]),
                "down_count": int(latest_row["down_count"]),
                "flat_count": int(latest_row["flat_count"]),
                "avg_change_pct": float(latest_row["avg_change_pct"]) if pd.notna(latest_row["avg_change_pct"]) else None,
                "five_day_change_pct": five_day_change_pct,
                "total_volume": float(latest_row["total_volume"]) if pd.notna(latest_row["total_volume"]) else None,
                "total_turnover": float(latest_row["total_turnover"]) if pd.notna(latest_row["total_turnover"]) else None,
                "volume_ratio": volume_ratio,
                "turnover_ratio": turnover_ratio,
                "heat_score": heat_score,
                "representative_stocks": representative_map.get(topic_name, "-"),
                "top_leaders": leader_map.get(topic_name, "-"),
                "top_laggards": laggard_map.get(topic_name, "-"),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["heat_score", "total_turnover", "avg_change_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def _build_group_snapshot(topic_snapshot_df, group_summary_df):
    if topic_snapshot_df.empty:
        return group_summary_df.copy()

    metrics_df = (
        topic_snapshot_df.groupby("group_name")
        .agg(
            avg_change_pct=("avg_change_pct", "mean"),
            five_day_change_pct=("five_day_change_pct", "mean"),
            avg_volume_ratio=("volume_ratio", "mean"),
            avg_turnover_ratio=("turnover_ratio", "mean"),
            total_turnover=("total_turnover", "sum"),
            heat_score=("heat_score", "mean"),
        )
        .reset_index()
    )
    merged_df = group_summary_df.merge(metrics_df, on="group_name", how="left")
    return merged_df.sort_values(
        ["sort_order", "heat_score", "total_turnover"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def get_market_map_page_bundle(anchor_date=None, history_trade_days=6, force_refresh=False):
    if force_refresh:
        refresh_market_map_db()
    ensure_market_map_db()

    if anchor_date is None:
        anchor_date = datetime.now().date()
    anchor_date_text = _to_date(anchor_date).strftime("%Y-%m-%d")

    if not force_refresh:
        latest_cached_snapshot_date = get_latest_cached_snapshot_date()
        if latest_cached_snapshot_date == anchor_date_text:
            bundle = load_cached_snapshot_bundle(
                latest_cached_snapshot_date,
                topic_catalog_df=get_market_map_topics_df(),
            )
            event_bundle = ensure_market_map_topic_events(anchor_date=latest_cached_snapshot_date)
            bundle["topic_event_summary_df"] = event_bundle["summary_df"]
            bundle["topic_event_item_df"] = event_bundle["item_df"]
            bundle["topic_event_source"] = event_bundle["source"]
            return bundle

    group_summary_df = get_market_map_group_summary_df()
    topic_catalog_df = get_market_map_topics_df()
    assignment_df = _load_assignment_base_df()
    if assignment_df.empty:
        return {
            "used_date": None,
            "group_summary_df": group_summary_df,
            "topic_catalog_df": topic_catalog_df,
            "topic_snapshot_df": pd.DataFrame(),
            "component_snapshot_df": pd.DataFrame(),
            "topic_event_summary_df": pd.DataFrame(),
            "topic_event_item_df": pd.DataFrame(),
            "topic_event_source": "empty",
            "snapshot_source": "empty",
        }

    history_df, collected_dates = _load_market_history_cached(
        anchor_date_text,
        int(history_trade_days),
        16,
    )
    if history_df.empty:
        bundle = {
            "used_date": None,
            "group_summary_df": group_summary_df,
            "topic_catalog_df": topic_catalog_df,
            "topic_snapshot_df": pd.DataFrame(),
            "component_snapshot_df": pd.DataFrame(),
            "topic_event_summary_df": pd.DataFrame(),
            "topic_event_item_df": pd.DataFrame(),
            "topic_event_source": "empty",
            "snapshot_source": "empty",
        }
        return bundle

    merged_df = history_df.merge(assignment_df, on="code", how="inner")
    if merged_df.empty:
        bundle = {
            "used_date": None,
            "group_summary_df": group_summary_df,
            "topic_catalog_df": topic_catalog_df,
            "topic_snapshot_df": pd.DataFrame(),
            "component_snapshot_df": pd.DataFrame(),
            "topic_event_summary_df": pd.DataFrame(),
            "topic_event_item_df": pd.DataFrame(),
            "topic_event_source": "empty",
            "snapshot_source": "empty",
        }
        return bundle

    summary_df = (
        merged_df.groupby(
            ["group_name", "topic_name", "parent_industry", "description", "news_query", "topic_type", "trade_date"]
        )
        .agg(
            company_count=("code", "nunique"),
            up_count=("change_pct", lambda series: int((pd.to_numeric(series, errors="coerce") > 0).sum())),
            down_count=("change_pct", lambda series: int((pd.to_numeric(series, errors="coerce") < 0).sum())),
            flat_count=("change_pct", lambda series: int((pd.to_numeric(series, errors="coerce") == 0).sum())),
            avg_change_pct=("change_pct", "mean"),
            total_volume=("volume", "sum"),
            total_turnover=("turnover_value", "sum"),
        )
        .reset_index()
        .sort_values(["topic_name", "trade_date"])
        .reset_index(drop=True)
    )

    topic_snapshot_df = _build_topic_snapshot(summary_df, merged_df)
    enriched_group_df = _build_group_snapshot(topic_snapshot_df, group_summary_df)

    latest_date = merged_df["trade_date"].max()
    component_snapshot_df = (
        merged_df[merged_df["trade_date"] == latest_date]
        .copy()
        .sort_values(["topic_name", "turnover_value", "change_pct"], ascending=[True, False, False])
        .reset_index(drop=True)
    )
    component_snapshot_df = normalize_component_snapshot_df(component_snapshot_df)

    bundle = {
        "used_date": latest_date.strftime("%Y-%m-%d"),
        "available_dates": list(collected_dates),
        "group_summary_df": enriched_group_df,
        "topic_catalog_df": topic_catalog_df,
        "topic_snapshot_df": topic_snapshot_df,
        "component_snapshot_df": component_snapshot_df,
        "snapshot_source": "fresh",
    }
    persist_snapshot_bundle(bundle)
    event_bundle = ensure_market_map_topic_events(anchor_date=bundle["used_date"])
    bundle["topic_event_summary_df"] = event_bundle["summary_df"]
    bundle["topic_event_item_df"] = event_bundle["item_df"]
    bundle["topic_event_source"] = event_bundle["source"]
    return bundle


def get_market_map_group_summary_df(force_refresh=False):
    if force_refresh:
        refresh_market_map_db()
    ensure_market_map_db()
    with _get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                g.group_name AS group_name,
                g.sort_order AS sort_order,
                g.is_tech AS is_tech,
                COUNT(DISTINCT t.topic_name) AS topic_count,
                COUNT(DISTINCT a.code) AS company_count
            FROM map_groups g
            LEFT JOIN map_topics t ON g.group_name = t.group_name
            LEFT JOIN map_topic_company_assignments a ON t.topic_name = a.topic_name
            GROUP BY g.group_name, g.sort_order, g.is_tech
            ORDER BY g.sort_order, g.group_name
            """,
            conn,
        )
    return df


def get_market_map_topics_df(group_name=None, force_refresh=False):
    if force_refresh:
        refresh_market_map_db()
    ensure_market_map_db()
    with _get_connection() as conn:
        if group_name:
            df = pd.read_sql_query(
                """
                SELECT
                    t.group_name,
                    t.topic_name,
                    t.parent_industry,
                    t.topic_type,
                    t.is_tech,
                    t.description,
                    t.news_query,
                    COUNT(DISTINCT a.code) AS company_count
                FROM map_topics t
                LEFT JOIN map_topic_company_assignments a ON t.topic_name = a.topic_name
                WHERE t.group_name = ?
                GROUP BY t.group_name, t.topic_name, t.parent_industry, t.topic_type, t.is_tech, t.description, t.news_query, t.sort_order
                ORDER BY t.sort_order, t.topic_name
                """,
                conn,
                params=(group_name,),
            )
        else:
            df = pd.read_sql_query(
                """
                SELECT
                    t.group_name,
                    t.topic_name,
                    t.parent_industry,
                    t.topic_type,
                    t.is_tech,
                    t.description,
                    t.news_query,
                    COUNT(DISTINCT a.code) AS company_count
                FROM map_topics t
                LEFT JOIN map_topic_company_assignments a ON t.topic_name = a.topic_name
                GROUP BY t.group_name, t.topic_name, t.parent_industry, t.topic_type, t.is_tech, t.description, t.news_query, t.sort_order
                ORDER BY t.group_name, t.sort_order, t.topic_name
                """,
                conn,
            )
    return df


def get_market_map_topic_members_df(topic_name, force_refresh=False):
    if force_refresh:
        refresh_market_map_db()
    ensure_market_map_db()
    with _get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                a.code,
                c.name_zh,
                c.full_name_zh,
                c.market,
                c.yfinance_symbol,
                c.official_industry,
                a.source,
                a.confidence,
                a.note,
                a.updated_at
            FROM map_topic_company_assignments a
            JOIN map_companies c ON a.code = c.code
            WHERE a.topic_name = ?
            ORDER BY a.confidence DESC, a.code
            """,
            conn,
            params=(topic_name,),
        )
    return df


def get_market_map_topic_heatmap_df(topic_name, anchor_date=None, history_trade_days=10):
    ensure_market_map_db()
    normalized_topic_name = str(topic_name or "").strip()
    if not normalized_topic_name:
        return pd.DataFrame()

    if anchor_date is None:
        anchor_date = datetime.now().date()
    anchor_date_text = _to_date(anchor_date).strftime("%Y-%m-%d")

    assignment_df = _load_assignment_base_df()
    assignment_df = assignment_df[assignment_df["topic_name"] == normalized_topic_name].copy()
    if assignment_df.empty:
        return pd.DataFrame()

    history_df, _ = _load_market_history_cached(anchor_date_text, int(history_trade_days), 45)
    if history_df.empty:
        return pd.DataFrame()

    merged_df = history_df.merge(assignment_df, on="code", how="inner")
    if merged_df.empty:
        return pd.DataFrame()

    merged_df = merged_df.sort_values(["code", "trade_date"]).reset_index(drop=True)

    rows = []
    for code, company_df in merged_df.groupby("code"):
        company_df = company_df.sort_values("trade_date").reset_index(drop=True)
        latest_row = company_df.iloc[-1]

        def _window_change(days):
            window_df = company_df.tail(days)
            if len(window_df) < 2:
                return None
            start_close = pd.to_numeric(window_df.iloc[0].get("close"), errors="coerce")
            end_close = pd.to_numeric(window_df.iloc[-1].get("close"), errors="coerce")
            if pd.isna(start_close) or pd.isna(end_close) or not start_close:
                return None
            return float((end_close / start_close - 1.0) * 100.0)

        rows.append(
            {
                "topic_name": normalized_topic_name,
                "code": str(code).zfill(4),
                "name": latest_row.get("name_zh") or latest_row.get("name") or str(code).zfill(4),
                "market": latest_row.get("market"),
                "official_industry": latest_row.get("official_industry"),
                "change_pct": pd.to_numeric(latest_row.get("change_pct"), errors="coerce"),
                "week_change_pct": _window_change(5),
                "month_change_pct": _window_change(20),
                "turnover_value": pd.to_numeric(latest_row.get("turnover_value"), errors="coerce"),
                "volume": pd.to_numeric(latest_row.get("volume"), errors="coerce"),
            }
        )

    heatmap_df = pd.DataFrame(rows)
    if heatmap_df.empty:
        return heatmap_df
    return heatmap_df.sort_values(["turnover_value", "change_pct"], ascending=[False, False]).reset_index(drop=True)
