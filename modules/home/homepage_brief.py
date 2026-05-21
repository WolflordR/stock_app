from __future__ import annotations

import streamlit as st

from modules.industry.industry_taxonomy import TECH_INDUSTRY_NAMES


HOMEPAGE_BRIEF_STYLE = """
<style>
.home-summary-card {
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 0.9rem;
    padding: 0.9rem 1rem 1rem 1rem;
    background: rgba(15, 23, 42, 0.04);
    min-height: 7.6rem;
}
.home-summary-label {
    font-size: 0.92rem;
    color: #94a3b8;
    margin-bottom: 0.55rem;
    line-height: 1.25;
}
.home-summary-value {
    font-size: clamp(1.35rem, 2vw, 2.85rem);
    font-weight: 700;
    line-height: 1.05;
    letter-spacing: -0.02em;
    word-break: break-word;
    overflow-wrap: anywhere;
}
.home-brief-box {
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 1rem;
    padding: 1rem 1rem 0.9rem 1rem;
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.06), rgba(15, 23, 42, 0.02));
    margin-bottom: 1rem;
}
</style>
"""


def _extract_name_list(rank_df, limit=3):
    if rank_df is None or rank_df.empty:
        return []

    items = []
    for row in rank_df.head(limit).to_dict("records"):
        code = str(row.get("代碼") or "").strip()
        name = str(row.get("名稱") or "").strip()
        if code and name:
            items.append(f"{name}({code})")
        elif name:
            items.append(name)
        elif code:
            items.append(code)
    return items


def _sum_numeric_column(rank_df, column_name):
    if rank_df is None or rank_df.empty or column_name not in rank_df.columns:
        return 0.0
    return float(rank_df[column_name].fillna(0).sum())


def _safe_nested_dict(mapping, key):
    if not isinstance(mapping, dict):
        return {}
    value = mapping.get(key)
    return value if isinstance(value, dict) else {}


def _render_home_summary_card(label, value):
    st.markdown(
        f"""
        <div class="home-summary-card">
            <div class="home-summary-label">{label}</div>
            <div class="home-summary-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_market_brief(
    range_results,
    revenue_result,
    market_watch_result,
    daily_institutional,
    industry_bundle=None,
    active_etf_bundle=None,
):
    limit_up_count = int((market_watch_result or {}).get("limit_up_count") or 0)
    limit_down_count = int((market_watch_result or {}).get("limit_down_count") or 0)
    locked_up_count = int((market_watch_result or {}).get("locked_limit_up_count") or 0)
    locked_down_count = int((market_watch_result or {}).get("locked_limit_down_count") or 0)
    range_count = len(range_results or {})
    revenue_count = int((revenue_result or {}).get("screened_count") or 0)

    foreign_section = _safe_nested_dict(daily_institutional or {}, "foreign")
    foreign_buy_df = foreign_section.get("buy_rank_df")
    foreign_sell_df = foreign_section.get("sell_rank_df")
    foreign_buy_amount = _sum_numeric_column(foreign_buy_df, "估算資金(百萬元)")
    foreign_sell_amount = _sum_numeric_column(foreign_sell_df, "估算資金(百萬元)")
    foreign_bias_amount = foreign_buy_amount - foreign_sell_amount

    top_theme = "-"
    top_theme_ratio = None
    top_tech_themes = []
    if industry_bundle:
        top_theme = industry_bundle["summary"].get("top_theme") or "-"
        top_theme_ratio = industry_bundle["summary"].get("top_theme_volume_ratio")
        theme_summary_df = ((industry_bundle or {}).get("theme_report") or {}).get("summary_df")
        if theme_summary_df is not None and not theme_summary_df.empty:
            tech_theme_df = theme_summary_df[
                theme_summary_df["parent_industry"].isin(TECH_INDUSTRY_NAMES)
            ].copy()
            if not tech_theme_df.empty:
                top_tech_themes = (
                    tech_theme_df["group_name"]
                    .dropna()
                    .astype(str)
                    .tolist()[:2]
                )

    busiest_etf = "-"
    if active_etf_bundle:
        busiest_etf = active_etf_bundle.get("busiest_etf") or "-"

    positive_score = 0
    negative_score = 0
    if limit_up_count >= limit_down_count + 8:
        positive_score += 2
    elif limit_down_count >= limit_up_count + 8:
        negative_score += 2

    if locked_up_count >= locked_down_count + 3:
        positive_score += 1
    elif locked_down_count >= locked_up_count + 3:
        negative_score += 1

    if range_count >= 20:
        positive_score += 2
    elif range_count >= 8:
        positive_score += 1
    elif range_count <= 3 and limit_down_count > limit_up_count:
        negative_score += 1

    if revenue_count >= 30:
        positive_score += 1
    elif revenue_count <= 5 and limit_down_count > limit_up_count:
        negative_score += 1

    if foreign_bias_amount >= 1500:
        positive_score += 2
    elif foreign_bias_amount >= 300:
        positive_score += 1
    elif foreign_bias_amount <= -1500:
        negative_score += 2
    elif foreign_bias_amount <= -300:
        negative_score += 1

    if top_theme_ratio is not None and top_theme_ratio >= 1.5:
        positive_score += 1

    total_limit_count = limit_up_count + limit_down_count
    if negative_score >= 4:
        market_label = "空方壓力盤"
        summary_text = "跌停與鎖跌停壓力偏強，短線先把防守和現金彈性擺前面。"
        action_text = "先看抗跌股、減少追價，等賣壓收斂再擴大出手。"
    elif positive_score >= 5 and limit_up_count >= 20:
        market_label = "主流擴散盤"
        summary_text = "強勢股不只集中在少數權值，題材和量能有同步擴散的味道。"
        action_text = "優先跟著強主題和強股，不用急著猜高點，但要盯量能是否續強。"
    elif total_limit_count >= 18 and abs(limit_up_count - limit_down_count) <= 6:
        market_label = "高波動分歧盤"
        summary_text = "盤面同時有強攻與殺盤，代表資金在快速換股，不是單一路線。"
        action_text = "聚焦最強族群，少碰中間值，追蹤續強而不是全面撒網。"
    elif positive_score >= negative_score:
        market_label = "題材輪動盤"
        summary_text = "資金還在市場裡，但更偏向題材和族群間的輪動切換。"
        action_text = "先看量比放大的細分產業，再搭配法人與主動ETF方向挑標的。"
    else:
        market_label = "整理觀察盤"
        summary_text = "盤面暫時沒有形成明確主流，適合先觀察資金往哪一邊收斂。"
        action_text = "保持輕倉與耐心，等主流主題、量能和法人方向同步再積極。"

    strength_signals = []
    risk_signals = []
    focus_signals = []

    if top_theme != "-":
        theme_line = f"細分主題量能最強的是 {top_theme}"
        if top_theme_ratio is not None:
            theme_line += f"（量比 {top_theme_ratio:.2f}x）"
        strength_signals.append(theme_line)
    if top_tech_themes:
        focus_signals.append(f"科技量能主題：{'、'.join(top_tech_themes)}")

    if foreign_bias_amount != 0:
        direction = "偏多" if foreign_bias_amount > 0 else "偏空"
        strength_signals.append(f"外資前三十名估算資金合計 {direction} {abs(foreign_bias_amount):,.0f} 百萬元")

    if busiest_etf != "-":
        focus_signals.append(f"主動ETF最近換股最積極的是 {busiest_etf}")

    foreign_buy_names = _extract_name_list(foreign_buy_df, limit=3)
    if foreign_buy_names:
        focus_signals.append(f"外資買盤前線：{'、'.join(foreign_buy_names)}")

    if limit_up_count or limit_down_count:
        strength_signals.append(f"漲停 / 跌停家數：{limit_up_count} / {limit_down_count}")
    if locked_up_count or locked_down_count:
        focus_signals.append(f"鎖住漲跌停：{locked_up_count} / {locked_down_count}")
    if range_count:
        focus_signals.append(f"盤整吸籌掃描共 {range_count} 檔")
    if revenue_count:
        focus_signals.append(f"月營收動能條件股 {revenue_count} 檔")

    if limit_down_count > limit_up_count:
        risk_signals.append("跌停家數高於漲停家數，代表追價風險偏高")
    if locked_down_count > locked_up_count:
        risk_signals.append("鎖跌停多於鎖漲停，弱勢股賣壓還沒完全退")
    if range_count <= 3:
        risk_signals.append("盤整吸籌名單偏少，代表量先出來但還留在區間內的股票還不多")
    if revenue_count <= 5:
        risk_signals.append("基本面動能股不多，市場更像短線資金輪動")

    return {
        "market_label": market_label,
        "summary_text": summary_text,
        "action_text": action_text,
        "top_theme": top_theme,
        "top_tech_themes": top_tech_themes,
        "top_tech_theme_text": "｜".join(top_tech_themes) if top_tech_themes else "-",
        "busiest_etf": busiest_etf,
        "foreign_frontline": "、".join(foreign_buy_names) if foreign_buy_names else "-",
        "strength_signals": strength_signals[:4],
        "focus_signals": focus_signals[:5],
        "risk_signals": risk_signals[:4],
    }


def render_market_brief(
    range_results,
    revenue_result,
    market_watch_result,
    daily_institutional,
    industry_bundle=None,
    active_etf_bundle=None,
):
    market_brief = build_market_brief(
        range_results,
        revenue_result,
        market_watch_result,
        daily_institutional,
        industry_bundle=industry_bundle,
        active_etf_bundle=active_etf_bundle,
    )

    st.write("**今日市場定調**")
    st.markdown('<div class="home-brief-box">', unsafe_allow_html=True)
    st.caption("先用首頁資料把今天市場在演什麼濃縮成一句話，再往下看法人、量增、營收與漲跌停細節。")

    brief_metric_cols = st.columns(4)
    with brief_metric_cols[0]:
        _render_home_summary_card("今日盤型", market_brief["market_label"])
    with brief_metric_cols[1]:
        _render_home_summary_card("主流題材", market_brief["top_theme"])
    with brief_metric_cols[2]:
        _render_home_summary_card("科技雙主題", market_brief["top_tech_theme_text"])
    with brief_metric_cols[3]:
        _render_home_summary_card("外資前線", market_brief["foreign_frontline"])

    brief_left_col, brief_right_col = st.columns([1.2, 1.0])
    with brief_left_col:
        st.write(f"**一句話結論：{market_brief['summary_text']}**")
        st.caption(f"操作含義：{market_brief['action_text']}")
    with brief_right_col:
        if market_watch_result:
            st.caption(
                f"觀察資料日：{market_watch_result['used_date']}｜"
                f"若你看到這裡和其他分頁日期不同，通常是資料來源更新時間不同。"
            )

    detail_cols = st.columns(3)
    detail_sections = [
        ("偏強線索", market_brief["strength_signals"]),
        ("觀察焦點", market_brief["focus_signals"]),
        ("風險提醒", market_brief["risk_signals"] or ["目前沒有特別突出的風險警訊。"]),
    ]
    for column, (title, items) in zip(detail_cols, detail_sections):
        with column:
            st.write(f"**{title}**")
            for item in items:
                st.caption(f"- {item}")

    st.markdown("</div>", unsafe_allow_html=True)
    return market_brief
