from __future__ import annotations

from datetime import datetime

import pandas as pd

from modules.market_map.market_map_db import _get_connection
from modules.market_map.market_map_db import ensure_market_map_db


def normalize_component_snapshot_df(component_snapshot_df):
    if component_snapshot_df.empty:
        return component_snapshot_df.copy()

    normalized_df = component_snapshot_df.copy()
    if "market" not in normalized_df.columns:
        for column_name in ("market_x", "market_y"):
            if column_name in normalized_df.columns:
                normalized_df["market"] = normalized_df[column_name]
                break
    if "official_industry" not in normalized_df.columns:
        for column_name in ("official_industry_x", "official_industry_y"):
            if column_name in normalized_df.columns:
                normalized_df["official_industry"] = normalized_df[column_name]
                break
    if "yfinance_symbol" not in normalized_df.columns:
        for column_name in ("yfinance_symbol_x", "yfinance_symbol_y"):
            if column_name in normalized_df.columns:
                normalized_df["yfinance_symbol"] = normalized_df[column_name]
                break
    return normalized_df.loc[:, ~normalized_df.columns.duplicated()].copy()


def load_cached_snapshot_bundle(snapshot_date, *, topic_catalog_df):
    ensure_market_map_db()
    with _get_connection() as conn:
        topic_snapshot_df = pd.read_sql_query(
            """
            SELECT
                snapshot_date AS used_date,
                group_name,
                topic_name,
                parent_industry,
                description,
                news_query,
                topic_type,
                company_count,
                up_count,
                down_count,
                flat_count,
                avg_change_pct,
                five_day_change_pct,
                total_volume,
                total_turnover,
                volume_ratio,
                turnover_ratio,
                heat_score,
                representative_stocks,
                top_leaders,
                top_laggards,
                updated_at
            FROM map_topic_daily_snapshots
            WHERE snapshot_date = ?
            ORDER BY heat_score DESC, total_turnover DESC, avg_change_pct DESC
            """,
            conn,
            params=(snapshot_date,),
        )
        group_summary_df = pd.read_sql_query(
            """
            SELECT
                group_name,
                sort_order,
                is_tech,
                topic_count,
                company_count,
                avg_change_pct,
                five_day_change_pct,
                avg_volume_ratio,
                avg_turnover_ratio,
                total_turnover,
                heat_score,
                updated_at
            FROM map_group_daily_snapshots
            WHERE snapshot_date = ?
            ORDER BY sort_order, heat_score DESC, total_turnover DESC
            """,
            conn,
            params=(snapshot_date,),
        )
        component_snapshot_df = pd.read_sql_query(
            """
            SELECT
                snapshot_date,
                topic_name,
                code,
                name,
                market,
                yfinance_symbol,
                official_industry,
                source,
                confidence,
                change_pct,
                volume,
                turnover_value,
                updated_at
            FROM map_component_daily_snapshots
            WHERE snapshot_date = ?
            ORDER BY topic_name, turnover_value DESC, change_pct DESC
            """,
            conn,
            params=(snapshot_date,),
        )

    return {
        "used_date": snapshot_date,
        "available_dates": [snapshot_date],
        "group_summary_df": group_summary_df,
        "topic_catalog_df": topic_catalog_df,
        "topic_snapshot_df": topic_snapshot_df,
        "component_snapshot_df": component_snapshot_df,
        "snapshot_source": "cache",
    }


def get_latest_cached_snapshot_date():
    ensure_market_map_db()
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(snapshot_date) AS snapshot_date FROM map_topic_daily_snapshots"
        ).fetchone()
    return row["snapshot_date"] if row and row["snapshot_date"] else None


def persist_snapshot_bundle(bundle):
    used_date = str(bundle.get("used_date") or "").strip()
    if not used_date:
        return

    updated_at = datetime.now().isoformat(timespec="seconds")
    topic_snapshot_df = bundle["topic_snapshot_df"].copy()
    group_summary_df = bundle["group_summary_df"].copy()
    component_snapshot_df = normalize_component_snapshot_df(bundle["component_snapshot_df"].copy())

    if not topic_snapshot_df.empty:
        topic_snapshot_df["snapshot_date"] = used_date
        topic_snapshot_df["updated_at"] = updated_at
    if not group_summary_df.empty:
        group_summary_df["snapshot_date"] = used_date
        group_summary_df["updated_at"] = updated_at
    if not component_snapshot_df.empty:
        component_snapshot_df["snapshot_date"] = used_date
        component_snapshot_df["updated_at"] = updated_at

    with _get_connection() as conn:
        conn.execute("DELETE FROM map_topic_daily_snapshots WHERE snapshot_date = ?", (used_date,))
        conn.execute("DELETE FROM map_group_daily_snapshots WHERE snapshot_date = ?", (used_date,))
        conn.execute("DELETE FROM map_component_daily_snapshots WHERE snapshot_date = ?", (used_date,))

        if not topic_snapshot_df.empty:
            conn.executemany(
                """
                INSERT INTO map_topic_daily_snapshots (
                    snapshot_date, group_name, topic_name, parent_industry, description, news_query, topic_type,
                    company_count, up_count, down_count, flat_count, avg_change_pct, five_day_change_pct,
                    total_volume, total_turnover, volume_ratio, turnover_ratio, heat_score,
                    representative_stocks, top_leaders, top_laggards, updated_at
                ) VALUES (
                    :snapshot_date, :group_name, :topic_name, :parent_industry, :description, :news_query, :topic_type,
                    :company_count, :up_count, :down_count, :flat_count, :avg_change_pct, :five_day_change_pct,
                    :total_volume, :total_turnover, :volume_ratio, :turnover_ratio, :heat_score,
                    :representative_stocks, :top_leaders, :top_laggards, :updated_at
                )
                """,
                topic_snapshot_df[
                    [
                        "snapshot_date",
                        "group_name",
                        "topic_name",
                        "parent_industry",
                        "description",
                        "news_query",
                        "topic_type",
                        "company_count",
                        "up_count",
                        "down_count",
                        "flat_count",
                        "avg_change_pct",
                        "five_day_change_pct",
                        "total_volume",
                        "total_turnover",
                        "volume_ratio",
                        "turnover_ratio",
                        "heat_score",
                        "representative_stocks",
                        "top_leaders",
                        "top_laggards",
                        "updated_at",
                    ]
                ].to_dict(orient="records"),
            )

        if not group_summary_df.empty:
            conn.executemany(
                """
                INSERT INTO map_group_daily_snapshots (
                    snapshot_date, group_name, sort_order, is_tech, topic_count, company_count,
                    avg_change_pct, five_day_change_pct, avg_volume_ratio, avg_turnover_ratio,
                    total_turnover, heat_score, updated_at
                ) VALUES (
                    :snapshot_date, :group_name, :sort_order, :is_tech, :topic_count, :company_count,
                    :avg_change_pct, :five_day_change_pct, :avg_volume_ratio, :avg_turnover_ratio,
                    :total_turnover, :heat_score, :updated_at
                )
                """,
                group_summary_df[
                    [
                        "snapshot_date",
                        "group_name",
                        "sort_order",
                        "is_tech",
                        "topic_count",
                        "company_count",
                        "avg_change_pct",
                        "five_day_change_pct",
                        "avg_volume_ratio",
                        "avg_turnover_ratio",
                        "total_turnover",
                        "heat_score",
                        "updated_at",
                    ]
                ].to_dict(orient="records"),
            )

        if not component_snapshot_df.empty:
            component_records_df = component_snapshot_df.copy()
            if "name" not in component_records_df.columns and "name_zh" in component_records_df.columns:
                component_records_df["name"] = component_records_df["name_zh"]
            conn.executemany(
                """
                INSERT INTO map_component_daily_snapshots (
                    snapshot_date, topic_name, code, name, market, yfinance_symbol, official_industry,
                    source, confidence, change_pct, volume, turnover_value, updated_at
                ) VALUES (
                    :snapshot_date, :topic_name, :code, :name, :market, :yfinance_symbol, :official_industry,
                    :source, :confidence, :change_pct, :volume, :turnover_value, :updated_at
                )
                """,
                component_records_df[
                    [
                        "snapshot_date",
                        "topic_name",
                        "code",
                        "name",
                        "market",
                        "yfinance_symbol",
                        "official_industry",
                        "source",
                        "confidence",
                        "change_pct",
                        "volume",
                        "turnover_value",
                        "updated_at",
                    ]
                ].to_dict(orient="records"),
            )

        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('latest_snapshot_trade_date', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (used_date,),
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('latest_snapshot_updated_at', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (updated_at,),
        )
        conn.commit()
