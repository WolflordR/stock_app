import altair as alt
import pandas as pd


def render_summary_metric_card(label, value):
    import streamlit as st

    st.markdown(
        f"""
        <div class="industry-summary-card">
            <div class="industry-summary-label">{label}</div>
            <div class="industry-summary-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_rotation_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.2f}%"


def format_rotation_lots(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value / 1000:,.1f} 張"


def format_rotation_billions(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value / 100000000:,.2f} 億"


def format_rotation_ratio(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.2f}x"


def safe_numeric(value, default=0.0):
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except Exception:
        return default


def format_rotation_score_delta(value):
    if value is None or pd.isna(value):
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}"


def add_member_weighted_sort_columns(summary_df):
    if summary_df.empty:
        return summary_df

    weighted_df = summary_df.copy()
    stock_counts = pd.to_numeric(weighted_df["stock_count"], errors="coerce").fillna(0.0)
    member_weight = 0.4 + 0.6 * stock_counts.clip(lower=0, upper=8) / 8.0
    weighted_df["member_weight"] = member_weight
    weighted_df["weighted_rotation_score"] = weighted_df["rotation_score"].fillna(0.0) * member_weight
    weighted_df["weighted_volume_ratio"] = weighted_df["volume_ratio"].fillna(0.0) * member_weight
    weighted_df["weighted_turnover_ratio"] = weighted_df["turnover_ratio"].fillna(0.0) * member_weight
    weighted_df["weighted_latest_change_pct"] = weighted_df["latest_change_pct"].fillna(0.0) * member_weight
    weighted_df["weighted_five_day_change_pct"] = weighted_df["five_day_change_pct"].fillna(0.0) * member_weight
    weighted_df["weighted_score_delta_1d"] = weighted_df["score_delta_1d"].fillna(0.0) * member_weight
    weighted_df["weighted_score_delta_3d"] = weighted_df["score_delta_3d"].fillna(0.0) * member_weight
    return weighted_df


def build_display_name(item_type, item_name):
    prefix = "細分" if item_type == "細分主題" else "官方"
    return f"{prefix}｜{item_name}"


def build_combined_rotation_summary_df(theme_summary_df, industry_summary_df):
    frames = []

    if not theme_summary_df.empty:
        theme_df = theme_summary_df.copy()
        theme_df["類型"] = "細分主題"
        theme_df["項目"] = theme_df["group_name"]
        frames.append(theme_df)

    if not industry_summary_df.empty:
        industry_df = industry_summary_df.copy()
        industry_df["類型"] = "官方產業"
        industry_df["項目"] = industry_df["group_name"]
        frames.append(industry_df)

    if not frames:
        return pd.DataFrame()

    combined_df = add_member_weighted_sort_columns(pd.concat(frames, ignore_index=True))
    combined_df = combined_df.sort_values(
        ["weighted_rotation_score", "latest_turnover", "stock_count", "latest_change_pct"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    return combined_df


def build_combined_rotation_display_df(theme_summary_df, industry_summary_df):
    combined_df = build_combined_rotation_summary_df(theme_summary_df, industry_summary_df)
    if combined_df.empty:
        return pd.DataFrame()

    display_df = combined_df.copy()
    display_df["報價"] = display_df["latest_index"].map(lambda value: f"{value:,.2f}" if pd.notna(value) else "-")
    display_df["單日(%)"] = display_df["latest_change_pct"].map(format_rotation_pct)
    display_df["5日(%)"] = display_df["five_day_change_pct"].map(format_rotation_pct)
    display_df["當日成交量"] = display_df["latest_volume"].map(format_rotation_lots)
    display_df["5日均量"] = display_df["avg_volume_5d"].map(format_rotation_lots)
    display_df["量比"] = display_df["volume_ratio"].map(format_rotation_ratio)
    display_df["當日成交值"] = display_df["latest_turnover"].map(format_rotation_billions)
    display_df["5日均成交值"] = display_df["avg_turnover_5d"].map(format_rotation_billions)
    display_df["成交值比"] = display_df["turnover_ratio"].map(format_rotation_ratio)
    display_df["上漲家數"] = display_df.apply(
        lambda row: f"{int(row['positive_count'])}/{int(row['stock_count'])}",
        axis=1,
    )
    display_df["輪動分數"] = display_df["rotation_score"].map(lambda value: f"{value:.1f}" if pd.notna(value) else "-")
    display_df["分數1日變化"] = display_df["score_delta_1d"].map(format_rotation_score_delta)
    display_df["分數3日變化"] = display_df["score_delta_3d"].map(format_rotation_score_delta)
    return display_df[
        [
            "類型",
            "項目",
            "parent_industry",
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
            "limit_up_count",
            "locked_up_count",
            "representative_stocks",
            "輪動分數",
            "分數1日變化",
            "分數3日變化",
        ]
    ].rename(
        columns={
            "parent_industry": "官方母產業",
            "limit_up_count": "漲停家數",
            "locked_up_count": "鎖漲停家數",
            "representative_stocks": "代表股",
        }
    )


def build_combined_rotation_series_df(theme_series_df, industry_series_df):
    frames = []

    if not theme_series_df.empty:
        theme_df = theme_series_df.copy()
        theme_df["類型"] = "細分主題"
        theme_df["項目"] = theme_df["group_name"]
        theme_df["顯示名稱"] = theme_df["項目"].map(lambda value: f"細分｜{value}")
        frames.append(theme_df)

    if not industry_series_df.empty:
        industry_df = industry_series_df.copy()
        industry_df["類型"] = "官方產業"
        industry_df["項目"] = industry_df["group_name"]
        industry_df["顯示名稱"] = industry_df["項目"].map(lambda value: f"官方｜{value}")
        frames.append(industry_df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def build_market_tone_summary(combined_summary_df):
    if combined_summary_df.empty:
        return {
            "title": "資料不足",
            "summary": "目前還沒有足夠的輪動資料可以定調。",
            "signals": [],
        }

    top_row = combined_summary_df.iloc[0]
    top_slice = combined_summary_df.head(min(5, len(combined_summary_df))).copy()
    avg_volume_ratio = float(top_slice["volume_ratio"].dropna().mean()) if top_slice["volume_ratio"].notna().any() else 0.0
    avg_turnover_ratio = float(top_slice["turnover_ratio"].dropna().mean()) if top_slice["turnover_ratio"].notna().any() else 0.0
    top_change = safe_numeric(top_row.get("latest_change_pct"))

    if top_change >= 1.5 and avg_volume_ratio >= 1.2:
        title = "題材擴散盤"
    elif top_change >= 1.0 and avg_turnover_ratio >= 1.15:
        title = "資金進攻盤"
    elif top_change <= -0.8 and avg_volume_ratio < 1.0:
        title = "防守觀望盤"
    else:
        title = "輪動測試盤"

    flow_row = combined_summary_df.sort_values(["turnover_ratio", "latest_turnover"], ascending=[False, False]).iloc[0]
    breadth_row = combined_summary_df.sort_values(["latest_change_pct", "rotation_score"], ascending=[False, False]).iloc[0]
    weak_row = combined_summary_df.sort_values(["five_day_change_pct", "latest_change_pct"], ascending=[True, True]).iloc[0]
    score_up_row = combined_summary_df.sort_values(["score_delta_1d", "score_delta_3d"], ascending=[False, False]).iloc[0]

    summary = (
        f"今天主攻在 {top_row['項目']}，"
        f"主流題材輪動還在延續；"
        f"若要看資金是否繼續集中，先盯 {flow_row['項目']} 的成交值比、{breadth_row['項目']} 的價格延續，"
        f"以及 {score_up_row['項目']} 的輪動分數是否續增。"
    )
    signals = [
        f"主攻焦點：{top_row['項目']}｜單日 {safe_numeric(top_row.get('latest_change_pct')):.2f}%｜量比 {safe_numeric(top_row.get('volume_ratio')):.2f}x",
        f"資金最積極：{flow_row['項目']}｜成交值比 {safe_numeric(flow_row.get('turnover_ratio')):.2f}x",
        f"分數加速：{score_up_row['項目']}｜1日變化 {safe_numeric(score_up_row.get('score_delta_1d')):+.1f}",
        f"相對轉弱：{weak_row['項目']}｜5日 {safe_numeric(weak_row.get('five_day_change_pct')):.2f}%",
    ]
    return {
        "title": title,
        "summary": summary,
        "signals": signals,
    }


def build_theme_rank_bar_chart(summary_df, value_column, value_title):
    if summary_df.empty:
        return None

    chart_df = summary_df[["項目", value_column]].dropna().copy()
    if chart_df.empty:
        return None

    chart_df = chart_df.sort_values(value_column, ascending=False).copy()
    chart_df["顏色"] = chart_df[value_column].apply(lambda value: "#b91c1c" if value >= 0 else "#1d4ed8")
    return alt.Chart(chart_df).mark_bar(cornerRadiusEnd=5).encode(
        y=alt.Y("項目:N", sort="-x", title=None),
        x=alt.X(f"{value_column}:Q", title=value_title),
        color=alt.Color("顏色:N", scale=None, legend=None),
        tooltip=[
            alt.Tooltip("項目:N", title="主題"),
            alt.Tooltip(f"{value_column}:Q", title=value_title, format=".2f"),
        ],
    ).properties(height=max(280, len(chart_df) * 28))


def classify_rotation_stage(row):
    five_day_change_pct = float(row.get("five_day_change_pct") or 0.0)
    volume_ratio = float(row.get("volume_ratio") or 0.0)
    turnover_ratio = float(row.get("turnover_ratio") or 0.0)
    score_delta_1d = float(row.get("score_delta_1d") or 0.0)

    if five_day_change_pct >= 6.0 and volume_ratio >= 1.3 and turnover_ratio >= 1.2:
        return "趨勢攻擊"
    if volume_ratio >= 1.25 and turnover_ratio >= 1.1 and five_day_change_pct >= -2.0:
        return "量先價後"
    if five_day_change_pct >= 6.0 and volume_ratio < 1.25:
        return "高檔整理"
    if volume_ratio >= 1.2 and five_day_change_pct < 0:
        return "弱勢反彈"
    if score_delta_1d >= 8.0:
        return "分數升溫"
    return "盤整觀察"


def build_rotation_stage_display_df(summary_df, top_n=10):
    if summary_df.empty:
        return pd.DataFrame()

    stage_df = summary_df.copy().head(top_n)
    stage_df["資金節奏"] = stage_df.apply(classify_rotation_stage, axis=1)
    stage_df["5日(%)"] = stage_df["five_day_change_pct"].map(format_rotation_pct)
    stage_df["量比"] = stage_df["volume_ratio"].map(format_rotation_ratio)
    stage_df["成交值比"] = stage_df["turnover_ratio"].map(format_rotation_ratio)
    stage_df["輪動分數"] = stage_df["rotation_score"].map(lambda value: f"{value:.1f}" if pd.notna(value) else "-")
    stage_df["分數1日變化"] = stage_df["score_delta_1d"].map(format_rotation_score_delta)
    stage_df["代表股"] = stage_df["representative_stocks"].fillna("-")
    return stage_df[["項目", "資金節奏", "5日(%)", "量比", "成交值比", "輪動分數", "分數1日變化", "代表股"]]
