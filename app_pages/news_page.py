from datetime import datetime

import pandas as pd
import streamlit as st

from modules.news.news_analysis import build_news_analysis_bundle
from modules.core.trading_calendar import resolve_recent_trade_date
from modules.ui.ui_display import format_company_link_badges, render_reaction_metrics
from modules.ui.ui_jobs import ensure_background_data_job, get_background_data_job_manager
from modules.ui.ui_status import render_background_data_job_status


def render_news_page(state):
    st.subheader("新聞分析")
    trade_date_resolution = resolve_recent_trade_date(state["news_trade_date"])
    effective_trade_date = trade_date_resolution["effective_date"]
    if trade_date_resolution["used_fallback"]:
        st.caption(
            f"新聞觀察日期 {trade_date_resolution['requested_date']} 非交易日或尚無完整行情，"
            f"已自動改用最近可讀交易日：{trade_date_resolution['effective_date_text']}"
        )
    action_cols = st.columns([0.9, 0.9, 0.9, 2.3])
    run_news_analysis = action_cols[0].button("執行", use_container_width=True, key="run_news_analysis")
    rerun_news_analysis = action_cols[1].button("重新整理", use_container_width=True, key="rerun_news_analysis")
    clear_news_analysis = action_cols[2].button("清除結果", use_container_width=True, key="clear_news_analysis")
    action_cols[3].caption("只在你按按鈕時整理新聞分析。")
    if clear_news_analysis:
        st.session_state["news_analysis_job_id"] = None
        st.rerun()
    cache_key = (
        "v4",
        datetime.now().strftime("%Y-%m-%d"),
        str(effective_trade_date),
        int(state["news_industry_count"]),
        int(state["news_headlines_per_industry"]),
        int(state["us_news_items"]),
    )
    job_id, job = ensure_background_data_job(
        "news_analysis_job_id",
        "news_analysis",
        cache_key,
        build_news_analysis_bundle,
        args=(
            effective_trade_date,
        ),
        kwargs={
            "industry_count": state["news_industry_count"],
            "headlines_per_industry": state["news_headlines_per_industry"],
            "us_news_items": state["us_news_items"],
        },
        running_message="正在整理新聞與產業熱度...",
        completed_message="新聞分析資料已整理完成",
        failed_message="新聞分析資料整理失敗",
        autostart=False,
        force_start=(run_news_analysis or rerun_news_analysis),
    )

    if job and job["status"] == "failed":
        failed_job = get_background_data_job_manager().get_job(job_id, include_result=False)
        st.error(f"讀取新聞分析失敗：{failed_job.get('error') or '未知錯誤'}")
        return

    if not job:
        st.info("目前是手動模式。按上面的 `執行新聞分析整理` 後，才會丟進背景 queue。")
        return

    if job["status"] != "completed":
        st.info("新聞分析背景整理中，完成後會自動刷新。")
        render_background_data_job_status("news_analysis_job_id", "新聞分析背景任務")
        return

    news_bundle = get_background_data_job_manager().get_job(job_id, include_result=True).get("result")

    if not news_bundle:
        return

    daily_brief = news_bundle.get("daily_brief", [])
    event_watch = news_bundle.get("event_watch")
    theme_news = news_bundle.get("theme_news")
    industry_news = news_bundle.get("industry_news")
    overlap_result = news_bundle.get("overlap_result")
    us_snapshot = news_bundle.get("us_snapshot")
    us_news = news_bundle.get("us_news")
    mna_news = news_bundle.get("mna_news")
    earnings_news = news_bundle.get("earnings_news")
    order_flow_news = news_bundle.get("order_flow_news")
    company_focus_news = news_bundle.get("company_focus_news")

    summary_cols = st.columns(5)
    summary_cols[0].metric("細分主題數", len(theme_news["sections"]) if theme_news else 0)
    summary_cols[1].metric("產業交集數", len(overlap_result["display_df"]) if overlap_result else 0)
    summary_cols[2].metric("美股新聞則數", len(us_news["merged_items"]) if us_news else 0)
    summary_cols[3].metric("重要事件類別", len(event_watch["topics"]) if event_watch else 0)
    summary_cols[4].metric("觀察日期", industry_news["used_date"] if industry_news else effective_trade_date.strftime("%Y-%m-%d"))

    news_tabs = st.tabs(["總覽", "台股主題", "美股與事件"])
    with news_tabs[0]:
        overview_left, overview_right = st.columns([1.2, 1])
        with overview_left:
            st.write("**今日摘要**")
            st.caption("先看今天最值得優先注意的題材與事件。")
            if daily_brief:
                for bullet in daily_brief:
                    st.markdown(f"- {bullet}")
            else:
                st.caption("目前還沒有足夠資料可以整理今日摘要。")

        with overview_right:
            if us_snapshot:
                st.write("**美股市場快照**")
                st.caption(us_snapshot["summary"])
                snapshot_df = us_snapshot["snapshot_df"].copy()
                snapshot_df["收盤"] = snapshot_df["收盤"].map(lambda value: f"{value:.2f}")
                snapshot_df["單日(%)"] = snapshot_df["單日(%)"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
                snapshot_df["近5日(%)"] = snapshot_df["近5日(%)"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
                st.dataframe(snapshot_df, use_container_width=True, hide_index=True)

        signal_left, signal_right = st.columns(2)
        with signal_left:
            if overlap_result is not None and not overlap_result["display_df"].empty:
                st.write("**產業交集訊號**")
                st.caption("同時兼具量價熱度與營收動能的產業，通常更值得優先追蹤。")
                st.dataframe(overlap_result["display_df"], use_container_width=True, hide_index=True)

        with signal_right:
            if theme_news and not theme_news["display_df"].empty:
                st.write("**熱門細分主題**")
                st.caption("這裡先把大產業再往下拆成更貼近盤面的主題，例如 ABF、PCB、DRAM、CPO、散熱、AI Agent。")
                st.dataframe(theme_news["display_df"], use_container_width=True, hide_index=True)

        if company_focus_news and (company_focus_news.get("bullish_items") or company_focus_news.get("bearish_items")):
            st.write("**重點利多 / 利空觀察**")
            st.caption(company_focus_news.get("summary", ""))
            focus_left, focus_right = st.columns(2)
            with focus_left:
                st.write("`偏利多`")
                if company_focus_news.get("bullish_items"):
                    for item in company_focus_news["bullish_items"][:3]:
                        st.markdown(f"- [{item.get('title_zh') or item['title']}]({item['link']})")
                        st.caption(format_company_link_badges(item.get("company_links", [])))
                else:
                    st.caption("目前沒有明顯的利多焦點。")
            with focus_right:
                st.write("`偏利空`")
                if company_focus_news.get("bearish_items"):
                    for item in company_focus_news["bearish_items"][:3]:
                        st.markdown(f"- [{item.get('title_zh') or item['title']}]({item['link']})")
                        st.caption(format_company_link_badges(item.get("company_links", [])))
                else:
                    st.caption("目前沒有明顯的利空焦點。")

    with news_tabs[1]:
        heat_left, heat_right = st.columns(2)
        with heat_left:
            if theme_news and not theme_news["display_df"].empty:
                st.write("**細分主題熱度**")
                st.caption("這份表會把大產業往下拆成更接近盤面炒作語言的題材。")
                st.dataframe(theme_news["display_df"], use_container_width=True, hide_index=True)
            else:
                st.caption("目前還抓不到可用的細分主題熱度資料。")

        with heat_right:
            if industry_news and not industry_news["hot_industry_df"].empty:
                st.write("**大產業熱度**")
                st.caption("這份表主要用成交量、平均漲跌幅與鎖住漲停家數，去估目前最有勢頭的大產業。")
                st.dataframe(industry_news["hot_industry_df"], use_container_width=True, hide_index=True)
            else:
                st.caption("目前還抓不到可用的大產業熱度資料。")

        inner_tabs = st.tabs(["細分主題新聞", "大產業新聞", "重點利多 / 利空"])
        with inner_tabs[0]:
            if theme_news and theme_news["sections"]:
                st.caption(f"觀察資料日：{theme_news['used_date']}。這裡會先看更貼近盤面的題材新聞。")
                for idx, section in enumerate(theme_news["sections"]):
                    with st.expander(f"{section['theme']}｜{section['summary'][:40]}...", expanded=(idx == 0)):
                        st.write(section["summary"])
                        st.caption(f"代表股：{section['representative_stocks']}")
                        for item in section["news_items"]:
                            source_text = item["source"] or "Google News"
                            published_text = item["published_at"] or ""
                            st.markdown(f"- [{item['title']}]({item['link']})")
                            st.caption(f"{source_text}｜{published_text}")
                            if item.get("company_links"):
                                st.caption(f"對應公司：{format_company_link_badges(item['company_links'])}")
                            if item.get("theme_links"):
                                st.caption(f"對應題材：{'、'.join(item['theme_links'])}")
            else:
                st.caption("目前還抓不到可用的細分主題新聞。")

        with inner_tabs[1]:
            if industry_news and industry_news["sections"]:
                st.caption(f"觀察資料日：{industry_news['used_date']}。以下先用成交量與價格反應找出較熱的大產業，再去抓各產業最近幾天的相關新聞。")
                for idx, section in enumerate(industry_news["sections"]):
                    with st.expander(f"{section['industry']}｜{section['summary'][:40]}...", expanded=(idx == 0)):
                        st.write(section["summary"])
                        st.caption(f"代表股：{section['representative_stocks']}")
                        for item in section["news_items"]:
                            source_text = item["source"] or "Google News"
                            published_text = item["published_at"] or ""
                            st.markdown(f"- [{item['title']}]({item['link']})")
                            st.caption(f"{source_text}｜{published_text}")
                            if item.get("company_links"):
                                st.caption(f"對應公司：{format_company_link_badges(item['company_links'])}")
                            if item.get("theme_links"):
                                st.caption(f"對應題材：{'、'.join(item['theme_links'])}")
            else:
                st.caption("目前還抓不到可用的大產業新聞。")

        with inner_tabs[2]:
            if company_focus_news and company_focus_news.get("items"):
                st.caption(company_focus_news.get("summary", ""))
                focus_cols = st.columns(2)
                with focus_cols[0]:
                    st.write("**偏利多**")
                    if company_focus_news.get("bullish_items"):
                        for item in company_focus_news["bullish_items"][:6]:
                            with st.expander(item.get("title_zh") or item["title"], expanded=False):
                                st.caption(f"{item['title']}｜{item['source']}｜{item['published_at']}")
                                st.caption(f"對應公司：{format_company_link_badges(item.get('company_links', []))}")
                                if item.get("theme_links"):
                                    st.caption(f"對應題材：{'、'.join(item['theme_links'])}")
                                st.write(f"判讀：{item.get('tone', '偏中性')}｜影響分數 {item.get('impact_score', 0)}")
                    else:
                        st.caption("目前還抓不到明顯偏利多的台股公司消息。")
                with focus_cols[1]:
                    st.write("**偏利空**")
                    if company_focus_news.get("bearish_items"):
                        for item in company_focus_news["bearish_items"][:6]:
                            with st.expander(item.get("title_zh") or item["title"], expanded=False):
                                st.caption(f"{item['title']}｜{item['source']}｜{item['published_at']}")
                                st.caption(f"對應公司：{format_company_link_badges(item.get('company_links', []))}")
                                if item.get("theme_links"):
                                    st.caption(f"對應題材：{'、'.join(item['theme_links'])}")
                                st.write(f"判讀：{item.get('tone', '偏中性')}｜影響分數 {item.get('impact_score', 0)}")
                    else:
                        st.caption("目前還抓不到明顯偏利空的台股公司消息。")
            else:
                st.caption("目前還抓不到足夠的台股公司焦點新聞。")

    with news_tabs[2]:
        market_col, event_col = st.columns([0.9, 1.1])
        with market_col:
            if us_snapshot:
                st.write("**美股市場快照**")
                st.caption(us_snapshot["summary"])
                snapshot_df = us_snapshot["snapshot_df"].copy()
                snapshot_df["收盤"] = snapshot_df["收盤"].map(lambda value: f"{value:.2f}")
                snapshot_df["單日(%)"] = snapshot_df["單日(%)"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
                snapshot_df["近5日(%)"] = snapshot_df["近5日(%)"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
                st.dataframe(snapshot_df, use_container_width=True, hide_index=True)

        with event_col:
            if event_watch and event_watch["topics"]:
                st.write("**重要事件**")
                st.caption("這裡會特別追川普發言、聯準會 / Powell，以及美國總體數據，並用 QQQ 當 Nasdaq 代理去看新聞後的市場反應。")
                for topic in event_watch["topics"]:
                    with st.expander(topic["topic"], expanded=(topic["topic"] == "川普發言")):
                        st.write(topic["summary"])
                        if topic.get("ai_summary"):
                            st.info(topic["ai_summary"].get("section_summary", ""))
                        if topic["items"]:
                            for item in topic["items"]:
                                st.markdown(f"- [{item.get('title_zh') or item['title']}]({item['link']})")
                                st.caption(f"{item['title']}｜{item['source']}｜{item['published_at']}")
                                reaction = item.get("reaction")
                                if reaction:
                                    render_reaction_metrics(reaction)
                                st.write(item["comment"])
                        else:
                            st.caption("目前沒有抓到足夠新聞。")
            else:
                st.caption("目前還抓不到可用的重要事件新聞。")

        extra_news_tabs = st.tabs(["美國大廠接單", "併購消息", "財報公布", "財報後分析"])
        with extra_news_tabs[0]:
            if order_flow_news and order_flow_news["items"]:
                st.write("**美國大廠接單 / 供應鏈**")
                st.write(order_flow_news.get("summary", ""))
                for item in order_flow_news["items"]:
                    with st.expander(item.get("title_zh") or item["title"], expanded=False):
                        st.caption(f"{item['title']}｜{item['source']}｜{item['published_at']}")
                        st.caption(f"對應公司：{format_company_link_badges(item.get('company_links', []))}")
                        if item.get("theme_links"):
                            st.caption(f"對應題材：{'、'.join(item['theme_links'])}")
                        reaction = item.get("reaction")
                        if reaction:
                            render_reaction_metrics(reaction)
                        if item.get("comment"):
                            st.write(item["comment"])
            else:
                st.caption("目前還抓不到可用的美國大廠接單 / 供應鏈新聞。")

        with extra_news_tabs[1]:
            if mna_news and mna_news["items"]:
                st.write("**併購消息**")
                st.caption("這裡優先抓 merger / acquisition / takeover / buyout 這類英文新聞，再保留中文重點與市場反應。")
                st.write(mna_news["summary"])
                if mna_news.get("ai_summary"):
                    st.info(mna_news["ai_summary"].get("section_summary", ""))
                    ai_item_map = {item["title"]: item for item in mna_news["ai_summary"].get("items", [])}
                else:
                    ai_item_map = {}
                for item in mna_news["items"]:
                    st.markdown(f"- [{item.get('title_zh') or item['title']}]({item['link']})")
                    st.caption(f"{item['title']}｜{item['source']}｜{item['published_at']}")
                    reaction = item.get("reaction")
                    if reaction:
                        render_reaction_metrics(reaction)
                    ai_item = ai_item_map.get(item.get("title"))
                    if ai_item:
                        themes_text = "、".join(ai_item.get("taiwan_themes", [])) or "暫無明確對應題材"
                        st.write(f"{ai_item.get('analysis', '')} 可能影響台股題材：{themes_text}")
                    st.caption(f"對應公司：{format_company_link_badges(item.get('company_links', []))}")
                    if item.get("comment"):
                        st.write(item["comment"])
            else:
                st.caption("目前還抓不到可用的併購消息。")

        with extra_news_tabs[2]:
            if earnings_news and earnings_news["items"]:
                st.write("**財報公布**")
                st.caption("這裡優先抓 earnings / results / guidance / beats / misses 這類英文新聞，再保留中文重點。")
                st.write(earnings_news["summary"])
                if earnings_news.get("ai_summary"):
                    st.info(earnings_news["ai_summary"].get("section_summary", ""))
                for item in earnings_news["items"]:
                    st.markdown(f"- [{item.get('title_zh') or item['title']}]({item['link']})")
                    st.caption(f"{item['title']}｜{item['source']}｜{item['published_at']}")
                    st.caption(f"對應公司：{format_company_link_badges(item.get('company_links', []))}")
                    if item.get("theme_links"):
                        st.caption(f"對應題材：{'、'.join(item['theme_links'])}")
            else:
                st.caption("目前還抓不到可用的財報公布新聞。")

        with extra_news_tabs[3]:
            if earnings_news and earnings_news["items"]:
                st.write("**財報後分析**")
                st.caption("這裡會把財報新聞和 QQQ 的後續反應放在一起，幫你快速看市場到底是買單還是不買單。")
                ai_item_map = {
                    item["title"]: item for item in earnings_news.get("ai_summary", {}).get("items", [])
                } if earnings_news.get("ai_summary") else {}
                for item in earnings_news["items"]:
                    with st.expander(item.get("title_zh") or item["title"], expanded=False):
                        st.caption(f"{item['title']}｜{item['source']}｜{item['published_at']}")
                        reaction = item.get("reaction")
                        if reaction:
                            render_reaction_metrics(reaction)
                        ai_item = ai_item_map.get(item.get("title"))
                        if ai_item:
                            st.write(f"AI判讀：{ai_item.get('tone', '偏中性')}｜{ai_item.get('analysis', '')}")
                            themes_text = "、".join(ai_item.get("taiwan_themes", [])) or "暫無明確對應題材"
                            st.caption(f"可能影響台股題材：{themes_text}")
                        st.caption(f"對應公司：{format_company_link_badges(item.get('company_links', []))}")
                        if item.get("comment"):
                            st.write(item["comment"])
            else:
                st.caption("目前還抓不到足夠的財報後分析資料。")

        if us_news:
            st.write("**美股英文新聞 / 中文重點**")
            bucket_cols = st.columns(3)
            for column, (bucket_name, items) in zip(bucket_cols, us_news["bucket_items"].items()):
                with column:
                    st.write(f"**{bucket_name}**")
                    if items:
                        for item in items[:max(3, state["us_news_items"] // 2)]:
                            source_text = item["source"] or "Google News"
                            published_text = item["published_at"] or ""
                            st.markdown(f"- [{item.get('title_zh') or item['title']}]({item['link']})")
                            st.caption(f"{item['title']}｜{source_text}｜{published_text}")
                    else:
                        st.caption("目前沒有抓到新聞。")
        else:
            st.caption("目前還抓不到可用的美股新聞。")
