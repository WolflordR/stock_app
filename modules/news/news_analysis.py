import os

from modules.news.news_ai import DEFAULT_OPENAI_NEWS_MODEL, get_openai_api_key
from modules.news.news_events import build_earnings_news_report, build_event_watch_report, build_mna_news_report, build_taiwan_company_focus_report, build_us_order_flow_report
from modules.news.news_market import build_daily_news_brief, build_hot_theme_rankings, build_industry_news_report, build_industry_overlap_signals, build_us_market_news_report, build_us_market_snapshot


def build_news_analysis_bundle(anchor_date, industry_count=5, headlines_per_industry=4, us_news_items=8):
    theme_news = build_hot_theme_rankings(
        anchor_date,
        top_n=industry_count,
        headlines_per_theme=headlines_per_industry,
    )
    industry_news = build_industry_news_report(
        anchor_date,
        industry_count=industry_count,
        headlines_per_industry=headlines_per_industry,
    )
    overlap_result = build_industry_overlap_signals(anchor_date, top_n=industry_count)
    us_snapshot = build_us_market_snapshot(anchor_date)
    us_news = build_us_market_news_report(anchor_date, max_items=us_news_items)
    event_watch = build_event_watch_report(anchor_date, max_items_per_topic=3)
    mna_news = build_mna_news_report(anchor_date, max_items=4)
    earnings_news = build_earnings_news_report(anchor_date, max_items=6)
    order_flow_news = build_us_order_flow_report(anchor_date, max_items=6)
    company_focus_news = build_taiwan_company_focus_report(anchor_date, max_items=8)
    daily_brief = build_daily_news_brief(
        anchor_date,
        theme_news,
        industry_news,
        overlap_result,
        us_snapshot,
        us_news,
        mna_news,
        earnings_news,
        order_flow_news,
        company_focus_news,
    )
    trump_topic = next((topic for topic in event_watch["topics"] if topic["topic"] == "川普發言"), None)
    if trump_topic and trump_topic["items"]:
        lead_item = trump_topic["items"][0]
        reaction = lead_item.get("reaction")
        if reaction and reaction.get("one_day_pct") is not None:
            daily_brief.append(
                f"最近一則川普事件是「{lead_item.get('title_zh') or lead_item['title']}」，QQQ 次日反應 {reaction['one_day_pct']:.2f}%，"
                f"3 日反應 {reaction['three_day_pct']:.2f}%。"
            )
        else:
            daily_brief.append(f"最近一則川普事件是「{lead_item.get('title_zh') or lead_item['title']}」，市場反應仍在等待下一個交易日確認。")
    return {
        "daily_brief": daily_brief,
        "theme_news": theme_news,
        "industry_news": industry_news,
        "overlap_result": overlap_result,
        "us_snapshot": us_snapshot,
        "us_news": us_news,
        "event_watch": event_watch,
        "mna_news": mna_news,
        "earnings_news": earnings_news,
        "order_flow_news": order_flow_news,
        "company_focus_news": company_focus_news,
        "ai_summary_enabled": bool(get_openai_api_key()),
        "ai_model": os.getenv("OPENAI_NEWS_MODEL", DEFAULT_OPENAI_NEWS_MODEL).strip() or DEFAULT_OPENAI_NEWS_MODEL,
    }
