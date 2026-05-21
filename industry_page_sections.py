import pandas as pd
import streamlit as st

from industry_rotation import build_theme_member_display_df
from industry_page_helpers import (
    build_combined_rotation_display_df,
    build_rotation_stage_display_df,
    build_theme_rank_bar_chart,
)


def render_battle_room_tab(
    *,
    focus_summary_df,
    focus_series_df,
):
    st.write("**主題排行**")
    st.caption("先用最直覺的方式看細分主題排行，不再混官方產業，也不需要先手動挑比較項目。你現在看到的就是完整主題清單。")
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
    st.caption(f"目前顯示 {len(compare_summary_df)} 個細分主題。排序已納入成分股家數權重，避免只靠 2~3 檔小型股就衝到最前面。輸入關鍵字時，下面所有圖表與表格會一起同步。")

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
        st.write("**主題強度排行**")
        st.caption("這張圖在回答：今天最強的是哪些主題。")
        rank_chart = build_theme_rank_bar_chart(compare_summary_df, metric_column, metric_label_map[ranking_metric])
        if rank_chart is not None:
            st.altair_chart(rank_chart, use_container_width=True)
        else:
            st.caption("目前沒有符合篩選條件的主題排行。")
    with rank_right:
        st.write("**分數變化排行**")
        st.caption("這張圖在回答：哪些主題正在加速升溫，哪些開始退潮。")
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
        st.caption("只保留前幾個最重要主題，避免一次太多線擠在一起。")
        if not compare_summary_df.empty and not focus_series_df.empty:
            selected_series_df = focus_series_df[focus_series_df["項目"].isin(focus_items)].copy()
            selected_series_pivot_df = (
                selected_series_df.pivot(index="trade_date", columns="顯示名稱", values="custom_index")
                .sort_index()
            )
            st.line_chart(selected_series_pivot_df, height=340)
        else:
            st.caption("目前沒有可顯示的主題走勢。")

    with chart_right:
        st.write("**資金節奏表**")
        st.caption("這裡直接把主題分成趨勢攻擊、量先價後、高檔整理等節奏，比泡泡圖更容易看。")
        stage_display_df = build_rotation_stage_display_df(compare_summary_df, top_n=10)
        if not stage_display_df.empty:
            st.dataframe(stage_display_df, use_container_width=True, hide_index=True)
        else:
            st.caption("目前沒有足夠資料整理資金節奏。")

    st.write("**輪動分數走勢**")
    st.caption("這裡只看前幾個重點主題的分數線，判斷是連續升溫還是開始退潮。")
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
    st.write("**主題成分股快照**")
    st.caption("如果想從輪動結果一路往下鑽到個股，這裡看起來會最直覺。")
    theme_options = theme_summary_df["group_name"].tolist() if not theme_summary_df.empty else []
    if theme_options:
        default_theme = "記憶體 / SSD" if "記憶體 / SSD" in theme_options else theme_options[0]
        selected_theme = st.selectbox(
            "看主題成分股",
            options=theme_options,
            index=theme_options.index(default_theme),
            key="industry_rotation_selected_theme",
        )
        member_df = build_theme_member_display_df(theme_report["component_df"], selected_theme)
        if not member_df.empty:
            st.caption(f"{selected_theme} 成分股快照")
            st.dataframe(member_df, use_container_width=True, hide_index=True)
        else:
            st.caption("目前抓不到這個主題的成分股快照。")
    else:
        st.caption("目前沒有可選的細分主題成分股。")


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
