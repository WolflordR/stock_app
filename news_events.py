from datetime import timedelta

import pandas as pd

from price_cache import fetch_price_history

from news_ai import build_ai_news_section_analysis
from news_common import US_EASTERN, attach_company_and_theme_links, attach_zh_translation, fetch_google_news, headline_keywords, parse_pub_datetime


def compute_market_reaction(published_at, symbol="QQQ"):
    event_dt = parse_pub_datetime(published_at)
    if event_dt is None:
        return None

    event_est = event_dt.astimezone(US_EASTERN)
    history_df = fetch_price_history(symbol, mode="即時選股", history_buffer_days=180)
    if history_df.empty:
        return None

    trading_dates = list(history_df.index)
    if not trading_dates:
        return None

    event_date = pd.Timestamp(event_est.date())
    after_close = event_est.hour > 16 or (event_est.hour == 16 and event_est.minute > 0)
    candidate_date = event_date + timedelta(days=1) if after_close else event_date

    reaction_pos = None
    for index, trade_date in enumerate(trading_dates):
        if trade_date >= candidate_date:
            reaction_pos = index
            break

    latest_trading_date = trading_dates[-1]
    if reaction_pos is None and candidate_date > latest_trading_date:
        return {
            "reaction_date": "待下個交易日",
            "one_day_pct": None,
            "three_day_pct": None,
            "pending": True,
        }

    if reaction_pos is None or reaction_pos == 0:
        return None

    reaction_date = trading_dates[reaction_pos]
    prev_date = trading_dates[reaction_pos - 1]
    base_close = float(history_df.loc[prev_date, "Close"])
    reaction_close = float(history_df.loc[reaction_date, "Close"])
    one_day_pct = (reaction_close / base_close - 1) * 100 if base_close else None

    three_day_pos = min(reaction_pos + 2, len(trading_dates) - 1)
    three_day_date = trading_dates[three_day_pos]
    three_day_close = float(history_df.loc[three_day_date, "Close"])
    three_day_pct = (three_day_close / base_close - 1) * 100 if base_close else None

    return {
        "reaction_date": reaction_date.strftime("%Y-%m-%d"),
        "one_day_pct": one_day_pct,
        "three_day_pct": three_day_pct,
        "pending": False,
    }


def _build_event_comment(title, one_day_pct, three_day_pct, pending=False):
    title_lower = title.lower()
    if pending:
        return "這則事件發布後的下一個交易日還沒收盤，所以 Nasdaq 反應要等下個交易日才會完整。"
    if one_day_pct is None:
        return "目前還抓不到足夠的市場反應資料。"

    if any(keyword in title_lower for keyword in ["tariff", "trade", "china", "sanction"]):
        topic_hint = "這類政策或關稅訊息通常先影響風險偏好與科技股評價。"
    elif any(keyword in title_lower for keyword in ["powell", "fed", "cpi", "inflation", "payroll"]):
        topic_hint = "這類宏觀訊息通常先影響利率預期，再帶動科技成長股評價。"
    elif any(keyword in title_lower for keyword in ["nvidia", "apple", "microsoft", "meta", "tesla"]):
        topic_hint = "這類科技龍頭消息通常最容易先反映在 Nasdaq 與 AI 族群。"
    else:
        topic_hint = "這則消息比較像總體風險偏好的事件。"

    if one_day_pct >= 1.5 and (three_day_pct is None or three_day_pct >= one_day_pct - 1):
        reaction_hint = "市場第一時間偏正面解讀，而且後續延續性不差。"
    elif one_day_pct <= -1.5 and (three_day_pct is None or three_day_pct <= one_day_pct + 1):
        reaction_hint = "市場第一時間偏負面解讀，後續壓力也沒有很快消失。"
    elif one_day_pct > 0 and three_day_pct is not None and three_day_pct < 0:
        reaction_hint = "市場先漲後回，代表第一時間樂觀，但後續追價力道不足。"
    elif one_day_pct < 0 and three_day_pct is not None and three_day_pct > 0:
        reaction_hint = "市場先跌後穩，代表初始反應偏保守，但後面有修正解讀。"
    else:
        reaction_hint = "市場有反應，但目前還是偏震盪消化。"

    return f"{topic_hint}{reaction_hint}"


def _classify_earnings_tone(title, one_day_pct=None, three_day_pct=None):
    title_lower = title.lower()
    positive_keywords = ["beats", "beat", "raised", "strong", "surge", "record", "above estimates", "tops estimates"]
    negative_keywords = ["misses", "miss", "cuts", "weak", "warns", "below estimates", "disappoints", "slump"]

    positive_hits = sum(keyword in title_lower for keyword in positive_keywords)
    negative_hits = sum(keyword in title_lower for keyword in negative_keywords)

    if one_day_pct is not None:
        if one_day_pct >= 2:
            positive_hits += 1
        elif one_day_pct <= -2:
            negative_hits += 1

    if positive_hits > negative_hits:
        return "偏利多"
    if negative_hits > positive_hits:
        return "偏利空"
    return "偏中性"


def _build_earnings_comment(title, one_day_pct, three_day_pct, pending=False):
    tone = _classify_earnings_tone(title, one_day_pct, three_day_pct)
    if pending:
        return f"這則財報消息目前判讀為 {tone}，但下一個交易日還沒完整反映，市場接受度要再看後續收盤。"
    if one_day_pct is None:
        return f"這則財報消息目前判讀為 {tone}，但還抓不到足夠的市場反應資料。"

    if one_day_pct >= 2 and (three_day_pct is None or three_day_pct >= 0):
        reaction = "市場第一時間偏買單，代表財報或展望有打中預期。"
    elif one_day_pct <= -2 and (three_day_pct is None or three_day_pct <= 0):
        reaction = "市場第一時間偏不買單，可能是財報數字、毛利率或財測不如預期。"
    elif one_day_pct > 0 and three_day_pct is not None and three_day_pct < 0:
        reaction = "市場先正面反應，但後續追價力道不足，代表解讀並不一致。"
    elif one_day_pct < 0 and three_day_pct is not None and three_day_pct > 0:
        reaction = "市場先保守再修正，代表初始反應可能過度悲觀。"
    else:
        reaction = "市場反應偏震盪，代表消息本身沒有形成單邊共識。"

    return f"這則財報消息目前判讀為 {tone}。{reaction}"


def _build_mna_comment(title, one_day_pct, three_day_pct, pending=False):
    title_lower = title.lower()
    if any(keyword in title_lower for keyword in ["all-stock", "share swap", "stock deal"]):
        structure_hint = "如果是換股或全股票交易，市場通常會同時評估稀釋與綜效。"
    elif any(keyword in title_lower for keyword in ["cash deal", "buyout", "take-private"]):
        structure_hint = "如果是現金收購或私有化，市場通常會先看溢價與監管風險。"
    else:
        structure_hint = "這類併購消息通常會先影響估值重訂價與產業想像空間。"

    if pending:
        return f"{structure_hint} 目前下一個交易日還沒完整反映，所以市場到底買不買單還要等後續收盤確認。"
    if one_day_pct is None:
        return f"{structure_hint} 目前還抓不到足夠的市場反應資料。"

    if one_day_pct >= 2:
        reaction = "市場第一時間偏正面，代表投資人較願意相信這筆交易有綜效或有利估值。"
    elif one_day_pct <= -2:
        reaction = "市場第一時間偏負面，可能在擔心溢價過高、整合風險或監管障礙。"
    else:
        reaction = "市場反應偏保守，通常代表交易條件還需要更多細節消化。"

    return f"{structure_hint}{reaction}"


def _classify_company_news_tone(title, title_zh=""):
    combined_text = f"{title} {title_zh}".lower()
    positive_keywords = [
        "beat", "beats", "raised", "strong", "surge", "record",
        "order win", "orders", "supplier", "selected", "partnership",
        "接單", "獲單", "供應", "打入", "合作", "成長", "創高", "優於預期", "上修", "樂觀",
    ]
    negative_keywords = [
        "miss", "misses", "cuts", "warns", "weak", "slump", "delay",
        "reduce orders", "cuts orders", "inventory", "downgrade",
        "砍單", "下修", "虧損", "不如預期", "衰退", "疲弱", "遞延", "降價", "庫存",
    ]
    positive_hits = sum(keyword in combined_text for keyword in positive_keywords)
    negative_hits = sum(keyword in combined_text for keyword in negative_keywords)
    if positive_hits > negative_hits:
        return "偏利多", positive_hits - negative_hits
    if negative_hits > positive_hits:
        return "偏利空", negative_hits - positive_hits
    return "偏中性", 0


def _describe_company_links(company_links):
    if not company_links:
        return "暫時沒有直接對上的台股公司"
    return " / ".join(
        f"{item['name_zh']}({item['code']}｜{item.get('industry') or '未分類'})"
        for item in company_links[:4]
    )


def _build_company_focus_summary(items):
    if not items:
        return "目前還抓不到夠明確的公司焦點新聞。"
    company_names = []
    theme_names = []
    for item in items:
        company_names.extend(link["name_zh"] for link in item.get("company_links", []))
        theme_names.extend(item.get("theme_links", []))
    company_text = "、".join(headline_keywords(company_names, top_n=4)) or "台股公司"
    theme_text = "、".join(headline_keywords(theme_names, top_n=4)) or "產業與財報"
    return f"這組新聞目前較常提到 {company_text}，重點多集中在 {theme_text}。"


def _rank_company_focus_items(items):
    ranked_items = []
    for item in items:
        tone, tone_score = _classify_company_news_tone(item.get("title", ""), item.get("title_zh", ""))
        topic_score = 0
        text = f"{item.get('title', '')} {item.get('title_zh', '')}".lower()
        if any(keyword in text for keyword in ["earnings", "guidance", "財報", "法說", "eps", "毛利"]):
            topic_score += 2
        if any(keyword in text for keyword in ["order", "supplier", "供應鏈", "接單", "供應", "客戶"]):
            topic_score += 2
        impact_score = tone_score * 3 + len(item.get("company_links", [])) * 2 + len(item.get("theme_links", [])) + topic_score
        ranked_items.append(
            {
                **item,
                "tone": tone,
                "impact_score": impact_score,
            }
        )
    return sorted(ranked_items, key=lambda item: (-item["impact_score"], item.get("published_at", "")), reverse=False)


def _build_order_flow_comment(item):
    company_text = _describe_company_links(item.get("company_links", []))
    theme_text = "、".join(item.get("theme_links", [])[:4]) or "供應鏈題材"
    tone, _ = _classify_company_news_tone(item.get("title", ""), item.get("title_zh", ""))
    if tone == "偏利多":
        return f"這則消息比較像訂單或供應鏈偏正面的線索，對應公司先看 {company_text}；相關題材可留意 {theme_text}。"
    if tone == "偏利空":
        return f"這則消息偏向訂單或需求面的壓力訊號，對應公司先看 {company_text}；相關題材可留意 {theme_text}。"
    return f"這則消息比較像供應鏈線索更新，對應公司先看 {company_text}；相關題材可留意 {theme_text}。"


def _build_topic_summary(topic_name, items):
    if not items:
        return f"{topic_name} 目前抓不到足夠新聞。"

    keywords = headline_keywords([item.get("title_zh") or item["title"] for item in items], top_n=4)
    keyword_text = "、".join(keywords) if keywords else "政策、利率與科技"
    sources = " / ".join(sorted({item["source"] for item in items if item.get("source")})[:3]) or "Google News"
    return f"{topic_name} 這幾天新聞重點多圍繞 {keyword_text}，主要來源包括 {sources}。"


def _build_thematic_news_report(anchor_date, topic_name, queries, max_items=4, days_back=5, comment_builder=None):
    merged_items = []
    seen_titles = set()

    for query in queries:
        items = fetch_google_news(
            query,
            max_items=max_items,
            ceid="US:en",
            anchor_date=anchor_date,
            days_back=days_back,
        )
        items = attach_company_and_theme_links(attach_zh_translation(items))
        for item in items:
            title = item.get("title", "")
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            reaction = compute_market_reaction(item.get("published_at"), symbol="QQQ")
            merged_items.append(
                {
                    **item,
                    "reaction": reaction,
                    "comment": comment_builder(
                        title,
                        reaction.get("one_day_pct") if reaction else None,
                        reaction.get("three_day_pct") if reaction else None,
                        reaction.get("pending", False) if reaction else False,
                    ) if comment_builder else None,
                }
            )

    merged_items = sorted(
        merged_items,
        key=lambda item: parse_pub_datetime(item.get("published_at")) or pd.Timestamp.min.tz_localize("UTC"),
        reverse=True,
    )[:max_items]

    return {
        "topic": topic_name,
        "summary": _build_topic_summary(topic_name, merged_items),
        "items": merged_items,
    }


def build_event_watch_report(anchor_date, max_items_per_topic=3):
    topic_queries = [
        ("川普發言", "Trump speech OR Trump remarks OR Trump says stocks OR Trump announcement"),
        ("聯準會 / Powell", "Powell speech OR FOMC OR Federal Reserve announcement stocks"),
        ("美國總體數據", "CPI OR PCE OR payrolls OR GDP US stocks"),
    ]

    topics = []
    for topic_name, query in topic_queries:
        items = fetch_google_news(
            query,
            max_items=max_items_per_topic,
            ceid="US:en",
            anchor_date=anchor_date,
            days_back=5,
        )
        items = attach_company_and_theme_links(attach_zh_translation(items))

        enriched_items = []
        for item in items:
            reaction = compute_market_reaction(item.get("published_at"), symbol="QQQ")
            enriched_items.append(
                {
                    **item,
                    "reaction": reaction,
                    "comment": _build_event_comment(
                        item.get("title", ""),
                        reaction.get("one_day_pct") if reaction else None,
                        reaction.get("three_day_pct") if reaction else None,
                        reaction.get("pending", False) if reaction else False,
                    ),
                }
            )

        ai_summary = build_ai_news_section_analysis(
            topic_name,
            enriched_items,
            "請特別說明事件重點、對風險偏好的影響，以及 Nasdaq/QQQ 的反應有沒有跟新聞方向一致。",
        )

        topics.append(
            {
                "topic": topic_name,
                "summary": _build_topic_summary(topic_name, enriched_items),
                "items": enriched_items,
                "ai_summary": ai_summary,
            }
        )

    return {
        "topics": topics,
    }


def build_mna_news_report(anchor_date, max_items=4):
    queries = [
        "merger OR acquisition OR takeover OR buyout US stocks",
        "M&A deal announced company to acquire US stocks",
        "strategic acquisition antitrust review merger stocks",
    ]
    report = _build_thematic_news_report(
        anchor_date,
        "併購消息",
        queries,
        max_items=max_items,
        days_back=7,
        comment_builder=_build_mna_comment,
    )
    if report:
        report["ai_summary"] = build_ai_news_section_analysis(
            "併購消息",
            report["items"],
            "請特別評估併購條件、可能的監管或整合風險，以及這對台股哪些題材可能有外溢影響。",
        )
    return report


def build_earnings_news_report(anchor_date, max_items=6):
    queries = [
        "earnings results guidance beats misses US stocks",
        "quarterly results revenue outlook earnings call Nasdaq",
        "after hours earnings guidance cuts raises Wall Street",
    ]
    report = _build_thematic_news_report(
        anchor_date,
        "財報公布",
        queries,
        max_items=max_items,
        days_back=5,
        comment_builder=_build_earnings_comment,
    )
    if report:
        report["ai_summary"] = build_ai_news_section_analysis(
            "財報公布",
            report["items"],
            "請特別指出市場是買單還是不買單、比較像數字優於預期還是展望影響，並補充可能影響的台股題材。",
        )
    return report


def build_us_order_flow_report(anchor_date, max_items=6):
    queries = [
        "NVIDIA supplier order OR Taiwan supply chain OR order win",
        "Apple supplier order Taiwan OR manufacturing partner OR supply chain",
        "Microsoft Amazon Meta AI server supplier Taiwan order",
        "AMD Broadcom Tesla supplier Taiwan order OR supply chain",
    ]

    merged_items = []
    seen_titles = set()
    for query in queries:
        items = fetch_google_news(
            query,
            max_items=max_items,
            ceid="US:en",
            anchor_date=anchor_date,
            days_back=5,
        )
        items = attach_company_and_theme_links(attach_zh_translation(items))
        for item in items:
            title = item.get("title", "")
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            reaction = compute_market_reaction(item.get("published_at"), symbol="QQQ")
            merged_items.append(
                {
                    **item,
                    "reaction": reaction,
                    "comment": _build_order_flow_comment(item),
                }
            )

    ranked_items = _rank_company_focus_items(merged_items)
    top_items = ranked_items[:max_items]
    return {
        "summary": _build_company_focus_summary(top_items),
        "items": top_items,
    }


def build_taiwan_company_focus_report(anchor_date, max_items=10):
    queries = [
        "台股 財報 法說 EPS 毛利 展望",
        "台股 接單 訂單 供應鏈 客戶 AI 伺服器",
        "台股 記憶體 財報 旺宏 華邦電 南亞科",
        "台股 利多 利空 下修 上修 砍單",
    ]

    merged_items = []
    seen_titles = set()
    for query in queries:
        items = fetch_google_news(
            query,
            max_items=max_items,
            anchor_date=anchor_date,
            days_back=5,
        )
        items = attach_company_and_theme_links(items)
        for item in items:
            title = item.get("title", "")
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            merged_items.append(item)

    ranked_items = _rank_company_focus_items(merged_items)
    bullish_items = [item for item in ranked_items if item.get("tone") == "偏利多"][:max_items]
    bearish_items = [item for item in ranked_items if item.get("tone") == "偏利空"][:max_items]
    neutral_items = [item for item in ranked_items if item.get("tone") == "偏中性"][:max_items]
    return {
        "summary": _build_company_focus_summary(ranked_items[:max_items]),
        "items": ranked_items[:max_items],
        "bullish_items": bullish_items,
        "bearish_items": bearish_items,
        "neutral_items": neutral_items,
    }
