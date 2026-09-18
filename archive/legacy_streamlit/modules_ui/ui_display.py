import pandas as pd
import streamlit as st


def render_reaction_metrics(reaction):
    if not reaction:
        return

    metric_items = [
        ("反應日", reaction.get("reaction_date") or "待確認", "1.45rem"),
        (
            "QQQ 單日反應",
            f"{reaction['one_day_pct']:.2f}%" if reaction.get("one_day_pct") is not None else "待確認",
            "2.15rem",
        ),
        (
            "QQQ 3日反應",
            f"{reaction['three_day_pct']:.2f}%" if reaction.get("three_day_pct") is not None else "待確認",
            "2.15rem",
        ),
    ]

    metric_cols = st.columns(3)
    for column, (label, value, value_font_size) in zip(metric_cols, metric_items):
        with column:
            st.markdown(
                f"""
                <div style="padding:0.2rem 0 0.4rem 0;">
                    <div style="font-size:0.92rem;color:#94a3b8;margin-bottom:0.25rem;">{label}</div>
                    <div style="font-size:{value_font_size};font-weight:700;line-height:1.12;word-break:break-word;overflow-wrap:anywhere;">
                        {value}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def format_company_link_badges(company_links):
    if not company_links:
        return "暫無直接對應公司"
    return " / ".join(
        f"{item['name_zh']}({item['code']}｜{item.get('industry') or '未分類'})"
        for item in company_links[:4]
    )


def render_rank_section(rank_df, caption_text, empty_text):
    st.caption(caption_text)
    display_df = rank_df if rank_df is not None else pd.DataFrame()
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    if display_df.empty:
        st.caption(empty_text)
