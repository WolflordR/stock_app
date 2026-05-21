from datetime import datetime

import pandas as pd
import streamlit as st

from news_ai import get_llm_backend_label, has_llm_backend
from research_workbench_data import (
    DEFAULT_RESEARCH_COMPANIES,
    TERM_GLOSSARY,
    TRANSCRIPT_KEYWORD_GROUPS,
    TRANSCRIPT_SHORTCUTS,
    analyze_transcript_excerpt_ai as _analyze_transcript_excerpt_ai,
    build_tracking_company_card_rows,
    build_tracking_company_schedule_payload_map as _build_tracking_company_schedule_payload_map,
    build_tracking_company_payload_map as _build_tracking_company_payload_map,
    build_tracking_overview_stats,
    extract_tracking_summary_row as _extract_tracking_summary_row,
    extract_transcript_analysis as _extract_transcript_analysis,
    normalize_transcript_text as _normalize_transcript_text,
    parse_tracking_companies as _parse_tracking_companies,
)
from ui_jobs import ensure_background_data_job, get_background_data_job_manager
from ui_status import render_background_data_job_status


def _render_keyword_block_table(title, items, empty_text):
    st.write(f"**{title}**")
    if not items:
        st.caption(empty_text)
        return
    block_df = pd.DataFrame(items)
    if "taiwan_supply_chain" in block_df.columns:
        block_df["台股方向"] = block_df["taiwan_supply_chain"].map(lambda values: "、".join(values) if values else "-")
    else:
        block_df["台股方向"] = "-"
    block_df = block_df.rename(
        columns={
            "keyword_en": "英文詞",
            "keyword_zh": "中文詞",
            "meaning": "中文解釋",
            "evidence_excerpt": "原文依據",
        }
    )
    available_columns = [column for column in ["英文詞", "中文詞", "中文解釋", "台股方向", "原文依據"] if column in block_df.columns]
    st.dataframe(
        block_df[available_columns],
        use_container_width=True,
        hide_index=True,
    )


def _render_tracking_overview_dashboard(summary_df, valid_payloads):
    stats = build_tracking_overview_stats(summary_df)
    card_rows = build_tracking_company_card_rows(valid_payloads)

    metric_cols = st.columns(5)
    metric_cols[0].metric("追蹤公司", stats["tracked_count"])
    metric_cols[1].metric("抓到來源總數", stats["source_count"])
    metric_cols[2].metric("最常出現方向", stats["top_direction"])
    metric_cols[3].metric("供應鏈方向數", stats["direction_coverage"])
    metric_cols[4].metric("一個月內活動", stats["upcoming_events"])

    st.write("**追蹤重點卡**")
    st.caption("先看每家公司這次抓到多少來源、偏向哪些台股方向，再決定要不要往下看完整來源。")
    card_cols = st.columns(min(3, max(1, len(card_rows))))
    for index, row in enumerate(card_rows[:6]):
        with card_cols[index % len(card_cols)].container(border=True):
            st.write(f"**{row['公司']}**")
            st.caption(
                f"來源 {row['來源數']}｜瓶頸 {row['瓶頸數']}｜技術 {row['技術詞數']}｜"
                f"Capex {row['Capex數']}｜接單台廠 {row['接單台廠數']}｜"
                f"一個月內活動 {row['一個月內活動數']}"
            )
            st.caption(f"最近活動日：{row['最近活動日']}")
            st.caption(f"台股方向：{row['台股方向']}")
            st.write(row["摘要"])


def _build_schedule_overview_df(schedule_payload_map):
    rows = []
    for company_query, schedule_bundle in (schedule_payload_map or {}).items():
        events = schedule_bundle.get("events") or []
        nearest = events[0] if events else {}
        rows.append(
            {
                "公司": company_query,
                "一個月內活動": len(events),
                "最近活動日": nearest.get("event_date_text") or "-",
                "最近活動類型": nearest.get("event_type") or "-",
                "最近活動標題": nearest.get("title") or "-",
            }
        )
    return pd.DataFrame(rows)


def _build_schedule_rows(schedule_payload_map, limit=30):
    rows = []
    for company_query, schedule_bundle in (schedule_payload_map or {}).items():
        for item in (schedule_bundle.get("events") or [])[:6]:
            rows.append(
                {
                    "公司": company_query,
                    "日期": item.get("event_date_text") or "-",
                    "剩餘天數": item.get("days_until"),
                    "類型": item.get("event_type") or "-",
                    "標題": item.get("title") or "-",
                    "來源": item.get("domain") or "-",
                }
            )
    return sorted(rows, key=lambda row: (row["日期"], row["公司"], row["類型"]))[:limit]


def _render_order_supply_chain_section(order_bundle, max_source_label):
    st.write("**台灣接單 / 供應鏈線索**")
    matched_companies = order_bundle.get("matched_companies") or []
    matched_themes = order_bundle.get("matched_themes") or []
    source_rows = order_bundle.get("sources") or []

    summary_cols = st.columns(3)
    summary_cols[0].metric("接單台廠", len(matched_companies))
    summary_cols[1].metric("線索來源", len(source_rows))
    summary_cols[2].metric("主題方向", len(matched_themes))

    if matched_themes:
        st.caption("接單線索最常對到的細分主題：" + "、".join(f"`{item}`" for item in matched_themes[:8]))

    if matched_companies:
        company_rows = []
        for item in matched_companies[:20]:
            company_rows.append(
                {
                    "代碼": item.get("code") or "-",
                    "名稱": item.get("name_zh") or "-",
                    "官方產業": item.get("industry") or "-",
                    "細分產業": "｜".join(item.get("themes") or []) or "未分類",
                    "命中別名": item.get("matched_alias") or "-",
                }
            )
        st.dataframe(pd.DataFrame(company_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("目前還沒有從這批英文搜尋結果抓到明確的台灣公司名稱。")

    if source_rows:
        st.write("**接單線索來源**")
        for source in source_rows[:max_source_label]:
            matched_label = "、".join(
                f"{item.get('name_zh')}({item.get('code')})"
                for item in (source.get("matched_companies") or [])[:5]
            ) or "未直接命中公司"
            with st.expander(f"{source['title']}｜{source['domain']}", expanded=False):
                st.caption(f"命中台廠：{matched_label}")
                if source.get("published_hint"):
                    st.caption(f"時間線索：{source['published_hint']}")
                if source.get("snippet"):
                    st.write(source["snippet"])
                if source.get("url"):
                    st.link_button("打開來源", source["url"], use_container_width=False)
    else:
        st.caption("目前還沒有抓到足夠的英文接單 / 供應鏈線索。")


def _render_schedule_section(schedule_bundle):
    st.write("**未來一個月法說會 / 發表會**")
    events = (schedule_bundle or {}).get("events") or []
    if not events:
        st.caption("目前還沒有從英文來源抓到未來一個月內可辨識的法說會或發表會日期。")
        return

    event_rows = [
        {
            "日期": item.get("event_date_text") or "-",
            "剩餘天數": item.get("days_until"),
            "類型": item.get("event_type") or "-",
            "標題": item.get("title") or "-",
            "來源": item.get("domain") or "-",
        }
        for item in events
    ]
    st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)

    for item in events[:6]:
        with st.expander(f"{item.get('event_date_text', '-')}｜{item.get('event_type', '-')}", expanded=False):
            st.write(item.get("title") or "-")
            if item.get("snippet"):
                st.caption(item["snippet"])
            if item.get("url"):
                st.link_button("打開來源", item["url"], use_container_width=False)


def _render_company_analysis_detail(company_query, bundle, analysis_result, order_bundle, schedule_bundle, max_source_label):
    summary_cols = st.columns(3)
    summary_cols[0].metric("抓到來源", len(bundle["sources"]))
    summary_cols[1].metric("可分析內容", "有" if bundle.get("combined_text") else "無")
    summary_cols[2].metric("AI 分析", get_llm_backend_label() or "關鍵字 fallback")

    if analysis_result:
        st.write("**AI 中文摘要**")
        st.info(analysis_result["summary_zh"])

        top_left, top_right = st.columns(2)
        with top_left:
            _render_keyword_block_table("瓶頸 / 受限關鍵字", analysis_result.get("bottleneck_keywords", []), "這批來源沒有明確提到瓶頸。")
        with top_right:
            _render_keyword_block_table("下一代方向關鍵字", analysis_result.get("next_generation_keywords", []), "這批來源沒有明確提到下一代方向。")

        mid_left, mid_right = st.columns(2)
        with mid_left:
            _render_keyword_block_table("Capex 關鍵字", analysis_result.get("capex_keywords", []), "這批來源沒有明確提到 Capex。")
        with mid_right:
            _render_keyword_block_table("需要的技術關鍵字", analysis_result.get("needed_technology_keywords", []), "這批來源沒有明確點出需要的技術。")

        _render_keyword_block_table("專有名詞 / 技術名詞", analysis_result.get("proper_terms", []), "這批來源沒有明確的專有名詞。")

        st.write("**台股供應鏈候選方向**")
        if analysis_result.get("overall_supply_chain"):
            st.markdown("、".join(f"`{item}`" for item in analysis_result["overall_supply_chain"]))
        else:
            st.caption("目前還整理不出明確的台股方向。")

        st.write("**研究結論**")
        st.success(analysis_result["research_takeaway"])

    st.write("**抓到的來源**")
    st.caption("這裡列的是系統實際抓回來的英文來源，AI 摘要就是從這些內容整理出來的。")
    for source in bundle["sources"][:max_source_label]:
        with st.expander(f"{source['title']}｜{source['domain']}", expanded=False):
            meta_df = pd.DataFrame(
                [
                    {"欄位": "來源類型", "內容": source.get("source_type") or "-"},
                    {"欄位": "時間線索", "內容": source.get("published_hint") or "-"},
                    {"欄位": "網址", "內容": source.get("url") or "-"},
                ]
            )
            st.dataframe(meta_df, use_container_width=True, hide_index=True)
            if source.get("snippet"):
                st.caption(source["snippet"])
            if source.get("extracted_text"):
                st.text_area(
                    "抓回的英文內容節錄",
                    value=source["extracted_text"][:3000],
                    height=220,
                    key=f"research_source_excerpt_{company_query}_{source['url']}",
                )

    _render_order_supply_chain_section(order_bundle or {}, max_source_label)
    _render_schedule_section(schedule_bundle)


def _render_web_earnings_call_analyzer():
    st.write("**自動抓法說 / 會議資料**")
    st.caption("現在可以一次追蹤多家公司。系統會先用英文搜尋，再自動抓回 transcript、investor relations、earnings coverage 內容，最後整理成中文研究摘要。")

    selected_companies = st.multiselect(
        "預設追蹤公司",
        DEFAULT_RESEARCH_COMPANIES,
        default=DEFAULT_RESEARCH_COMPANIES[:7],
        key="research_company_multiselect",
    )

    input_cols = st.columns([1.5, 0.7])
    custom_company_text = input_cols[0].text_area(
        "額外公司名 / Ticker",
        value=st.session_state.get("research_company_text", ""),
        placeholder="例如：Meta, Amazon, AVGO",
        height=90,
        key="research_company_text",
    )
    max_source_label = input_cols[1].selectbox(
        "來源檢視",
        [2, 3, 4],
        index=1,
        key="research_source_preview_count",
    )
    action_cols = st.columns([0.8, 0.8, 0.8, 0.8, 2.0])
    refresh_clicked = action_cols[0].button("執行日程", use_container_width=True, key="run_research_schedule")
    rerun_schedule = action_cols[1].button("重整日程", use_container_width=True, key="rerun_research_schedule")
    run_analysis_clicked = action_cols[2].button("執行AI", use_container_width=True, type="primary", key="run_research_ai")
    clear_research_ai = action_cols[3].button("清除結果", use_container_width=True, key="clear_research_ai")
    action_cols[4].caption("先跑日程，再決定要不要跑 AI 法說分析。")
    if clear_research_ai:
        st.session_state["research_schedule_job_id"] = None
        st.session_state["research_tracking_job_id"] = None
        st.session_state["research_excerpt_ai_job_id"] = None
        st.session_state["research_analysis_requested"] = False
        st.rerun()

    company_queries = _parse_tracking_companies(selected_companies, custom_company_text)
    if not company_queries:
        st.caption("先選幾家要追蹤的公司，下面才會開始抓法說或會議資料。")
        return

    if refresh_clicked:
        st.session_state["research_schedule_refresh_token"] = datetime.now().isoformat(timespec="seconds")
    schedule_refresh_token = st.session_state.get("research_schedule_refresh_token", datetime.now().strftime("%Y-%m-%d"))
    schedule_cache_key = (
        "research_schedule_v1",
        schedule_refresh_token,
        tuple(company_queries),
    )
    schedule_job_id, schedule_job = ensure_background_data_job(
        "research_schedule_job_id",
        "research_schedule",
        schedule_cache_key,
        _build_tracking_company_schedule_payload_map,
        args=(tuple(company_queries),),
        kwargs={"window_days": 30},
        running_message=f"正在整理 {len(company_queries)} 家公司的法說 / 發表會日程...",
        completed_message=f"{len(company_queries)} 家公司的日程已整理完成",
        failed_message="法說 / 發表會日程整理失敗",
        autostart=False,
        force_start=(refresh_clicked or rerun_schedule),
    )
    if schedule_job and schedule_job["status"] == "failed":
        failed_job = get_background_data_job_manager().get_job(schedule_job_id, include_result=False)
        st.error(f"讀取法說 / 發表會日程失敗：{failed_job.get('error') or '未知錯誤'}")
        return
    if not schedule_job:
        st.info("目前是手動模式。按上面的 `執行法說日程` 後，才會丟進背景 queue。")
        return
    if schedule_job["status"] != "completed":
        st.info("法說 / 發表會日程背景整理中，完成後會自動刷新。")
        render_background_data_job_status("research_schedule_job_id", "法說日程背景任務")
        return
    schedule_payload_map = get_background_data_job_manager().get_job(schedule_job_id, include_result=True).get("result") or {}
    schedule_rows = _build_schedule_rows(schedule_payload_map)
    st.write("**未來一個月法說會 / 發表會**")
    if schedule_rows:
        st.dataframe(pd.DataFrame(schedule_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("目前還抓不到未來一個月內可辨識的法說會或發表會日期。")

    schedule_summary_df = _build_schedule_overview_df(schedule_payload_map)
    if not schedule_summary_df.empty:
        st.write("**追蹤日程總覽**")
        st.dataframe(schedule_summary_df, use_container_width=True, hide_index=True)

    st.divider()
    st.write("**AI 法說分析**")
    st.caption("日程先顯示；只有你按下 `開始AI分析` 時，才會去抓法說來源、跑 AI 摘要與供應鏈分析。")

    analysis_requested = run_analysis_clicked or st.session_state.get("research_analysis_requested", False)
    if run_analysis_clicked:
        st.session_state["research_analysis_requested"] = True
        st.session_state["research_tracking_refresh_token"] = datetime.now().isoformat(timespec="seconds")

    if not analysis_requested:
        st.caption("目前尚未啟動 AI 法說分析。先看上面的法說 / 發表會日程，確認要追哪幾家後再按按鈕即可。")
        return

    refresh_token = st.session_state.get("research_tracking_refresh_token", datetime.now().strftime("%Y-%m-%d"))
    analysis_cache_key = ("research_tracking_v3", refresh_token, tuple(company_queries))
    analysis_job_id, analysis_job = ensure_background_data_job(
        "research_tracking_job_id",
        "research_tracking",
        analysis_cache_key,
        _build_tracking_company_payload_map,
        args=(tuple(company_queries),),
        running_message=f"正在分析 {len(company_queries)} 家公司的法說 / 會議資料...",
        completed_message=f"{len(company_queries)} 家公司的 AI 法說分析已整理完成",
        failed_message="AI 法說分析失敗",
        autostart=False,
        force_start=run_analysis_clicked,
    )
    if analysis_job and analysis_job["status"] == "failed":
        failed_job = get_background_data_job_manager().get_job(analysis_job_id, include_result=False)
        st.error(f"讀取 AI 法說分析失敗：{failed_job.get('error') or '未知錯誤'}")
        return
    if not analysis_job:
        st.caption("按 `開始AI分析` 後，才會把這批公司丟進背景 queue。")
        return
    if analysis_job["status"] != "completed":
        st.info("AI 法說分析背景執行中，完成後會自動刷新。")
        render_background_data_job_status("research_tracking_job_id", "AI法說分析背景任務")
        return

    payload_map = get_background_data_job_manager().get_job(analysis_job_id, include_result=True).get("result") or {}
    valid_payloads = {
        company_query: payload
        for company_query, payload in payload_map.items()
        if payload.get("bundle") and payload["bundle"].get("sources")
    }
    if not valid_payloads:
        st.warning("目前還抓不到可用的法說或會議來源，建議改用英文全名、ticker，或過一段時間再試。")
        return

    summary_df = pd.DataFrame([_extract_tracking_summary_row(company_query, payload) for company_query, payload in valid_payloads.items()])
    _render_tracking_overview_dashboard(summary_df, valid_payloads)
    st.write("**AI 分析總覽表**")
    st.caption("這張表會一起看法說重點、台灣接單 / 供應鏈線索，還有未來一個月內的法說會 / 發表會日期。")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    detail_company = st.selectbox("細看哪一家公司", list(valid_payloads.keys()), index=0, key="research_detail_company")
    selected_payload = valid_payloads[detail_company]
    st.write(f"**{detail_company} 詳細分析**")
    _render_company_analysis_detail(
        detail_company,
        selected_payload["bundle"],
        selected_payload.get("analysis"),
        selected_payload.get("order_bundle"),
        selected_payload.get("schedule_bundle"),
        max_source_label,
    )


def _render_transcript_paste_analyzer():
    st.write("**法說摘錄貼上分析**")
    st.caption("把英文法說片段貼進來後，AI 會直接抓關鍵字，並分成瓶頸、下一代、Capex、需要技術、專有名詞五類輸出。")

    transcript_input = st.text_area(
        "貼上英文逐字稿片段",
        value="",
        height=220,
        placeholder="Paste transcript excerpt here...",
        key="research_transcript_excerpt",
    )

    normalized_text = _normalize_transcript_text(transcript_input)
    analysis = _extract_transcript_analysis(normalized_text)
    if not normalized_text:
        st.caption("貼上法說片段後，這裡會顯示 AI 抓出的關鍵字分類與台股方向。")
        return

    ai_result = None
    if has_llm_backend():
        excerpt_cache_key = ("research_excerpt_ai_v1", normalized_text[:500], len(normalized_text), get_llm_backend_label())
        excerpt_action_cols = st.columns([0.8, 0.8, 2.4])
        run_excerpt_ai = excerpt_action_cols[0].button("執行片段AI", use_container_width=True, key="run_excerpt_ai")
        clear_excerpt_ai = excerpt_action_cols[1].button("清除片段結果", use_container_width=True, key="clear_excerpt_ai")
        if clear_excerpt_ai:
            st.session_state["research_excerpt_ai_job_id"] = None
            st.rerun()
        excerpt_job_id, excerpt_job = ensure_background_data_job(
            "research_excerpt_ai_job_id",
            "research_excerpt_ai",
            excerpt_cache_key,
            _analyze_transcript_excerpt_ai,
            args=(normalized_text,),
            running_message="正在分析貼上的法說片段...",
            completed_message="法說片段 AI 分析已完成",
            failed_message="法說片段 AI 分析失敗",
            autostart=False,
            force_start=run_excerpt_ai,
        )
        if excerpt_job and excerpt_job["status"] == "completed":
            ai_result = get_background_data_job_manager().get_job(excerpt_job_id, include_result=True).get("result")
        elif excerpt_job and excerpt_job["status"] in {"queued", "running"}:
            st.info("法說片段 AI 分析背景執行中，完成後會自動刷新。")
            render_background_data_job_status("research_excerpt_ai_job_id", "法說片段背景任務")
        elif excerpt_job and excerpt_job["status"] == "failed":
            st.warning("法說片段 AI 分析這次失敗，先退回關鍵字 fallback。")
        elif not excerpt_job:
            st.caption("按 `執行片段AI分析` 後，才會把這段文字丟進背景 queue。")

    if ai_result:
        st.write("**AI 中文摘要**")
        st.info(ai_result["summary_zh"])

        summary_cols = st.columns(3)
        summary_cols[0].metric("瓶頸關鍵字", len(ai_result["bottleneck_keywords"]))
        summary_cols[1].metric("下一代 / 技術詞", len(ai_result["next_generation_keywords"]) + len(ai_result["needed_technology_keywords"]))
        summary_cols[2].metric("Capex / 專有名詞", len(ai_result["capex_keywords"]) + len(ai_result["proper_terms"]))

        top_left, top_right = st.columns(2)
        with top_left:
            _render_keyword_block_table("瓶頸 / 受限關鍵字", ai_result["bottleneck_keywords"], "這段沒有明確提到瓶頸。")
        with top_right:
            _render_keyword_block_table("下一代方向關鍵字", ai_result["next_generation_keywords"], "這段沒有明確提到下一代方向。")

        mid_left, mid_right = st.columns(2)
        with mid_left:
            _render_keyword_block_table("Capex 關鍵字", ai_result["capex_keywords"], "這段沒有明確提到 Capex。")
        with mid_right:
            _render_keyword_block_table("需要的技術關鍵字", ai_result["needed_technology_keywords"], "這段沒有明確點出需要的技術。")

        _render_keyword_block_table("專有名詞 / 技術名詞", ai_result["proper_terms"], "這段沒有明確的專有名詞。")

        st.write("**台股供應鏈候選方向**")
        if ai_result["overall_supply_chain"]:
            st.markdown("、".join(f"`{item}`" for item in ai_result["overall_supply_chain"]))
        else:
            st.caption("目前還整理不出明確的台股方向。")

        st.write("**研究結論**")
        st.success(ai_result["research_takeaway"])
        return

    if not analysis:
        st.caption("目前這段內容還抓不到明顯的關鍵字或專有名詞。")
        return

    top_cols = st.columns(3)
    top_cols[0].metric("關鍵字群組", len(analysis["keyword_hits"]))
    top_cols[1].metric("專有名詞", len(analysis["matched_terms"]))
    top_cols[2].metric("台股方向", len(analysis["directions"]))

    st.warning("目前先用關鍵字 fallback 分析。若有啟用 OpenAI 或本地 Ollama，這裡會直接改成中文摘要版。")

    if analysis["directions"]:
        st.write("**優先聯想到的台股方向**")
        st.caption("先不要急著追原廠，先想哪個供應鏈最可能因為這段話受惠。")
        st.markdown("、".join(f"`{direction}`" for direction in analysis["directions"]))

    if analysis["keyword_hits"]:
        st.write("**關鍵字群組命中**")
        for hit in analysis["keyword_hits"]:
            with st.expander(f"{hit['group']}｜{', '.join(hit['keywords'])}", expanded=True):
                st.caption(hit["focus"])
                for line in hit["matched_lines"]:
                    st.markdown(f"- {line}")

    if analysis["matched_terms"]:
        st.write("**專有名詞命中**")
        term_df = pd.DataFrame(analysis["matched_terms"]).rename(
            columns={
                "term": "英文詞",
                "meaning": "意思",
                "why_it_matters": "代表什麼",
                "taiwan_link": "台股方向",
            }
        )
        st.dataframe(term_df, use_container_width=True, hide_index=True)


def render_research_transcript_tab():
    st.write("**AI 法說分析**")
    st.caption("這裡現在會先自動幫你上網抓法說或相關會議資料，再做英文內容整理與中文摘要。")
    _render_web_earnings_call_analyzer()

    with st.expander("手動貼上法說片段", expanded=False):
        st.caption("如果你之後手上有特定段落，也可以直接貼進來補充分析。")
        _render_transcript_paste_analyzer()

    with st.expander("英文搜尋輔助", expanded=False):
        st.caption("如果你還沒拿到法說內容，可以先用英文搜尋找 transcript。")

        shortcut_cols = st.columns(len(TRANSCRIPT_SHORTCUTS))
        for col, item in zip(shortcut_cols, TRANSCRIPT_SHORTCUTS):
            with col:
                st.write(f"**{item['label']}**")
                st.caption(item["symbol"])
                st.link_button("Transcript", item["transcript_url"], use_container_width=True)

        custom_symbol = st.text_input(
            "自訂美股代號",
            value="",
            placeholder="例如：AMZN、META、AVGO",
            key="research_custom_transcript_symbol",
        ).strip().upper()
        if custom_symbol:
            st.link_button(
                f"打開 {custom_symbol} Transcript",
                f"https://seekingalpha.com/symbol/{custom_symbol}/earnings/transcripts",
                use_container_width=False,
            )

        st.write("**英文搜尋關鍵字**")
        for group in TRANSCRIPT_KEYWORD_GROUPS:
            st.markdown(f"**{group['group']}**")
            st.code(" | ".join(group["keywords"]), language="text")
            st.caption(group["focus"])

        st.write("**搜尋句型範本**")
        search_samples = pd.DataFrame(
            [
                {"用途": "找缺貨 / 瓶頸", "英文搜尋句": "NVDA transcript bottleneck constrained lead time"},
                {"用途": "找下一代規格", "英文搜尋句": "MSFT transcript next generation roadmap transition"},
                {"用途": "找資本支出", "英文搜尋句": "TSM transcript capex buildout investment"},
                {"用途": "找傳輸升級", "英文搜尋句": "earnings transcript silicon photonics CPO retimer"},
                {"用途": "找散熱升級", "英文搜尋句": "earnings transcript liquid cooling TDP rack scale"},
                {"用途": "找供電升級", "英文搜尋句": "earnings transcript BBU power delivery HVDC"},
            ]
        )
        st.dataframe(search_samples, use_container_width=True, hide_index=True)

    with st.expander("專有名詞參考", expanded=False):
        st.caption("這裡不是讓你背字典，而是幫你快速判斷這個英文詞通常對應哪條台股方向。")
        glossary_df = pd.DataFrame(TERM_GLOSSARY).rename(
            columns={
                "term": "英文詞",
                "meaning": "意思",
                "why_it_matters": "法說看到它代表什麼",
                "taiwan_link": "優先聯想到的台股方向",
            }
        )
        st.dataframe(glossary_df, use_container_width=True, hide_index=True)

    with st.expander("台股供應鏈延伸查詢", expanded=False):
        st.caption("AI 抓到關鍵字後，再回台灣產業鏈平台往上中下游展開。")
        supply_cols = st.columns(2)
        with supply_cols[0]:
            st.link_button("打開櫃買中心產業價值鏈資訊平台", "https://ic.tpex.org.tw/", use_container_width=True)
        with supply_cols[1]:
            st.link_button("打開經濟部產業發展署", "https://www.ida.gov.tw/", use_container_width=True)

        theme_keyword = st.text_input(
            "供應鏈關鍵字提醒",
            value="光通訊、CPO、散熱、ABF、重電",
            key="research_value_chain_keywords",
        )
        st.caption(f"法說提到的關鍵字可以先記在這裡：{theme_keyword}")
