import altair as alt
import pandas as pd
import streamlit as st

from modules.industry.industry_rotation import build_theme_member_display_df
from modules.industry.industry_taxonomy import (
    SECTOR_GROUP_ORDER,
    TIDE_REFERENCE_SECTOR_GROUPS,
)
from modules.industry.industry_page_helpers import (
    build_combined_rotation_display_df,
    build_rotation_stage_display_df,
    build_theme_rank_bar_chart,
)


FUND_STATUS_COLORS = {
    "漲潮": "#DF6F7B",
    "輪動": "#D3A64F",
    "觀望": "#7D8FA3",
    "退潮": "#63C796",
}


def _format_yi(value):
    if value is None or pd.isna(value):
        return "-"
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{float(value):,.1f}"


def build_sector_fund_bubble_chart(raw_df):
    if raw_df.empty:
        return None

    chart_df = raw_df.copy()
    chart_df["label"] = chart_df["group_name"].astype(str)
    chart_df["net_20d_abs"] = chart_df["net_20d_yi"].abs().clip(lower=1.0)

    base = alt.Chart(chart_df).encode(
        x=alt.X(
            "net_5d_yi:Q",
            title="近 5 日法人淨買超估算(億)",
            scale=alt.Scale(type="symlog"),
            axis=alt.Axis(grid=True),
        ),
        y=alt.Y(
            "accel_yi:Q",
            title="資金加速度：5日均速 - 20日均速(億/日)",
            scale=alt.Scale(type="symlog"),
            axis=alt.Axis(grid=True),
        ),
    )

    bubbles = base.mark_circle(opacity=0.84, stroke="#101A26", strokeWidth=0.8).encode(
        size=alt.Size(
            "net_20d_abs:Q",
            title="20日累計資金",
            scale=alt.Scale(range=[90, 1900]),
        ),
        color=alt.Color(
            "fund_status:N",
            title="狀態",
            scale=alt.Scale(
                domain=list(FUND_STATUS_COLORS.keys()),
                range=list(FUND_STATUS_COLORS.values()),
            ),
        ),
        tooltip=[
            alt.Tooltip("group_name:N", title="細分產業"),
            alt.Tooltip("fund_status:N", title="狀態"),
            alt.Tooltip("net_1d_yi:Q", title="今日淨買超(億)", format="+.1f"),
            alt.Tooltip("net_5d_yi:Q", title="5日淨買超(億)", format="+.1f"),
            alt.Tooltip("net_20d_yi:Q", title="20日累計(億)", format="+.1f"),
            alt.Tooltip("accel_yi:Q", title="資金加速度", format="+.1f"),
            alt.Tooltip("five_day_change_pct:Q", title="5日漲跌", format="+.2f"),
            alt.Tooltip("covered_stock_count:Q", title="法人涵蓋成分股"),
        ],
    )

    labels = base.mark_text(
        align="center",
        baseline="middle",
        dy=-16,
        fontSize=11,
        color="#9FB2C5",
    ).encode(text=alt.Text("label:N"))

    x_rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="rgba(143,163,184,0.42)", strokeDash=[5, 5]).encode(x="x:Q")
    y_rule = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="rgba(143,163,184,0.42)", strokeDash=[5, 5]).encode(y="y:Q")
    return (bubbles + labels + x_rule + y_rule).properties(height=470)


def render_sector_fund_flow_tab(fund_flow_report):
    st.write("**板塊資金潮汐**")
    source_label = (fund_flow_report or {}).get("source") or "本地法人估算"
    st.caption(f"功能對齊 Tide 的核心視角：泡泡圖看資金流向與加速度，排行榜看買超、賣超與量價落差。資金資料來源：{source_label}。")

    if not fund_flow_report or fund_flow_report.get("raw_df") is None or fund_flow_report["raw_df"].empty:
        st.caption("目前沒有足夠的法人資金資料可顯示潮汐圖。")
        return

    raw_df = fund_flow_report["raw_df"].copy()
    display_df = fund_flow_report["display_df"].copy()
    stock_flow_df = fund_flow_report.get("stock_flow_df", pd.DataFrame()).copy()

    metric_cols = st.columns(6)
    metric_cols[0].metric("法人資料日", fund_flow_report.get("used_date") or "-")
    metric_cols[1].metric("統計交易日", fund_flow_report.get("history_trade_days") or 0)
    for index, status in enumerate(["漲潮", "輪動", "觀望", "退潮"], start=2):
        metric_cols[index].metric(status, int((raw_df["fund_status"] == status).sum()))

    filter_cols = st.columns([0.85, 0.85, 1.4])
    status_filter = filter_cols[0].selectbox(
        "狀態",
        ["全部", "漲潮", "輪動", "觀望", "退潮"],
        index=0,
        key="industry_fund_flow_status",
    )
    ranking_mode = filter_cols[1].selectbox(
        "排行榜",
        ["5日買超", "5日賣超", "20日累計", "低漲高買"],
        index=0,
        key="industry_fund_flow_ranking_mode",
    )
    keyword = filter_cols[2].text_input(
        "搜尋板塊 / 代表股",
        value="",
        key="industry_fund_flow_keyword",
        placeholder="例如：CPO、記憶體、散熱、台積電",
    ).strip()

    filtered_df = raw_df.copy()
    if status_filter != "全部":
        filtered_df = filtered_df[filtered_df["fund_status"] == status_filter].copy()
    if keyword:
        mask = (
            filtered_df["group_name"].astype(str).str.contains(keyword, case=False, na=False)
            | filtered_df["representative_stocks"].astype(str).str.contains(keyword, case=False, na=False)
            | filtered_df["parent_industry"].astype(str).str.contains(keyword, case=False, na=False)
        )
        filtered_df = filtered_df[mask].copy()

    left_col, right_col = st.columns([1.45, 0.9])
    with left_col:
        st.write("**泡泡圖**")
        st.caption("右上是資金加速流入；右下是仍流入但放緩；左側代表法人資金流出。")
        chart = build_sector_fund_bubble_chart(filtered_df)
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("目前沒有符合條件的泡泡圖資料。")

    with right_col:
        st.write("**排行榜**")
        if ranking_mode == "5日買超":
            ranking_df = filtered_df.sort_values(["net_5d_yi", "accel_yi"], ascending=[False, False]).head(20)
        elif ranking_mode == "5日賣超":
            ranking_df = filtered_df.sort_values(["net_5d_yi", "accel_yi"], ascending=[True, True]).head(20)
        elif ranking_mode == "20日累計":
            ranking_df = filtered_df.sort_values(["net_20d_yi", "net_5d_yi"], ascending=[False, False]).head(20)
        else:
            ranking_df = filtered_df[filtered_df["net_5d_yi"] > 0].copy()
            ranking_df["low_chg_buy_score"] = ranking_df["net_5d_yi"] - ranking_df["five_day_change_pct"].fillna(0) * 4
            ranking_df = ranking_df.sort_values(["low_chg_buy_score", "net_5d_yi"], ascending=[False, False]).head(20)

        ranking_display_df = ranking_df.copy()
        ranking_display_df["狀態"] = ranking_display_df["fund_status"]
        ranking_display_df["板塊"] = ranking_display_df["group_name"]
        ranking_display_df["5日資金"] = ranking_display_df["net_5d_yi"].map(_format_yi)
        ranking_display_df["今日資金"] = ranking_display_df["net_1d_yi"].map(_format_yi)
        ranking_display_df["5日漲跌"] = ranking_display_df["five_day_change_pct"].map(lambda value: f"{value:.2f}%" if pd.notna(value) else "-")
        st.dataframe(
            ranking_display_df[["狀態", "板塊", "5日資金", "今日資金", "5日漲跌"]],
            use_container_width=True,
            hide_index=True,
            height=470,
        )

    st.write("**板塊明細**")
    sector_options = filtered_df["group_name"].tolist()
    if not sector_options:
        st.caption("目前沒有符合篩選條件的板塊。")
        return

    selected_sector = st.selectbox(
        "查看板塊成分股",
        sector_options,
        index=0,
        key="industry_fund_flow_selected_sector",
    )
    selected_row = raw_df[raw_df["group_name"] == selected_sector].iloc[0]
    detail_cols = st.columns(5)
    detail_cols[0].metric("狀態", selected_row["fund_status"])
    detail_cols[1].metric("今日資金(億)", _format_yi(selected_row["net_1d_yi"]))
    detail_cols[2].metric("5日資金(億)", _format_yi(selected_row["net_5d_yi"]))
    detail_cols[3].metric("20日累計(億)", _format_yi(selected_row["net_20d_yi"]))
    detail_cols[4].metric("加速度", _format_yi(selected_row["accel_yi"]))

    sector_display = display_df[display_df["細分產業"] == selected_sector]
    if not sector_display.empty:
        st.dataframe(sector_display, use_container_width=True, hide_index=True)

    if not stock_flow_df.empty:
        sector_stock_df = stock_flow_df[stock_flow_df["group_name"] == selected_sector].copy()
        if not sector_stock_df.empty:
            sector_stock_df = sector_stock_df.sort_values("net_5d_yi", ascending=False).head(30)
            sector_stock_df["代碼"] = sector_stock_df["code"]
            sector_stock_df["名稱"] = sector_stock_df["name_zh"]
            sector_stock_df["收盤"] = sector_stock_df["close"].map(lambda value: f"{value:,.2f}" if pd.notna(value) else "-")
            sector_stock_df["今日資金(億)"] = sector_stock_df["net_1d_yi"].map(_format_yi)
            sector_stock_df["5日資金(億)"] = sector_stock_df["net_5d_yi"].map(_format_yi)
            sector_stock_df["20日累計(億)"] = sector_stock_df["net_20d_yi"].map(_format_yi)
            st.dataframe(
                sector_stock_df[["代碼", "名稱", "收盤", "今日資金(億)", "5日資金(億)", "20日累計(億)"]],
                use_container_width=True,
                hide_index=True,
                height=360,
            )


def build_sector_classification_display_df(theme_summary_df):
    if theme_summary_df.empty:
        return pd.DataFrame()

    display_df = theme_summary_df.copy()
    display_df["大分類"] = display_df["parent_industry"]
    display_df["細分產業"] = display_df["group_name"]
    display_df["成分股數"] = display_df["stock_count"].map(lambda value: int(value) if pd.notna(value) else 0)
    display_df["代表股"] = display_df["representative_stocks"].fillna("")
    display_df["單日漲跌"] = display_df["latest_change_pct"].map(lambda value: f"{value:.2f}%" if pd.notna(value) else "-")
    display_df["5日漲跌"] = display_df["five_day_change_pct"].map(lambda value: f"{value:.2f}%" if pd.notna(value) else "-")
    display_df["成交值比"] = display_df["turnover_ratio"].map(lambda value: f"{value:.2f}x" if pd.notna(value) else "-")
    display_df["_group_order"] = display_df["大分類"].map({name: idx for idx, name in enumerate(SECTOR_GROUP_ORDER)}).fillna(999)
    display_df = display_df.sort_values(
        ["_group_order", "成分股數", "latest_turnover", "細分產業"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    return display_df[
        [
            "大分類",
            "細分產業",
            "成分股數",
            "代表股",
            "單日漲跌",
            "5日漲跌",
            "成交值比",
        ]
    ]


def build_tide_reference_display_df(theme_summary_df):
    local_lookup = theme_summary_df.set_index("group_name") if not theme_summary_df.empty else pd.DataFrame()

    rows = []
    for group_name in SECTOR_GROUP_ORDER:
        for sector_name in TIDE_REFERENCE_SECTOR_GROUPS.get(group_name, []):
            has_sector = sector_name in local_lookup.index
            local_row = local_lookup.loc[sector_name] if has_sector else {}
            rows.append(
                {
                    "大分類": group_name,
                    "細分產業": sector_name,
                    "成分股數": int(local_row.get("stock_count", 0)) if has_sector else 0,
                    "代表股": local_row.get("representative_stocks", "") if has_sector else "",
                    "資料狀態": "已載入" if has_sector else "Tide無行情成分",
                }
            )
    return pd.DataFrame(rows)


def render_sector_classification_tab(theme_summary_df):
    st.write("**產業分類表**")
    st.caption("這裡直接使用 Tide 的 sector_groups.json 與 latest.json：大分類、細分產業、成分股來源都以 Tide 為準，不再用本系統舊主題做對應。")

    display_df = build_sector_classification_display_df(theme_summary_df)
    reference_df = build_tide_reference_display_df(theme_summary_df)
    if display_df.empty:
        st.caption("目前沒有可整理的產業分類資料。")
        return

    view_mode = st.segmented_control(
        "分類表模式",
        ["Tide完整分類", "目前有行情分類"],
        default="Tide完整分類",
        key="industry_sector_classification_mode",
        label_visibility="collapsed",
    )

    if view_mode == "Tide完整分類":
        coverage_df = reference_df.copy()
        summary_df = (
            coverage_df.groupby("大分類")
            .agg(
                Tide板塊數=("細分產業", "nunique"),
                已載入=("資料狀態", lambda series: int((series == "已載入").sum())),
                暫無行情=("資料狀態", lambda series: int((series != "已載入").sum())),
            )
            .reindex(SECTOR_GROUP_ORDER)
            .dropna(how="all")
            .reset_index()
        )
        for column in ["Tide板塊數", "已載入", "暫無行情"]:
            summary_df[column] = summary_df[column].astype(int)

        metric_cols = st.columns(4)
        metric_cols[0].metric("Tide 大分類", summary_df["大分類"].nunique())
        metric_cols[1].metric("Tide 細分板塊", coverage_df["細分產業"].nunique())
        metric_cols[2].metric("目前已載入", int((coverage_df["資料狀態"] == "已載入").sum()))
        metric_cols[3].metric("暫無行情", int((coverage_df["資料狀態"] != "已載入").sum()))

        left_col, right_col = st.columns([0.9, 1.7])
        with left_col:
            st.write("**分類摘要**")
            st.dataframe(summary_df, use_container_width=True, hide_index=True, height=360)

        with right_col:
            filter_cols = st.columns([0.9, 0.8, 1.4])
            group_options = ["全部"] + [group for group in SECTOR_GROUP_ORDER if group in set(coverage_df["大分類"])]
            selected_group = filter_cols[0].selectbox(
                "大分類",
                group_options,
                index=0,
                key="industry_tide_reference_group",
            )
            selected_coverage = filter_cols[1].selectbox(
                "資料",
                ["全部", "已載入", "Tide無行情成分"],
                index=0,
                key="industry_tide_reference_coverage",
            )
            keyword = filter_cols[2].text_input(
                "搜尋 Tide 板塊 / 代表股",
                value="",
                key="industry_tide_reference_keyword",
                placeholder="例如：HBM、CPO、記憶體、散熱",
            ).strip()

            filtered_df = coverage_df.copy()
            if selected_group != "全部":
                filtered_df = filtered_df[filtered_df["大分類"] == selected_group].copy()
            if selected_coverage != "全部":
                filtered_df = filtered_df[filtered_df["資料狀態"] == selected_coverage].copy()
            if keyword:
                mask = (
                    filtered_df["細分產業"].astype(str).str.contains(keyword, case=False, na=False)
                    | filtered_df["代表股"].astype(str).str.contains(keyword, case=False, na=False)
                )
                filtered_df = filtered_df[mask].copy()

            st.write("**Tide 細分板塊**")
            st.dataframe(filtered_df, use_container_width=True, hide_index=True, height=520)
        return

    count_df = (
        display_df.groupby("大分類")
        .agg(
            細分產業數=("細分產業", "nunique"),
            成分股數=("成分股數", "sum"),
        )
        .reindex(SECTOR_GROUP_ORDER)
        .dropna(how="all")
        .reset_index()
    )
    count_df["細分產業數"] = count_df["細分產業數"].astype(int)
    count_df["成分股數"] = count_df["成分股數"].astype(int)

    metric_cols = st.columns(4)
    metric_cols[0].metric("大分類", count_df["大分類"].nunique())
    metric_cols[1].metric("細分產業", display_df["細分產業"].nunique())
    metric_cols[2].metric("板塊成分股次", int(display_df["成分股數"].sum()))
    metric_cols[3].metric("最大分類", count_df.sort_values("細分產業數", ascending=False).iloc[0]["大分類"])

    left_col, right_col = st.columns([0.9, 1.7])
    with left_col:
        st.write("**大分類摘要**")
        st.dataframe(count_df, use_container_width=True, hide_index=True, height=360)

    with right_col:
        filter_cols = st.columns([0.9, 1.4])
        group_options = ["全部"] + [group for group in SECTOR_GROUP_ORDER if group in set(display_df["大分類"])]
        selected_group = filter_cols[0].selectbox(
            "大分類",
            group_options,
            index=0,
            key="industry_sector_classification_group",
        )
        keyword = filter_cols[1].text_input(
            "搜尋細分產業 / 代表股",
            value="",
            key="industry_sector_classification_keyword",
            placeholder="例如：CPO、記憶體、散熱、台積電",
        ).strip()

        filtered_df = display_df.copy()
        if selected_group != "全部":
            filtered_df = filtered_df[filtered_df["大分類"] == selected_group].copy()
        if keyword:
            mask = (
                filtered_df["細分產業"].astype(str).str.contains(keyword, case=False, na=False)
                | filtered_df["代表股"].astype(str).str.contains(keyword, case=False, na=False)
            )
            filtered_df = filtered_df[mask].copy()

        st.write("**細分產業清單**")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True, height=520)


def render_battle_room_tab(
    *,
    focus_summary_df,
    focus_series_df,
):
    st.write("**板塊排行**")
    st.caption("先用最直覺的方式看 Tide 細分板塊排行，不再混用本系統舊主題。你現在看到的是 Tide 板塊清單。")
    filter_cols = st.columns([1.05, 1.6])
    ranking_metric = filter_cols[0].selectbox(
        "排序依據",
        ["輪動分數", "量比", "成交值比", "單日(%)", "5日(%)", "分數1日變化", "分數3日變化"],
        index=0,
        key="industry_rotation_combined_rank_metric",
    )
    keyword = filter_cols[1].text_input(
        "搜尋項目 / 代表股",
        value="",
        key="industry_rotation_combined_keyword",
        placeholder="例如：記憶體、CPO、光通訊、南亞科、威剛",
    ).strip()

    rank_metric_map = {
        "輪動分數": "weighted_rotation_score",
        "量比": "weighted_volume_ratio",
        "成交值比": "weighted_turnover_ratio",
        "單日(%)": "weighted_latest_change_pct",
        "5日(%)": "weighted_five_day_change_pct",
        "分數1日變化": "weighted_score_delta_1d",
        "分數3日變化": "weighted_score_delta_3d",
    }

    filtered_combined_df = focus_summary_df.copy()
    if keyword:
        mask = (
            filtered_combined_df["項目"].astype(str).str.contains(keyword, case=False, na=False)
            | filtered_combined_df["representative_stocks"].astype(str).str.contains(keyword, case=False, na=False)
            | filtered_combined_df["parent_industry"].astype(str).str.contains(keyword, case=False, na=False)
        )
        filtered_combined_df = filtered_combined_df[mask].copy()

    metric_column = rank_metric_map[ranking_metric]
    filtered_combined_df = filtered_combined_df.sort_values(
        [metric_column, "weighted_rotation_score", "latest_turnover", "stock_count"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    compare_summary_df = filtered_combined_df.copy()
    st.caption(f"目前顯示 {len(compare_summary_df)} 個 Tide 細分板塊。排序已納入成分股家數權重，避免只靠 2~3 檔小型股就衝到最前面。輸入關鍵字時，下面所有圖表與表格會一起同步。")

    rank_left, rank_right = st.columns(2)
    metric_label_map = {
        "輪動分數": "輪動分數",
        "量比": "量比",
        "成交值比": "成交值比",
        "單日(%)": "單日漲跌幅 (%)",
        "5日(%)": "5日漲跌幅 (%)",
        "分數1日變化": "分數1日變化",
        "分數3日變化": "分數3日變化",
    }
    with rank_left:
        st.write("**板塊強度排行**")
        st.caption("這張圖在回答：今天最強的是哪些 Tide 板塊。")
        rank_chart = build_theme_rank_bar_chart(compare_summary_df, metric_column, metric_label_map[ranking_metric])
        if rank_chart is not None:
            st.altair_chart(rank_chart, use_container_width=True)
        else:
            st.caption("目前沒有符合篩選條件的板塊排行。")
    with rank_right:
        st.write("**分數變化排行**")
        st.caption("這張圖在回答：哪些板塊正在加速升溫，哪些開始退潮。")
        delta_chart = build_theme_rank_bar_chart(compare_summary_df, "score_delta_1d", "分數1日變化")
        if delta_chart is not None:
            st.altair_chart(delta_chart, use_container_width=True)
        else:
            st.caption("目前沒有足夠資料計算分數變化。")

    trend_focus_n = st.selectbox(
        "走勢聚焦筆數",
        [5, 8, 10],
        index=0,
        key="industry_rotation_trend_focus_n",
    )
    focus_items = compare_summary_df.head(trend_focus_n)["項目"].tolist()

    chart_left, chart_right = st.columns([1.15, 1.0])
    with chart_left:
        st.write("**報價走勢**")
        st.caption("只保留前幾個最重要板塊，避免一次太多線擠在一起。")
        if not compare_summary_df.empty and not focus_series_df.empty:
            selected_series_df = focus_series_df[focus_series_df["項目"].isin(focus_items)].copy()
            selected_series_pivot_df = (
                selected_series_df.pivot(index="trade_date", columns="顯示名稱", values="custom_index")
                .sort_index()
            )
            st.line_chart(selected_series_pivot_df, height=340)
        else:
            st.caption("目前沒有可顯示的板塊走勢。")

    with chart_right:
        st.write("**資金節奏表**")
        st.caption("這裡直接把板塊分成趨勢攻擊、量先價後、高檔整理等節奏，比泡泡圖更容易看。")
        stage_display_df = build_rotation_stage_display_df(compare_summary_df, top_n=10)
        if not stage_display_df.empty:
            st.dataframe(stage_display_df, use_container_width=True, hide_index=True)
        else:
            st.caption("目前沒有足夠資料整理資金節奏。")

    st.write("**輪動分數走勢**")
    st.caption("這裡只看前幾個重點板塊的分數線，判斷是連續升溫還是開始退潮。")
    if not compare_summary_df.empty and not focus_series_df.empty:
        selected_score_df = focus_series_df[focus_series_df["項目"].isin(focus_items)].copy()
        score_pivot_df = (
            selected_score_df.pivot(index="trade_date", columns="顯示名稱", values="rotation_score")
            .sort_index()
        )
        st.line_chart(score_pivot_df, height=280)
    else:
        st.caption("目前沒有可顯示的輪動分數走勢。")

    st.write("**輪動比較表**")
    st.caption("同一組項目直接比單日、5日、量比、成交值比、輪動分數，以及相較前幾天分數是增是減。")
    if not compare_summary_df.empty:
        compare_display_df = build_combined_rotation_display_df(compare_summary_df, pd.DataFrame())
        compare_display_df = compare_display_df.drop(columns=["類型"], errors="ignore")
        st.dataframe(compare_display_df, use_container_width=True, hide_index=True)
    else:
        st.caption("目前沒有可比較的輪動資料。")


def render_theme_members_tab(theme_summary_df, theme_report):
    st.write("**板塊成分股快照**")
    st.caption("如果想從輪動結果一路往下鑽到個股，這裡看起來會最直覺。")
    theme_options = theme_summary_df["group_name"].tolist() if not theme_summary_df.empty else []
    if theme_options:
        default_theme = "記憶體 / SSD" if "記憶體 / SSD" in theme_options else theme_options[0]
        selected_theme = st.selectbox(
            "看板塊成分股",
            options=theme_options,
            index=theme_options.index(default_theme),
            key="industry_rotation_selected_theme",
        )
        member_df = build_theme_member_display_df(theme_report["component_df"], selected_theme)
        if not member_df.empty:
            st.caption(f"{selected_theme} 成分股快照")
            st.dataframe(member_df, use_container_width=True, hide_index=True)
        else:
            st.caption("目前抓不到這個板塊的成分股快照。")
    else:
        st.caption("目前沒有可選的 Tide 細分板塊成分股。")


def render_official_indices_tab(industry_report, twse_index_snapshot, industry_top_n):
    left_col, right_col = st.columns([1.25, 1.0])
    with left_col:
        st.write("**官方科技產業聚合**")
        st.caption("如果你還是想補看純官方產業別，這裡保留完整表。")
        industry_display_df = industry_report["display_df"].head(industry_top_n).copy()
        if not industry_display_df.empty:
            st.dataframe(industry_display_df, use_container_width=True, hide_index=True)
        else:
            st.caption("目前還沒有可用的官方產業聚合資料。")

    with right_col:
        st.write("**TWSE 官方類股指數**")
        st.caption("這裡是證交所公布的上市類股指數，可拿來補看官方報價。")
        if twse_index_snapshot and not twse_index_snapshot["display_df"].empty:
            st.caption(f"指數日期：{twse_index_snapshot['used_date']}")
            st.dataframe(twse_index_snapshot["display_df"], use_container_width=True, hide_index=True)
        else:
            st.caption("目前抓不到官方類股指數資料。")
