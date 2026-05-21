import pandas as pd
import streamlit as st

from modules.core.app_constants import INSTITUTIONAL_STREAK_OPTIONS
from modules.ui.ui_display import render_rank_section


def build_bowl_candidate_rows(range_results):
    rows = []
    for code, info in sorted(
        (range_results or {}).items(),
        key=lambda item: (
            item[1].get("bowl_score") is not None,
            item[1].get("bowl_score") or 0,
            item[1].get("current_volume_ratio") or 0,
        ),
        reverse=True,
    ):
        positive_reasons = info.get("positive_reasons") or []
        caution_reasons = info.get("caution_reasons") or []
        rows.append(
            {
                "代碼": code,
                "名稱": info["name"],
                "級別": info.get("bowl_grade") or "-",
                "相似分數": info.get("bowl_score"),
                "現價": info["price"],
                "成交張數": f"{round(info['latest_volume'] / 1000, 1):,}" if info.get("latest_volume") is not None else "-",
                "近3日均張數": f"{round(info['avg_volume_3'] / 1000, 1):,}" if info.get("avg_volume_3") is not None else "-",
                "前3日均張數": f"{round(info['avg_volume_prev3'] / 1000, 1):,}" if info.get("avg_volume_prev3") is not None else "-",
                "20日均張數": f"{round(info['avg_volume_20'] / 1000, 1):,}" if info.get("avg_volume_20") is not None else "-",
                "當日量增倍數": f"{info['current_volume_ratio']:.2f}x" if info.get("current_volume_ratio") is not None else "-",
                "近3日量增倍數": f"{info['recent3_volume_ratio']:.2f}x" if info.get("recent3_volume_ratio") is not None else "-",
                "區間內位置(%)": f"{info['range_position_pct']:.1f}%" if info.get("range_position_pct") is not None else "-",
                "距區間上緣(%)": f"{info['peak_distance_pct']:.2f}%" if info.get("peak_distance_pct") is not None else "-",
                "突破區間(%)": f"{info['breakout_pct']:.2f}%" if info.get("breakout_pct") is not None else "-",
                "連續放量天數": info.get("sustain_days") if info.get("sustain_days") is not None else "-",
                "入選原因": "；".join(positive_reasons[:3]) if positive_reasons else "-",
                "觀察點": "；".join(caution_reasons[:2]) if caution_reasons else "-",
            }
        )
    return rows


def _render_bowl_candidate_section(rows, grade, title, caption, limit):
    grade_rows = [row for row in rows if row.get("級別") == grade]
    st.write(f"**{title}**")
    st.caption(caption)
    if grade_rows:
        compact_columns = [
            "代碼",
            "名稱",
            "級別",
            "相似分數",
            "成交張數",
            "近3日均張數",
            "前3日均張數",
            "20日均張數",
            "區間內位置(%)",
            "距區間上緣(%)",
            "突破區間(%)",
            "當日量增倍數",
            "近3日量增倍數",
            "連續放量天數",
            "入選原因",
            "觀察點",
        ]
        compact_rows = [{column: row.get(column, "-") for column in compact_columns} for row in grade_rows[:limit]]
        st.dataframe(
            compact_rows,
            width="stretch",
            hide_index=True,
            column_order=compact_columns,
            column_config={
                "代碼": st.column_config.Column(width="small", pinned=True),
                "名稱": st.column_config.Column(width="small", pinned=True),
                "級別": st.column_config.Column(width="small"),
                "相似分數": st.column_config.Column(width="small"),
                "成交張數": st.column_config.Column(width="small"),
                "近3日均張數": st.column_config.Column(width="small"),
                "前3日均張數": st.column_config.Column(width="small"),
                "20日均張數": st.column_config.Column(width="small"),
                "區間內位置(%)": st.column_config.Column(width="small"),
                "距區間上緣(%)": st.column_config.Column(width="small"),
                "突破區間(%)": st.column_config.Column(width="small"),
                "當日量增倍數": st.column_config.Column(width="small"),
                "近3日量增倍數": st.column_config.Column(width="small"),
                "連續放量天數": st.column_config.Column(width="small"),
                "入選原因": st.column_config.Column(width="large"),
                "觀察點": st.column_config.Column(width="medium"),
            },
        )
    else:
        st.caption("目前這一層還沒有候選股。")


def render_homepage_tabs(
    *,
    state,
    background_manager,
    daily_institutional,
    institutional_results,
    revenue_result,
    market_watch_result,
    disposition_result,
    industry_flow_bundle,
    industry_flow_job,
    industry_flow_job_id,
    schedule_bundle,
):
    home_tabs = st.tabs(["法人連買觀察", "資金流向", "法說日程", "月營收動能", "處置股票"])

    with home_tabs[0]:
        has_daily_price_data = (
            daily_institutional.get("foreign", {}).get("has_price_data")
            if daily_institutional.get("foreign") else False
        )

        st.write("**當日前三十名**")
        daily_foreign_col, daily_total_col = st.columns(2)

        with daily_foreign_col:
            st.write("**外資當日前三十名**")
            if daily_institutional.get("foreign"):
                render_rank_section(daily_institutional["foreign"]["buy_rank_df"], "買超前三十名｜單位：百萬元 / 張", "目前沒有外資買超前三十名資料。")
                render_rank_section(daily_institutional["foreign"]["sell_rank_df"], "賣超前三十名｜單位：百萬元 / 張", "目前沒有外資賣超前三十名資料。")
            else:
                st.caption("目前抓不到足夠的外資當日前三十名資料。")

        with daily_total_col:
            st.write("**三大法人當日前三十名**")
            if daily_institutional.get("total"):
                render_rank_section(daily_institutional["total"]["buy_rank_df"], "買超前三十名｜單位：百萬元 / 張", "目前沒有三大法人買超前三十名資料。")
                render_rank_section(daily_institutional["total"]["sell_rank_df"], "賣超前三十名｜單位：百萬元 / 張", "目前沒有三大法人賣超前三十名資料。")
            else:
                st.caption("目前抓不到足夠的三大法人當日前三十名資料。")

        for streak_days in INSTITUTIONAL_STREAK_OPTIONS:
            streak_group = institutional_results.get(streak_days, {})
            foreign_streak = streak_group.get("foreign")
            total_streak = streak_group.get("total")
            st.write(f"**連{streak_days}日都在前三十名**")
            foreign_section, total_section = st.columns(2)
            with foreign_section:
                st.write(f"**外資連{streak_days}日**")
                if foreign_streak:
                    render_rank_section(foreign_streak["buy_rank_df"], "買超前三十名｜單位：百萬元 / 張", f"最近 {streak_days} 天沒有股票每天都同時留在外資買超前三十名。")
                    render_rank_section(foreign_streak["sell_rank_df"], "賣超前三十名｜單位：百萬元 / 張", f"最近 {streak_days} 天沒有股票每天都同時留在外資賣超前三十名。")
                else:
                    st.caption(f"目前抓不到足夠的外資連{streak_days}日資料，通常代表最近 {streak_days} 天沒有股票每天都還留在前三十名。")

            with total_section:
                st.write(f"**三大法人連{streak_days}日**")
                if total_streak:
                    render_rank_section(total_streak["buy_rank_df"], "買超前三十名｜單位：百萬元 / 張", f"最近 {streak_days} 天沒有股票每天都同時留在三大法人買超前三十名。")
                    render_rank_section(total_streak["sell_rank_df"], "賣超前三十名｜單位：百萬元 / 張", f"最近 {streak_days} 天沒有股票每天都同時留在三大法人賣超前三十名。")
                else:
                    st.caption(f"目前抓不到足夠的三大法人連{streak_days}日資料，通常代表最近 {streak_days} 天沒有股票每天都還留在前三十名。")

    with home_tabs[1]:
        st.write("**官方產業資金流向**")
        st.caption("比較每個官方產業當日總成交金額，對照前 20 個交易日均值，並按上升比例由大到小排序。")
        if industry_flow_bundle and industry_flow_bundle.get("display_df") is not None:
            st.caption(
                f"使用資料日：{industry_flow_bundle.get('used_date')}｜"
                f"對照區間：最近 {industry_flow_bundle.get('history_trade_days')} 個交易日"
            )
            st.dataframe(
                industry_flow_bundle["display_df"],
                width="stretch",
                hide_index=True,
                column_config={
                    "產業": st.column_config.Column(width="medium", pinned=True),
                    "當日成交金額": st.column_config.Column(width="small"),
                    "20日均成交金額": st.column_config.Column(width="small"),
                    "上升比例": st.column_config.Column(width="small"),
                    "高於20日均值(%)": st.column_config.Column(width="small"),
                    "平均漲跌幅(%)": st.column_config.Column(width="small"),
                    "成分股數": st.column_config.Column(width="small"),
                },
            )
        elif industry_flow_job and industry_flow_job["status"] == "failed":
            failed_job = background_manager.get_job(industry_flow_job_id, include_result=False)
            st.error(f"讀取首頁資金流向失敗：{failed_job.get('error') or '未知錯誤'}")
        else:
            st.caption("資金流向資料整理中，稍後會自動顯示。")

    with home_tabs[2]:
        st.write("**未來一個月法說會 / 發表會**")
        st.caption("先看預設追蹤公司的未來一個月活動。這塊不需要等 AI 法說分析，就會先顯示。")
        schedule_rows = []
        for company_query, bundle in (schedule_bundle or {}).items():
            for item in (bundle.get("events") or [])[:6]:
                schedule_rows.append(
                    {
                        "公司": company_query,
                        "日期": item.get("event_date_text") or "-",
                        "剩餘天數": item.get("days_until"),
                        "類型": item.get("event_type") or "-",
                        "標題": item.get("title") or "-",
                        "來源": item.get("domain") or "-",
                    }
                )
        schedule_rows = sorted(schedule_rows, key=lambda row: (row["日期"], row["公司"], row["類型"]))
        if schedule_rows:
            st.dataframe(pd.DataFrame(schedule_rows[:30]), use_container_width=True, hide_index=True)
        else:
            st.caption("目前還抓不到未來一個月內可辨識的法說會或發表會日期。")

    with home_tabs[3]:
        if revenue_result and not revenue_result["top_df"].empty:
            revenue_cols = st.columns(4)
            revenue_cols[0].metric("資料月份", revenue_result["report_month"])
            revenue_cols[1].metric("出表日期", revenue_result["output_date"])
            revenue_cols[2].metric("符合條件總檔數", revenue_result["screened_count"])
            revenue_cols[3].metric("目前顯示筆數", min(state["revenue_top_n"], revenue_result["screened_count"]))
            if revenue_result.get("used_months"):
                mode_label = "連續月營收模式" if revenue_result.get("history_mode") == "consecutive" else "保守 fallback 模式"
                feb_label = "排除 2 月均值" if revenue_result.get("exclude_february_from_average") else "包含 2 月均值"
                scope_label = "科技股限定" if revenue_result.get("technology_only") else "全市場"
                st.caption(f"{scope_label}｜{mode_label}｜觀察月份：{' / '.join(revenue_result['used_months'])}｜{feb_label}")

            revenue_display_df = revenue_result["top_df"].copy().rename(
                columns={
                    "code": "代碼",
                    "name_zh": "名稱",
                    "market": "市場",
                    "industry": "產業",
                    "report_month": "資料月份",
                    "output_date": "出表日期",
                    "current_revenue": "當月營收(千元)",
                    "mom_pct": "MoM(%)",
                    "yoy_pct": "YoY(%)",
                    "cumulative_yoy_pct": "累計YoY(%)",
                    "overall_growth_pct": "近3月整體增幅(%)",
                    "positive_step_count": "上行月數",
                    "latest_vs_recent_average_pct": "最新月高於前均值(%)",
                    "momentum_score": "動能分數",
                }
            )
            revenue_display_df["當月營收(千元)"] = revenue_display_df["當月營收(千元)"].map(
                lambda value: f"{int(round(value)):,}" if value is not None and value == value else "-"
            )
            for column in ["MoM(%)", "YoY(%)", "累計YoY(%)", "近3月整體增幅(%)", "最新月高於前均值(%)", "動能分數"]:
                revenue_display_df[column] = revenue_display_df[column].map(
                    lambda value: f"{value:.2f}" if value is not None and value == value else "-"
                )
            revenue_display_df["上行月數"] = revenue_display_df["上行月數"].map(
                lambda value: f"{int(value)}" if value is not None and value == value else "-"
            )

            st.caption("這份排行現在只看科技股，優先抓最近 3 個月整體墊高、最新月仍站上近期高點的公司，再用 YoY、MoM、累計 YoY 當輔助排序。")
            st.caption(f"目前表格只顯示排序前 {min(state['revenue_top_n'], revenue_result['screened_count'])} 檔；若想看更多，可以把左側的「首頁顯示幾檔」調大。")
            st.dataframe(revenue_display_df, use_container_width=True, hide_index=True)
        elif revenue_result:
            st.caption("最新官方月營收資料有抓到，但目前沒有股票同時符合你設定的 MoM / YoY 條件。")
        else:
            st.caption("目前還抓不到月營收動能資料，可能是官方來源暫時不可用。")

    with home_tabs[4]:
        if disposition_result and not disposition_result["df"].empty:
            st.caption("這裡整合上市與上櫃的官方處置股票名單。")
            st.dataframe(disposition_result["df"], use_container_width=True, hide_index=True)
        else:
            st.caption("目前沒有抓到處置股票資料，可能今天沒有名單或官方來源尚未更新。")
