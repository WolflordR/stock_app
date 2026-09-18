from datetime import datetime, timedelta
from textwrap import dedent

import streamlit as st

from modules.data_sources.broker_branch_short_term import format_short_term_summary
from modules.data_sources.chip_data import get_recent_institutional_snapshots
from modules.data_sources.price_cache import get_price_cache_status
from modules.data_sources.stock_db import find_security, get_stock_name
from modules.stock_detail.page_helpers import (
    BROKER_BRANCH_CACHE_VERSION,
    TODAY_CHIP_CACHE_VERSION,
    format_close_text,
    format_lots_text,
    format_net_lots_metric,
    format_pct_text,
    format_price_text,
    format_profit_k_text,
    format_ratio_text,
    format_signed_lots_text,
    latest_market_date_key,
    load_broker_branch_summary,
    load_broker_branch_trace,
    load_short_term_broker_report_window,
    load_today_chip_snapshot,
    row_value,
)
from modules.ui.ui_stock_charts import render_streamlit_lightweight_chart


def _inject_stock_detail_css():
    st.html("""
        <style>
        .stock-today-hero {
            display:grid;
            grid-template-columns: minmax(260px, 0.95fr) minmax(260px, 0.95fr);
            gap: 18px;
            margin: 0.35rem 0 1rem 0;
        }
        .stock-today-topline {
            display:grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin: 0.35rem 0 1rem 0;
        }
        .stock-today-top-card {
            border:1px solid rgba(137,157,179,0.18);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(17,27,39,0.94), rgba(13,21,31,0.96));
            padding: 1rem 1.15rem;
            box-shadow: 0 8px 24px rgba(0,0,0,0.20);
        }
        .stock-today-top-label {
            color:#8fa3b8;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-today-top-value {
            color:#eef5fb;
            font-size:2.2rem;
            font-weight:900;
            margin-top:0.4rem;
            line-height:1.05;
        }
        .stock-today-top-value.is-bull { color: #df6f7b; }
        .stock-today-top-value.is-bear { color: #63c796; }
        .stock-today-top-note {
            color:#8fa3b8;
            margin-top:0.3rem;
            font-size:0.88rem;
            font-weight:700;
        }
        .stock-today-main {
            border:1px solid rgba(137,157,179,0.18);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(17,27,39,0.96), rgba(13,21,31,0.98));
            padding: 1.35rem 1.5rem;
            box-shadow: 0 18px 45px rgba(0,0,0,0.24);
        }
        .stock-today-kicker {
            color: #8fa3b8;
            font-size: 0.95rem;
            font-weight: 700;
        }
        .stock-today-value {
            margin-top: 0.42rem;
            font-size: 3rem;
            font-weight: 900;
            line-height: 1;
            color: #eef5fb;
        }
        .stock-today-value.is-bull { color: #df6f7b; }
        .stock-today-value.is-bear { color: #63c796; }
        .stock-today-value.is-neutral { color: #eef5fb; }
        .stock-today-sub {
            margin-top: 0.55rem;
            color: #dbe7f3;
            font-size: 1rem;
            line-height: 1.45;
        }
        .stock-today-grid {
            display:grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin: 0.8rem 0 1rem 0;
        }
        .stock-today-mini {
            border:1px solid rgba(137,157,179,0.18);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(17,27,39,0.94), rgba(13,21,31,0.96));
            padding: 1rem 1.1rem;
            box-shadow: 0 8px 24px rgba(0,0,0,0.20);
        }
        .stock-today-mini-label {
            color:#8fa3b8;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-today-mini-value {
            color:#eef5fb;
            font-size:1.7rem;
            font-weight:900;
            margin-top:0.35rem;
            line-height:1.05;
        }
        .stock-today-mini-note {
            color:#8fa3b8;
            margin-top:0.3rem;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-today-alert-grid {
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin: 0.65rem 0 1rem 0;
        }
        .stock-today-alert {
            border-radius: 8px;
            padding: 0.95rem 1.1rem;
            border: 1px solid rgba(211, 166, 79, 0.22);
            background: linear-gradient(135deg, rgba(75,61,30,0.24), rgba(27,30,32,0.20));
            color: #e8c878;
            font-weight: 700;
        }
        .stock-today-alert.is-danger {
            border-color: rgba(223,111,123,0.24);
            background: linear-gradient(135deg, rgba(77,30,40,0.30), rgba(41,24,31,0.20));
            color: #f2a2a9;
        }
        .stock-today-alert.is-good {
            border-color: rgba(99,199,150,0.24);
            background: linear-gradient(135deg, rgba(30,83,62,0.26), rgba(22,45,40,0.20));
            color: #9be0bd;
        }
        .stock-short-term-hero {
            display:grid;
            grid-template-columns: minmax(240px, 0.95fr) minmax(320px, 1.05fr);
            gap: 18px;
            margin: 0.4rem 0 1rem 0;
        }
        .stock-short-term-main {
            border:1px solid rgba(137,157,179,0.18);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(17,27,39,0.96), rgba(13,21,31,0.98));
            padding: 1.35rem 1.5rem;
            box-shadow: 0 18px 45px rgba(0,0,0,0.24);
        }
        .stock-short-term-kicker {
            color: #8fa3b8;
            font-size: 0.95rem;
            font-weight: 700;
        }
        .stock-short-term-signal {
            margin-top: 0.4rem;
            font-size: 3.4rem;
            font-weight: 900;
            line-height: 1;
            color: #eef5fb;
        }
        .stock-short-term-signal.is-bull { color: #df6f7b; }
        .stock-short-term-signal.is-bear { color: #63c796; }
        .stock-short-term-signal.is-neutral { color: #eef5fb; }
        .stock-short-term-reason {
            margin-top: 0.65rem;
            color: #dbe7f3;
            font-size: 1rem;
        }
        .stock-short-term-grid {
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
        }
        .stock-short-term-mini {
            border:1px solid rgba(137,157,179,0.18);
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(17,27,39,0.94), rgba(13,21,31,0.96));
            padding: 1rem 1.1rem;
            box-shadow: 0 8px 24px rgba(0,0,0,0.20);
        }
        .stock-short-term-mini-label {
            color:#8fa3b8;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-short-term-mini-value {
            color:#eef5fb;
            font-size:1.85rem;
            font-weight:900;
            margin-top:0.35rem;
            line-height:1.05;
        }
        .stock-short-term-alert {
            border-radius: 8px;
            padding: 0.95rem 1.15rem;
            margin: 0.7rem 0;
            border: 1px solid rgba(211,166,79,0.22);
            background: linear-gradient(135deg, rgba(75,61,30,0.24), rgba(27,30,32,0.20));
            color: #e8c878;
            font-weight: 700;
        }
        .stock-short-term-alert.is-danger {
            border-color: rgba(223,111,123,0.24);
            background: linear-gradient(135deg, rgba(77,30,40,0.30), rgba(41,24,31,0.20));
            color: #f2a2a9;
        }
        .stock-short-term-rank-grid {
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 18px;
            margin-top: 1rem;
        }
        .stock-short-term-rank-panel {
            border:1px solid rgba(137,157,179,0.18);
            border-radius: 8px;
            overflow: hidden;
            background: rgba(17,27,39,0.86);
            box-shadow: 0 8px 24px rgba(0,0,0,0.20);
        }
        .stock-short-term-rank-head {
            padding: 1rem 1.2rem;
            font-size: 1.45rem;
            font-weight: 900;
            border-bottom: 1px solid rgba(137,157,179,0.16);
        }
        .stock-short-term-rank-head.is-buy {
            color: #f2a2a9;
            background: linear-gradient(135deg, rgba(77,30,40,0.62), rgba(32,27,34,0.84));
        }
        .stock-short-term-rank-head.is-sell {
            color: #9be0bd;
            background: linear-gradient(135deg, rgba(30,83,62,0.58), rgba(23,43,40,0.84));
        }
        .stock-short-term-rank-row {
            display:grid;
            grid-template-columns: 120px minmax(180px, 1.2fr) minmax(180px, 0.95fr);
            gap: 16px;
            align-items:center;
            padding: 1.05rem 1.2rem;
            border-top: 1px solid rgba(137,157,179,0.12);
        }
        .stock-short-term-rank-row:first-child {
            border-top: none;
        }
        .stock-short-term-rank-left {
            display:flex;
            flex-direction:column;
            gap: 0.12rem;
        }
        .stock-short-term-rank-weight {
            color:#eef5fb;
            font-size: 1.15rem;
            font-weight: 900;
        }
        .stock-short-term-rank-net {
            color:#dbe7f3;
            font-size: 0.9rem;
            font-weight: 700;
        }
        .stock-short-term-rank-center {
            min-width: 0;
        }
        .stock-short-term-rank-branch {
            color:#eef5fb;
            font-size: 1.25rem;
            font-weight: 900;
            line-height: 1.15;
            word-break: break-word;
        }
        .stock-short-term-rank-tagline {
            color:#8fa3b8;
            margin-top: 0.3rem;
            font-size: 0.96rem;
            word-break: break-word;
        }
        .stock-short-term-rank-right {
            display:flex;
            flex-direction:column;
            gap: 0.18rem;
            text-align:right;
        }
        .stock-short-term-rank-price {
            color:#eef5fb;
            font-size: 1rem;
            font-weight: 800;
        }
        .stock-short-term-rank-profit {
            font-size: 1.3rem;
            font-weight: 900;
        }
        .stock-short-term-rank-profit.is-buy { color:#df6f7b; }
        .stock-short-term-rank-profit.is-sell { color:#63c796; }
        .stock-short-term-rank-note {
            color:#8fa3b8;
            font-size: 0.92rem;
            font-weight: 700;
        }
        .stock-short-term-rank-caption {
            color:#dbe7f3;
            font-size: 0.98rem;
            margin-top: 0.8rem;
        }
        @media (max-width: 900px) {
            .stock-today-topline {
                grid-template-columns: 1fr;
            }
            .stock-today-hero {
                grid-template-columns: 1fr;
            }
            .stock-today-grid {
                grid-template-columns: 1fr 1fr;
            }
            .stock-today-alert-grid {
                grid-template-columns: 1fr;
            }
            .stock-short-term-hero {
                grid-template-columns: 1fr;
            }
            .stock-short-term-grid {
                grid-template-columns: 1fr 1fr;
            }
            .stock-short-term-signal {
                font-size: 2.8rem;
            }
            .stock-short-term-rank-grid {
                grid-template-columns: 1fr;
            }
            .stock-short-term-rank-row {
                grid-template-columns: 1fr;
                gap: 0.7rem;
            }
            .stock-short-term-rank-right {
                text-align:left;
            }
        }
        </style>
        """)


def _render_today_chip_section(stock_code: str, symbol: str, end_date):
    st.markdown("### 今日籌碼")
    _inject_stock_detail_css()

    try:
        payload = load_today_chip_snapshot(stock_code, symbol, end_date, TODAY_CHIP_CACHE_VERSION)
    except Exception as exc:
        st.warning(f"目前抓不到今日籌碼資料：{exc}")
        return

    quote_warning = payload.get("quote_warning")
    report_error = payload.get("report_error")
    report_deferred = bool(payload.get("report_deferred"))

    report = payload.get("short_term_report") or {}
    summary = report.get("summary") or {}
    summary_text = format_short_term_summary(report)
    signal_label = summary_text["主力動向"]
    signal_class = "is-neutral"
    if signal_label in {"大買", "偏多集中"}:
        signal_class = "is-bull"
    elif signal_label in {"大賣", "偏空集中"}:
        signal_class = "is-bear"

    price_state_label, price_state_reason = payload.get("price_volume_state") or ("量價中性", "目前沒有特別明顯的價量偏態。")
    state_class = "is-neutral"
    if price_state_label in {"放量上攻", "量縮墊高"}:
        state_class = "is-bull"
    elif price_state_label in {"放量下殺", "量縮回檔"}:
        state_class = "is-bear"

    history_row = payload.get("history_row") or {}
    close_text = format_close_text(row_value(history_row, "close", "Close"))
    change_pct_text = format_pct_text(payload.get("change_pct"))
    display_volume_lots = payload.get("official_volume_lots")
    if display_volume_lots is None:
        fallback_volume = row_value(history_row, "volume", "Volume")
        display_volume_lots = (fallback_volume or 0.0) / 1000.0 if fallback_volume is not None else None
    volume_text = format_lots_text(display_volume_lots)
    summary_text["成交量"] = volume_text
    volume_growth_text = format_ratio_text(payload.get("volume_ratio_prev_day"))
    top_close_class = "is-neutral"
    change_pct_value = payload.get("change_pct")
    if change_pct_value is not None:
        if change_pct_value > 0:
            top_close_class = "is-bull"
        elif change_pct_value < 0:
            top_close_class = "is-bear"
    top_line_html = dedent(
        f"""
        <div class="stock-today-topline">
            <div class="stock-today-top-card">
                <div class="stock-today-top-label">收盤價</div>
                <div class="stock-today-top-value {top_close_class}">{close_text}</div>
                <div class="stock-today-top-note">資料日 {history_row.get("trade_date") or report.get("trade_date") or '-'}</div>
            </div>
            <div class="stock-today-top-card">
                <div class="stock-today-top-label">漲跌幅</div>
                <div class="stock-today-top-value {top_close_class}">{change_pct_text}</div>
                <div class="stock-today-top-note">相對前一交易日</div>
            </div>
            <div class="stock-today-top-card">
                <div class="stock-today-top-label">成交量</div>
                <div class="stock-today-top-value">{volume_text}</div>
                <div class="stock-today-top-note">量增幅 {volume_growth_text}</div>
            </div>
        </div>
        """
    ).strip()
    st.html(top_line_html)
    hero_html = dedent(
        f"""
        <div class="stock-today-hero">
            <div class="stock-today-main">
                <div class="stock-today-kicker">主力動向</div>
                <div class="stock-today-value {signal_class}">{signal_label}</div>
                <div class="stock-today-sub">{summary.get("signal_reason") or "以前15大買超與賣超分點的差額，搭配籌碼集中度來判斷主力動向。"} </div>
            </div>
            <div class="stock-today-main">
                <div class="stock-today-kicker">今日價量</div>
                <div class="stock-today-value {state_class}">{price_state_label}</div>
                <div class="stock-today-sub">收盤 {close_text}｜漲跌幅 {change_pct_text}｜成交量 {volume_text}｜量增幅 {volume_growth_text}<br>{price_state_reason}</div>
            </div>
        </div>
        """
    ).strip()
    st.html(hero_html)

    today_grid_html = dedent(
        f"""
        <div class="stock-today-grid">
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">籌碼集中</div>
                <div class="stock-today-mini-value">{summary_text["籌碼集中"]}</div>
                <div class="stock-today-mini-note">前15大買超分點合計－前15大賣超分點合計</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">籌碼集中度</div>
                <div class="stock-today-mini-value">{summary_text["籌碼集中度"]}</div>
                <div class="stock-today-mini-note">籌碼集中 ÷ 區間總成交張數</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">成交量</div>
                <div class="stock-today-mini-value">{summary_text["成交量"]}</div>
                <div class="stock-today-mini-note">資料日 {history_row.get("trade_date") or report.get("trade_date") or '-'}</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">成交量增幅</div>
                <div class="stock-today-mini-value">{format_ratio_text(payload.get("volume_ratio_prev_day"))}</div>
                <div class="stock-today-mini-note">相對前一日成交量</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">區間週轉率</div>
                <div class="stock-today-mini-value">{summary_text["區間週轉率"]}</div>
                <div class="stock-today-mini-note">區間總成交量 ÷ 公司發行總股本</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">估股本比重</div>
                <div class="stock-today-mini-value">{summary_text["估股本比重"]}</div>
                <div class="stock-today-mini-note">籌碼集中 ÷ 公司發行總股本</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">分點集中張數</div>
                <div class="stock-today-mini-value">{format_lots_text(summary.get("concentration_lots"))}</div>
                <div class="stock-today-mini-note">與籌碼集中同步，方便對照主力吸納規模</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">分點集中度</div>
                <div class="stock-today-mini-value">{format_pct_text(max(summary.get("buy_top5_pct") or 0.0, summary.get("sell_top5_pct") or 0.0))}</div>
                <div class="stock-today-mini-note">前五大分點相對成交量占比</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">短衝買超占比</div>
                <div class="stock-today-mini-value">{summary_text["短衝買超占比"]}</div>
                <div class="stock-today-mini-note">已知短衝 / 隔日沖分點買超占量</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">短衝賣超占比</div>
                <div class="stock-today-mini-value">{summary_text["短衝賣超占比"]}</div>
                <div class="stock-today-mini-note">已知短衝 / 隔日沖分點賣超占量</div>
            </div>
        </div>
        """
    ).strip()
    st.html(today_grid_html)

    if quote_warning:
        st.info(f"今日總量補值逾時，先用一般盤日行情顯示：{quote_warning}")
    if report_deferred:
        st.caption("第一屏先顯示價量與法人摘要；分點榜與短衝分析會在後面的分頁再載入。")
    if report_error:
        st.warning(f"分點資料暫時退回簡化模式：{report_error}")

    institutional = payload.get("institutional_detail") or {}
    institution_cols = st.columns(4)
    institution_cols[0].metric("外資", format_net_lots_metric(institutional.get("foreign_net")))
    institution_cols[1].metric("投信", format_net_lots_metric(institutional.get("trust_net")))
    institution_cols[2].metric("自營商", format_net_lots_metric(institutional.get("dealer_net")))
    institution_cols[3].metric("三大法人", format_net_lots_metric(institutional.get("total_net")))

    alerts = list(report.get("alerts") or [])
    if price_state_label == "放量上攻":
        alerts.insert(0, "提醒：今天屬於放量上攻，若同時短衝買超占比高，隔日沖接力與倒貨都要留意。")
    elif price_state_label == "放量下殺":
        alerts.insert(0, "提醒：今天屬於放量下殺，若賣方短衝席次偏多，短線壓力通常不小。")
    elif price_state_label == "量縮整理":
        alerts.insert(0, "提醒：今天量縮整理，先觀察主力席次是否開始集中，通常比追價更重要。")
    if institutional.get("trust_net") and institutional["trust_net"] > 0:
        alerts.append("加分：投信當日偏買，若分點也同步集中，後續續強機率會更高。")
    if institutional.get("foreign_net") and institutional["foreign_net"] < 0 and (summary.get("short_term_sell_pct") or 0) >= 8:
        alerts.append("提醒：外資偏賣且短衝席次賣超偏高，短線隔日沖壓力提高。")

    if alerts:
        alert_boxes = []
        for alert in alerts[:4]:
            variant = "is-danger" if ("壓力" in alert or "賣超" in alert or "下殺" in alert) else "is-good" if ("加分" in alert or "上攻" in alert) else ""
            alert_boxes.append(f"<div class='stock-today-alert {variant}'>{alert}</div>")
        st.html(f"<div class='stock-today-alert-grid'>{''.join(alert_boxes)}</div>")


def _render_short_term_broker_section(stock_code: str):
    st.markdown("### 短衝主力 / 分點日報")
    _inject_stock_detail_css()
    trade_date_key = latest_market_date_key()

    days_window = st.segmented_control(
        "統計天數",
        options=[1, 3, 5, 10, 20],
        default=1,
        key=f"short_term_days_{stock_code}",
        format_func=lambda value: f"近 {value} 日",
    )

    try:
        report = load_short_term_broker_report_window(
            stock_code,
            int(days_window or 1),
            trade_date_key,
            BROKER_BRANCH_CACHE_VERSION,
        )
    except Exception as exc:
        st.warning(f"目前抓不到短衝主力分點資料：{exc}")
        return

    summary = report.get("summary") or {}
    summary_text = format_short_term_summary(report)
    signal_label = summary_text["主力動向"]
    signal_class = "is-neutral"
    if signal_label in {"大買", "偏多集中"}:
        signal_class = "is-bull"
    elif signal_label in {"大賣", "偏空集中"}:
        signal_class = "is-bear"

    concentration_lots = summary.get("concentration_lots") or 0.0
    concentration_pct = summary.get("concentration_pct") or 0.0
    short_term_net_lots = (summary.get("short_term_buy_lots") or 0.0) - (summary.get("short_term_sell_lots") or 0.0)
    short_term_seats = int(summary.get("short_term_buy_count") or 0) + int(summary.get("short_term_sell_count") or 0)

    reason = summary.get("signal_reason")
    hero_html = dedent(
        f"""
        <div class="stock-short-term-hero">
            <div class="stock-short-term-main">
                <div class="stock-short-term-kicker">近 {report.get('days_window') or 1} 日主力動向</div>
                <div class="stock-short-term-signal {signal_class}">{signal_label}</div>
                <div class="stock-short-term-reason">{reason or "目前買賣力道接近，先觀察分點集中度。"}</div>
            </div>
            <div class="stock-short-term-grid">
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">籌碼集中</div>
                    <div class="stock-short-term-mini-value">{format_lots_text(concentration_lots)}</div>
                </div>
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">籌碼集中度</div>
                    <div class="stock-short-term-mini-value">{format_pct_text(concentration_pct)}</div>
                </div>
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">估股本比重</div>
                    <div class="stock-short-term-mini-value">{summary_text["估股本比重"]}</div>
                </div>
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">區間週轉率</div>
                    <div class="stock-short-term-mini-value">{summary_text["區間週轉率"]}</div>
                </div>
            </div>
        </div>
        """
    ).strip()
    st.html(hero_html)

    quick_metrics = st.columns(3)
    quick_metrics[0].metric("成交量", summary_text["成交量"])
    quick_metrics[1].metric("短衝席次", short_term_seats)
    quick_metrics[2].metric("短衝淨差", format_lots_text(short_term_net_lots))

    if report.get("history_mode") == "current_snapshot_only" and (report.get("days_window") or 1) > 1:
        st.info("目前分點來源改為 Yahoo 當日榜單。近 3 / 5 / 10 / 20 日先沿用當日主力榜做觀察，單一分點歷史之後再接官方快照。")

    alerts = report.get("alerts") or []
    if not alerts:
        st.html(
            "<div class='stock-short-term-alert'>提醒：目前沒有明顯短衝席次異常，但仍可持續觀察買賣榜是否由固定分點反覆進出。</div>"
        )
    else:
        for alert in alerts:
            danger = " is-danger" if ("賣超" in alert or "偏空" in (reason or "")) else ""
            st.html(f"<div class='stock-short-term-alert{danger}'>{alert}</div>")

    meta_cols = st.columns([1.2, 1.0, 1.0, 1.2])
    meta_cols[0].metric("股票", report.get("stock_title") or stock_code)
    meta_cols[1].metric("短衝買方席次", int(summary.get("short_term_buy_count") or 0))
    meta_cols[2].metric("短衝賣方席次", int(summary.get("short_term_sell_count") or 0))
    source_url = report.get("source_url") or ""
    if source_url:
        meta_cols[3].link_button("查看來源頁", source_url)
    else:
        meta_cols[3].metric("來源", report.get("source_label") or "官方匯入資料")
    source_label = report.get("source_label") or "分點榜來源"
    st.caption(f"目前分點來源：{source_label}")
    is_yahoo_fallback = "Yahoo" in source_label

    buy_rows = report.get("buy_rows") or []
    sell_rows = report.get("sell_rows") or []

    def _render_rank_panel(rows, *, title: str, variant: str, caption: str):
        panel_rows = []
        for row in rows[:15]:
            tag_labels = [tag for tag in row.get("tag_labels") or [] if tag]
            group_labels = [group for group in row.get("group_labels") or [] if group]
            tag_pieces = tag_labels + [group for group in group_labels if group not in tag_labels]
            if row.get("active_days"):
                tag_pieces.append(f"近{report.get('days_window') or 1}日活躍 {int(row['active_days'])} 天")
            tag_line = " / ".join(tag_pieces) if tag_pieces else "一般分點"
            right_lines = []
            if not is_yahoo_fallback and row.get("avg_price_value") is not None:
                right_lines.append(
                    f'<div class="stock-short-term-rank-price">均價 {format_price_text(row.get("avg_price_value"))}</div>'
                )
            if not is_yahoo_fallback and row.get("total_profit_k_value") is not None:
                right_lines.append(
                    f'<div class="stock-short-term-rank-profit {variant}">損益 {format_profit_k_text(row.get("total_profit_k_value"))} 萬</div>'
                )
            right_lines.append(
                f'<div class="stock-short-term-rank-note">買進 {row.get("buy_shares") or "-"} ｜ 賣出 {row.get("sell_shares") or "-"}</div>'
            )
            panel_rows.append(
                dedent(
                    f"""
                    <div class="stock-short-term-rank-row">
                        <div class="stock-short-term-rank-left">
                            <div class="stock-short-term-rank-weight">{format_pct_text(row.get('weight_pct'))}</div>
                            <div class="stock-short-term-rank-net">{format_signed_lots_text(row.get('net_lots_value'))}</div>
                        </div>
                        <div class="stock-short-term-rank-center">
                            <div class="stock-short-term-rank-branch">{row.get('broker_branch') or '-'}</div>
                            <div class="stock-short-term-rank-tagline">{tag_line}</div>
                        </div>
                        <div class="stock-short-term-rank-right">
                            {''.join(right_lines)}
                        </div>
                    </div>
                    """
                ).strip()
            )
        rows_html = "".join(panel_rows) or "<div class='stock-short-term-rank-row'><div class='stock-short-term-rank-center'><div class='stock-short-term-rank-branch'>目前沒有資料</div></div></div>"
        return dedent(
            f"""
            <div>
                <div class="stock-short-term-rank-panel">
                    <div class="stock-short-term-rank-head {variant}">{title}</div>
                    {rows_html}
                </div>
                <div class="stock-short-term-rank-caption">{caption}</div>
            </div>
            """
        ).strip()

    panels_html = dedent(
        f"""
        <div class="stock-short-term-rank-grid">
            {_render_rank_panel(buy_rows, title='買方 Top15', variant='is-buy', caption='先看哪些分點真的在抬轎，是否有已知短衝席次集中進場。')}
            {_render_rank_panel(sell_rows, title='賣方 Top15', variant='is-sell', caption='再看誰在倒貨，若短衝分點同時出現在賣方前排，隔日沖壓力通常更大。')}
        </div>
        """
    ).strip()
    st.html(panels_html)


def _render_broker_branch_section(stock_code: str):
    st.markdown("### 券商分點明細")
    trade_date_key = latest_market_date_key()

    try:
        summary_bundle = load_broker_branch_summary(stock_code, trade_date_key, BROKER_BRANCH_CACHE_VERSION)
    except Exception as exc:
        st.warning(f"目前抓不到券商分點資料：{exc}")
        return

    buy_rows = summary_bundle.get("buy_side") or []
    sell_rows = summary_bundle.get("sell_side") or []
    if not buy_rows and not sell_rows:
        st.info("目前沒有可顯示的分點資料。")
        return

    header_cols = st.columns([1.2, 1.0, 1.0, 1.2])
    header_cols[0].metric("股票", summary_bundle.get("stock_title") or summary_bundle.get("stock_code") or stock_code)
    header_cols[1].metric("買超分點數", len(buy_rows))
    header_cols[2].metric("賣超分點數", len(sell_rows))
    source_url = summary_bundle.get("source_url") or ""
    if source_url:
        header_cols[3].link_button("查看來源頁", source_url)
    else:
        header_cols[3].metric("來源", summary_bundle.get("source_label") or "官方匯入資料")
    st.caption(f"目前分點來源：{summary_bundle.get('source_label') or '分點榜來源'}")

    def _compact_branch_table(rows):
        return [
            {
                "分點": row.broker_branch,
                "買賣超(張)": row.net_shares,
                "買張": row.buy_shares,
                "賣張": row.sell_shares,
            }
            for row in rows
        ]

    table_cols = st.columns(2)
    with table_cols[0]:
        st.markdown("**買超分點排行**")
        st.dataframe(
            _compact_branch_table(buy_rows),
            use_container_width=True,
            hide_index=True,
        )
    with table_cols[1]:
        st.markdown("**賣超分點排行**")
        st.dataframe(
            _compact_branch_table(sell_rows),
            use_container_width=True,
            hide_index=True,
        )
    if "Yahoo" in str(summary_bundle.get("source_label") or ""):
        st.info("目前 Yahoo 來源只提供當日買賣分點榜，單一分點歷史明細、均價與損益暫時不提供。")
    else:
        st.info("目前顯示的是官方匯入分點日報；如果你補匯更多交易日，後面可以直接擴充成多日分點統計。")


def render_stock_detail_page(state):
    default_start = st.session_state.get("stock_detail_start_date", datetime.now().date() - timedelta(days=365))
    default_end = st.session_state.get("stock_detail_end_date", datetime.now().date())

    stock_input = st.text_input(
        "股票代碼 / yfinance symbol",
        value=st.session_state.get("stock_detail_input", "2330"),
        key="stock_detail_input",
        help="可輸入 2330、2330.TW 或其他已在主檔中的 symbol。",
    ).strip()

    if not stock_input:
        st.info("先輸入股票代碼，就會載入個股圖表。")
        return

    security = find_security(stock_input)
    if security:
        symbol = security["yfinance_symbol"]
        stock_title = f"{security['name_zh']} ({symbol})"
        market_text = security.get("market") or "-"
    else:
        normalized = stock_input.upper()
        symbol = normalized if "." in normalized else f"{normalized}.TW"
        stock_title = f"{get_stock_name(normalized)} ({symbol})"
        market_text = "未辨識"

    cache_status = get_price_cache_status(symbol)
    display_code = security["code"] if security else stock_input.split(".")[0]

    st.markdown(f"## {get_stock_name(display_code)} ({display_code})")
    meta_cols = st.columns(3)
    meta_cols[0].metric("市場", market_text)
    meta_cols[1].metric("快取筆數", f"{int(cache_status.get('row_count') or 0):,}")
    meta_cols[2].metric("快取最新日", cache_status.get("last_cached_date") or "尚未建立")

    if cache_status.get("fetch_status") == "failed":
        st.warning(f"最近一次補抓資料失敗：{cache_status.get('last_error')}")
    elif cache_status.get("last_checked_date"):
        st.caption(
            f"快取檢查到 {cache_status['last_checked_date']}，資料來源 {cache_status.get('source') or 'yfinance'}。"
        )

    stock_code = display_code
    selected_section = st.segmented_control(
        "個股詳頁分頁",
        options=["今日籌碼", "技術線圖", "短衝主力", "分點明細"],
        default="今日籌碼",
        key="stock_detail_section",
        label_visibility="collapsed",
    )

    if selected_section == "今日籌碼":
        _render_today_chip_section(stock_code, symbol, default_end)
    elif selected_section == "技術線圖":
        chart_cols = st.columns([0.9, 0.9, 1.2])
        start_date = chart_cols[0].date_input(
            "開始日",
            value=default_start,
            key="stock_detail_start_date",
        )
        end_date = chart_cols[1].date_input(
            "結束日",
            value=default_end,
            key="stock_detail_end_date",
        )
        interval_label = chart_cols[2].segmented_control(
            "週期",
            ["1m", "5m", "1h", "1d"],
            default=st.session_state.get("stock_detail_chart_interval", "1d"),
            key="stock_detail_chart_interval",
        )
        with st.expander("圖表指標", expanded=False):
            indicator_cols = st.columns(2)
            visible_price_indicators = indicator_cols[0].multiselect(
                "價格指標",
                options=["MA5", "MA10", "MA20", "MA60", "MA120"],
                default=["MA5", "MA10", "MA20", "MA60"],
                key="stock_detail_price_indicators",
            )
            visible_volume_indicators = indicator_cols[1].multiselect(
                "量能指標",
                options=["MV5", "MV20"],
                default=["MV5", "MV20"],
                key="stock_detail_volume_indicators",
            )
        if start_date > end_date:
            st.error("開始日不能晚於結束日。")
        else:
            render_streamlit_lightweight_chart(
                symbol,
                stock_title,
                start_date=start_date,
                end_date=end_date,
                key_prefix="stock_detail_workspace",
                stock_code=stock_code,
                market_label=market_text,
                visible_price_indicators=visible_price_indicators,
                visible_volume_indicators=visible_volume_indicators,
                interval=interval_label,
            )
    elif stock_code and selected_section == "短衝主力":
        _render_short_term_broker_section(stock_code)
    elif stock_code and selected_section == "分點明細":
        _render_broker_branch_section(stock_code)
