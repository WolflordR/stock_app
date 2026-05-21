import pandas as pd
import streamlit as st

from modules.core.app_constants import HOMEPAGE_RANGE_SCAN_DELAY_SEC
from modules.backtest.backtest_models import HomepageRangeScanRequest
from modules.backtest.backtest_service import run_homepage_range_scan
from modules.data_sources.chip_data import build_consecutive_institutional_rankings
from modules.industry.company_links_db import get_company_profiles_df
from modules.data_sources.price_cache import fetch_price_history
from modules.core.trading_calendar import resolve_recent_trade_date, resolve_trade_dates_in_range

TECH_INDUSTRY_NAMES = {
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


@st.cache_data(ttl=1800, show_spinner=False)
def load_company_theme_lookup():
    profiles_df = get_company_profiles_df()
    if profiles_df.empty:
        return {}

    lookup = {}
    for row in profiles_df.to_dict(orient="records"):
        code = str(row.get("code") or "").zfill(4)
        themes = [str(theme).strip() for theme in (row.get("themes") or []) if str(theme).strip()]
        lookup[code] = "｜".join(themes) if themes else "未分類"
    return lookup


@st.cache_data(ttl=1800, show_spinner=False)
def load_company_official_industry_lookup():
    profiles_df = get_company_profiles_df()
    if profiles_df.empty:
        return {}

    lookup = {}
    for row in profiles_df.to_dict(orient="records"):
        code = str(row.get("code") or "").zfill(4)
        industry = str(row.get("industry") or "").strip() or "未分類"
        lookup[code] = industry
    return lookup


def attach_theme_column(source_df, code_column="代碼", insert_after="名稱", theme_column="細分產業"):
    if source_df is None or source_df.empty or code_column not in source_df.columns:
        return source_df

    theme_lookup = load_company_theme_lookup()
    result_df = source_df.copy()
    result_df[theme_column] = (
        result_df[code_column]
        .astype(str)
        .str.extract(r"(\d{4})", expand=False)
        .fillna("")
        .str.zfill(4)
        .map(theme_lookup)
        .fillna("未分類")
    )

    columns = result_df.columns.tolist()
    columns.remove(theme_column)
    if insert_after in columns:
        columns.insert(columns.index(insert_after) + 1, theme_column)
        result_df = result_df[columns]
    return result_df


def attach_official_industry_column(source_df, code_column="代碼", insert_after="細分產業", industry_column="官方產業"):
    if source_df is None or source_df.empty or code_column not in source_df.columns:
        return source_df

    industry_lookup = load_company_official_industry_lookup()
    result_df = source_df.copy()
    result_df[industry_column] = (
        result_df[code_column]
        .astype(str)
        .str.extract(r"(\d{4})", expand=False)
        .fillna("")
        .str.zfill(4)
        .map(industry_lookup)
        .fillna("未分類")
    )

    columns = result_df.columns.tolist()
    columns.remove(industry_column)
    if insert_after in columns:
        columns.insert(columns.index(insert_after) + 1, industry_column)
        result_df = result_df[columns]
    return result_df


def build_research_institutional_signals_payload(trade_date):
    return {
        "trust_3d": build_consecutive_institutional_rankings(trade_date, "投信", consecutive_days=3, top_n=30),
        "trust_5d": build_consecutive_institutional_rankings(trade_date, "投信", consecutive_days=5, top_n=30),
        "foreign_3d": build_consecutive_institutional_rankings(trade_date, "外資", consecutive_days=3, top_n=30),
    }


def run_research_candidate_scan(state, trade_date):
    request_state = dict(state)
    request_state["home_trade_date"] = trade_date
    request = HomepageRangeScanRequest.from_sidebar_state(request_state)
    return run_homepage_range_scan(
        request,
        request_delay_sec=HOMEPAGE_RANGE_SCAN_DELAY_SEC,
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_candidate_structure_snapshot(trade_date, candidate_items):
    rows = []
    for code, info in candidate_items:
        df = fetch_price_history(
            code,
            "即時選股",
            None,
            trade_date,
            history_buffer_days=240,
        )
        if df.empty or len(df) < 140:
            rows.append(
                {
                    "code": code,
                    "ma60": None,
                    "ma120": None,
                    "ma_gap_pct": None,
                    "price_to_ma60_pct": None,
                    "price_to_ma120_pct": None,
                    "squeeze_label": "資料不足",
                }
            )
            continue

        close_series = df["Close"].sort_index()
        ma60 = close_series.rolling(60).mean().iloc[-1]
        ma120 = close_series.rolling(120).mean().iloc[-1]
        close_price = close_series.iloc[-1]
        if pd.isna(ma60) or pd.isna(ma120) or ma120 == 0:
            rows.append(
                {
                    "code": code,
                    "ma60": None,
                    "ma120": None,
                    "ma_gap_pct": None,
                    "price_to_ma60_pct": None,
                    "price_to_ma120_pct": None,
                    "squeeze_label": "資料不足",
                }
            )
            continue

        ma_gap_pct = abs(ma60 - ma120) / ma120 * 100
        price_to_ma60_pct = (close_price / ma60 - 1) * 100
        price_to_ma120_pct = (close_price / ma120 - 1) * 100
        if ma_gap_pct <= 6 and abs(price_to_ma60_pct) <= 8 and abs(price_to_ma120_pct) <= 10:
            squeeze_label = "均線糾結"
        elif ma_gap_pct <= 10 and abs(price_to_ma60_pct) <= 12:
            squeeze_label = "接近糾結"
        else:
            squeeze_label = "已偏離均線"

        rows.append(
            {
                "code": code,
                "ma60": round(float(ma60), 2),
                "ma120": round(float(ma120), 2),
                "ma_gap_pct": round(float(ma_gap_pct), 2),
                "price_to_ma60_pct": round(float(price_to_ma60_pct), 2),
                "price_to_ma120_pct": round(float(price_to_ma120_pct), 2),
                "squeeze_label": squeeze_label,
            }
        )

    return pd.DataFrame(rows)


def build_research_candidate_display_df(candidate_results, trade_date, trust_3d_result, top_n=20):
    if not candidate_results:
        return pd.DataFrame()

    sorted_items = sorted(
        candidate_results.items(),
        key=lambda item: (
            item[1].get("bowl_score") is not None,
            item[1].get("bowl_score") or 0,
            item[1].get("current_volume_ratio") or 0,
        ),
        reverse=True,
    )
    top_items = sorted_items[:top_n]
    structure_df = load_candidate_structure_snapshot(
        trade_date,
        tuple((code, info.get("price")) for code, info in top_items),
    )
    structure_map = structure_df.set_index("code").to_dict("index") if not structure_df.empty else {}

    trust_map = {}
    if trust_3d_result and not trust_3d_result["buy_rank_df"].empty:
        buy_df = trust_3d_result["buy_rank_df"].copy()
        latest_share_column = next((column for column in buy_df.columns if column.endswith("累計股數(張)")), None)
        if latest_share_column:
            trust_map = buy_df.set_index("代碼")[latest_share_column].to_dict()

    rows = []
    for code, info in top_items:
        plain_code = code.split(".")[0]
        structure = structure_map.get(code, {})
        positive_reasons = info.get("positive_reasons") or []
        caution_reasons = info.get("caution_reasons") or []
        rows.append(
            {
                "代碼": code,
                "名稱": info["name"],
                "級別": info.get("bowl_grade") or "-",
                "盤整吸籌分數": info.get("bowl_score"),
                "成交張數": round((info.get("latest_volume") or 0) / 1000, 1) if info.get("latest_volume") is not None else "-",
                "近3日均張數": round((info.get("avg_volume_3") or 0) / 1000, 1) if info.get("avg_volume_3") is not None else "-",
                "前3日均張數": round((info.get("avg_volume_prev3") or 0) / 1000, 1) if info.get("avg_volume_prev3") is not None else "-",
                "20日均張數": round((info.get("avg_volume_20") or 0) / 1000, 1) if info.get("avg_volume_20") is not None else "-",
                "當日量增倍數": f"{info['current_volume_ratio']:.2f}x" if info.get("current_volume_ratio") is not None else "-",
                "近3日量增倍數": f"{info['recent3_volume_ratio']:.2f}x" if info.get("recent3_volume_ratio") is not None else "-",
                "區間內位置(%)": f"{info['range_position_pct']:.1f}%" if info.get("range_position_pct") is not None else "-",
                "突破區間(%)": f"{info['breakout_pct']:.2f}%" if info.get("breakout_pct") is not None else "-",
                "60/120MA": structure.get("squeeze_label", "資料不足"),
                "60/120MA距離(%)": f"{structure['ma_gap_pct']:.2f}%" if structure.get("ma_gap_pct") is not None else "-",
                "投信連3日": "是" if plain_code in trust_map else "-",
                "投信3日累計(張)": trust_map.get(plain_code, "-"),
                "入選原因": "；".join(positive_reasons[:3]) if positive_reasons else "-",
                "觀察點": "；".join(caution_reasons[:2]) if caution_reasons else "-",
            }
        )

    return pd.DataFrame(rows)


def summarize_candidate_dashboard(candidate_df):
    if candidate_df is None or candidate_df.empty:
        return {
            "grade_counts": {"A": 0, "B": 0, "C": 0},
            "top_theme": "-",
            "trust_overlap": 0,
            "avg_volume_ratio": None,
        }

    grade_counts = {
        grade: int((candidate_df["級別"] == grade).sum())
        for grade in ["A", "B", "C"]
    }
    theme_series = candidate_df.get("細分產業")
    top_theme = "-"
    if theme_series is not None:
        non_empty = theme_series[theme_series.astype(str).str.strip().ne("")]
        if not non_empty.empty:
            top_theme = non_empty.value_counts().index[0]

    trust_overlap = int((candidate_df.get("投信連3日") == "是").sum()) if "投信連3日" in candidate_df.columns else 0
    avg_volume_ratio = None
    if "當日量增倍數" in candidate_df.columns:
        numeric_series = (
            candidate_df["當日量增倍數"]
            .astype(str)
            .str.replace("x", "", regex=False)
            .replace("-", pd.NA)
        )
        numeric_series = pd.to_numeric(numeric_series, errors="coerce")
        if numeric_series.notna().any():
            avg_volume_ratio = float(numeric_series.mean())

    return {
        "grade_counts": grade_counts,
        "top_theme": top_theme,
        "trust_overlap": trust_overlap,
        "avg_volume_ratio": avg_volume_ratio,
    }


def build_candidate_history_payload(
    state,
    start_date,
    end_date,
    min_group_size=2,
    top_n_per_day=20,
    progress_callback=None,
    status_callback=None,
):
    resolved_dates = resolve_trade_dates_in_range(start_date, end_date)
    daily_group_rows = []
    daily_candidate_rows = []
    total_dates = len(resolved_dates)

    if status_callback:
        if total_dates:
            status_callback(f"準備回放 {total_dates} 個交易日")
        else:
            status_callback("指定區間內沒有可回放的交易日")

    for index, resolution in enumerate(resolved_dates, start=1):
        if progress_callback and total_dates:
            progress_callback(
                min(0.15 + 0.65 * (index - 1) / total_dates, 0.8),
                f"回放第 {index}/{total_dates} 個交易日：{resolution['effective_date_text']}",
            )
        effective_trade_date = resolution["effective_date"]
        candidate_results = run_research_candidate_scan(state, effective_trade_date)
        candidate_df = build_research_candidate_display_df(
            candidate_results or {},
            effective_trade_date,
            trust_3d_result=None,
            top_n=top_n_per_day,
        )
        candidate_df = attach_theme_column(candidate_df)
        candidate_df = attach_official_industry_column(candidate_df)
        if candidate_df is None or candidate_df.empty:
            continue

        candidate_df["觀察日期"] = resolution["effective_date_text"]

        industry_group_df = (
            candidate_df.groupby("官方產業", dropna=False)
            .agg(
                入選檔數=("代碼", "count"),
                平均分數=("盤整吸籌分數", "mean"),
                股票名單=("名稱", lambda values: "、".join(list(values)[:8])),
                細分主題=("細分產業", lambda values: "、".join(pd.Series(values).fillna("未分類").astype(str).unique()[:6])),
            )
            .reset_index()
        )
        industry_group_df = industry_group_df[industry_group_df["入選檔數"] >= int(min_group_size)].copy()
        if industry_group_df.empty:
            continue

        industry_group_df["觀察日期"] = resolution["effective_date_text"]
        industry_group_df["平均分數"] = pd.to_numeric(industry_group_df["平均分數"], errors="coerce").round(1)
        daily_group_rows.append(industry_group_df)

        matched_industries = set(industry_group_df["官方產業"].astype(str))
        matched_candidates_df = candidate_df[candidate_df["官方產業"].astype(str).isin(matched_industries)].copy()
        daily_candidate_rows.append(matched_candidates_df)

    if progress_callback:
        progress_callback(0.88, "正在整理回放結果")

    grouped_days_df = pd.concat(daily_group_rows, ignore_index=True) if daily_group_rows else pd.DataFrame()
    candidate_history_df = pd.concat(daily_candidate_rows, ignore_index=True) if daily_candidate_rows else pd.DataFrame()

    if not grouped_days_df.empty:
        grouped_days_df = grouped_days_df.sort_values(
            ["觀察日期", "入選檔數", "平均分數", "官方產業"],
            ascending=[True, False, False, True],
        ).reset_index(drop=True)

    if not candidate_history_df.empty:
        candidate_history_df = candidate_history_df.sort_values(
            ["觀察日期", "官方產業", "盤整吸籌分數"],
            ascending=[True, True, False],
        ).reset_index(drop=True)

    backtest_exit_resolution = resolve_recent_trade_date(pd.Timestamp.today().date())
    backtest_exit_date = backtest_exit_resolution["effective_date"]
    backtest_exit_date_text = backtest_exit_resolution["effective_date_text"]
    if progress_callback:
        progress_callback(0.92, f"正在計算回測損益，出場上限日：{backtest_exit_date_text}")
    backtest_detail_df, backtest_group_df = build_candidate_history_backtest_frames(
        candidate_history_df,
        backtest_exit_date,
    )

    return {
        "resolved_dates": resolved_dates,
        "grouped_days_df": grouped_days_df,
        "candidate_history_df": candidate_history_df,
        "backtest_exit_date_text": backtest_exit_date_text,
        "backtest_detail_df": backtest_detail_df,
        "backtest_group_df": backtest_group_df,
        "backtest_sample_count": int(len(backtest_detail_df)),
        "backtest_group_count": int(len(backtest_group_df)),
        "backtest_avg_peak_gain_pct": (
            round(float(backtest_detail_df["最高點損益(%)"].mean()), 2)
            if not backtest_detail_df.empty else None
        ),
        "backtest_median_peak_gain_pct": (
            round(float(backtest_detail_df["最高點損益(%)"].median()), 2)
            if not backtest_detail_df.empty else None
        ),
        "matched_day_count": int(grouped_days_df["觀察日期"].nunique()) if not grouped_days_df.empty else 0,
        "matched_group_count": int(len(grouped_days_df)),
        "matched_stock_count": int(len(candidate_history_df)),
    }


def build_candidate_history_backtest_frames(candidate_history_df, exit_trade_date):
    if candidate_history_df is None or candidate_history_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    exit_ts = pd.to_datetime(exit_trade_date).normalize()
    detail_rows = []

    for row in candidate_history_df.to_dict(orient="records"):
        symbol = str(row.get("代碼") or "").strip()
        observe_date_text = str(row.get("觀察日期") or "").strip()
        if not symbol or not observe_date_text:
            continue

        observe_ts = pd.to_datetime(observe_date_text).normalize()
        if observe_ts >= exit_ts:
            continue

        history_df = fetch_price_history(
            symbol,
            mode="歷史回測",
            start_date=observe_ts.date(),
            end_date=exit_ts.date(),
            history_buffer_days=10,
        )
        if history_df.empty:
            continue

        trade_window_df = history_df[history_df.index > observe_ts].copy()
        if trade_window_df.empty:
            continue

        trade_window_df = trade_window_df.sort_index()
        buy_date = trade_window_df.index[0]
        buy_open = pd.to_numeric(trade_window_df.iloc[0]["Open"], errors="coerce")
        if pd.isna(buy_open) or float(buy_open) <= 0:
            continue

        high_series = pd.to_numeric(trade_window_df["High"], errors="coerce").dropna()
        if high_series.empty:
            continue

        peak_exit_price = float(high_series.max())
        peak_exit_date = pd.to_datetime(high_series.idxmax()).strftime("%Y-%m-%d")
        peak_gain_pct = (peak_exit_price / float(buy_open) - 1) * 100

        detail_rows.append(
            {
                "觀察日期": observe_date_text,
                "官方產業": row.get("官方產業", "未分類"),
                "細分產業": row.get("細分產業", "未分類"),
                "代碼": symbol,
                "名稱": row.get("名稱", "-"),
                "級別": row.get("級別", "-"),
                "盤整吸籌分數": row.get("盤整吸籌分數"),
                "買進日": buy_date.strftime("%Y-%m-%d"),
                "買進價(隔日開盤)": round(float(buy_open), 2),
                "最高點日": peak_exit_date,
                "最高點出場價": round(float(peak_exit_price), 2),
                "最高點損益(%)": round(float(peak_gain_pct), 2),
                "入選原因": row.get("入選原因", "-"),
                "觀察點": row.get("觀察點", "-"),
            }
        )

    detail_df = pd.DataFrame(detail_rows)
    if detail_df.empty:
        return detail_df, pd.DataFrame()

    detail_df = detail_df.sort_values(
        ["觀察日期", "官方產業", "最高點損益(%)"],
        ascending=[True, True, False],
    ).reset_index(drop=True)

    group_df = (
        detail_df.groupby(["觀察日期", "官方產業"], dropna=False)
        .agg(
            入選檔數=("代碼", "count"),
            平均最高點損益=("最高點損益(%)", "mean"),
            中位數最高點損益=("最高點損益(%)", "median"),
            最大最高點損益=("最高點損益(%)", "max"),
            股票名單=("名稱", lambda values: "、".join(list(values)[:8])),
        )
        .reset_index()
    )
    for column in ["平均最高點損益", "中位數最高點損益", "最大最高點損益"]:
        group_df[column] = pd.to_numeric(group_df[column], errors="coerce").round(2)
    group_df = group_df.sort_values(
        ["觀察日期", "平均最高點損益", "入選檔數"],
        ascending=[True, False, False],
    ).reset_index(drop=True)

    return detail_df, group_df
