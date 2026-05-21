from datetime import date, datetime, timedelta

from modules.industry.company_links_db import extract_company_links_from_text
from modules.research.transcript_research import fetch_source_text, search_generic_sources

from modules.research.research_transcript_constants import (
    COMPANY_TICKER_MAP,
    EVENT_ISO_PATTERN,
    EVENT_MONTH_PATTERN,
    EVENT_SEARCH_KEYWORDS,
    EVENT_SLASH_PATTERN,
    ORDER_SEARCH_KEYWORDS,
)


def build_order_search_queries(company_query):
    normalized = str(company_query or "").strip()
    return [f"{normalized} {keyword}" for keyword in ORDER_SEARCH_KEYWORDS]


def build_event_search_queries(company_query):
    normalized = str(company_query or "").strip()
    return [f"{normalized} {keyword}" for keyword in EVENT_SEARCH_KEYWORDS]


def resolve_research_ticker(company_query):
    normalized = str(company_query or "").strip().lower()
    if normalized in COMPANY_TICKER_MAP:
        return COMPANY_TICKER_MAP[normalized]
    compact = normalized.replace(".", "").replace("-", "").replace(" ", "")
    return COMPANY_TICKER_MAP.get(compact, str(company_query or "").strip().upper())


def parse_event_date_token(token, today):
    normalized = str(token or "").strip().replace("Sept ", "Sep ")
    if not normalized:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(normalized, fmt).date().replace(year=today.year)
            if parsed < today - timedelta(days=7):
                parsed = parsed.replace(year=today.year + 1)
            return parsed
        except ValueError:
            continue
    return None


def extract_candidate_event_dates(text, today):
    if not text:
        return []

    date_tokens = []
    for pattern in (EVENT_MONTH_PATTERN, EVENT_ISO_PATTERN, EVENT_SLASH_PATTERN):
        for match in pattern.finditer(text):
            token = str(match.group(0) or "").strip()
            if token:
                date_tokens.append(token)

    parsed_dates = []
    seen = set()
    for token in date_tokens:
        parsed = parse_event_date_token(token, today)
        if parsed and parsed not in seen:
            seen.add(parsed)
            parsed_dates.append(parsed)
    return sorted(parsed_dates)


def infer_event_type(text):
    lowered = str(text or "").lower()
    if any(keyword in lowered for keyword in ["earnings call", "earnings release", "quarterly results", "financial results", "investor relations"]):
        return "法說會"
    if any(keyword in lowered for keyword in ["investor day", "shareholder", "annual meeting"]):
        return "投資人 / 股東會"
    if any(keyword in lowered for keyword in ["conference", "summit", "forum", "expo", "computex"]):
        return "產業 / 技術會議"
    if any(keyword in lowered for keyword in ["keynote", "launch", "unveil", "event"]):
        return "產品發表會"
    return "公司活動"


def load_yfinance_earnings_events(company_query, today, window_end):
    try:
        import yfinance as yf
    except Exception:
        return []

    ticker = resolve_research_ticker(company_query)
    try:
        calendar = yf.Ticker(ticker).calendar
    except Exception:
        return []

    earnings_dates = []
    if isinstance(calendar, dict):
        earnings_dates = calendar.get("Earnings Date") or []
    elif hasattr(calendar, "get"):
        earnings_dates = calendar.get("Earnings Date") or []

    events = []
    seen = set()
    for raw_value in earnings_dates:
        if hasattr(raw_value, "date"):
            event_date = raw_value.date()
        elif isinstance(raw_value, date):
            event_date = raw_value
        else:
            continue
        if not (today <= event_date <= window_end) or event_date in seen:
            continue
        seen.add(event_date)
        events.append(
            {
                "event_date": event_date.isoformat(),
                "event_date_text": event_date.strftime("%Y-%m-%d"),
                "days_until": (event_date - today).days,
                "event_type": "法說會",
                "title": f"{company_query} earnings date (Yahoo Finance calendar)",
                "domain": "finance.yahoo.com",
                "source_type": "earnings_calendar",
                "snippet": f"{company_query} 下一次法說 / 財報日期",
                "url": f"https://finance.yahoo.com/quote/{ticker}",
            }
        )
    return events


def build_company_event_schedule_bundle(company_query, max_sources=6, window_days=30):
    today = date.today()
    window_end = today + timedelta(days=window_days)
    events = load_yfinance_earnings_events(company_query, today, window_end)

    try:
        sources = search_generic_sources(build_event_search_queries(company_query), max_results=max_sources + 3)
    except Exception:
        sources = []
    fetched_sources = [fetch_source_text(source, max_chars=2400) for source in sources[: max_sources + 3]]

    seen_keys = {(item["event_date"], item["url"], item["event_type"]) for item in events}
    for source in fetched_sources:
        combined_text = " ".join(part for part in [source.title, source.snippet, source.published_hint, source.extracted_text] if part)
        candidate_dates = extract_candidate_event_dates(combined_text, today)
        event_type = infer_event_type(combined_text)
        for event_date in candidate_dates:
            if not (today <= event_date <= window_end):
                continue
            dedupe_key = (event_date.isoformat(), source.url, event_type)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            events.append(
                {
                    "event_date": event_date.isoformat(),
                    "event_date_text": event_date.strftime("%Y-%m-%d"),
                    "days_until": (event_date - today).days,
                    "event_type": event_type,
                    "title": source.title,
                    "domain": source.domain,
                    "source_type": source.source_type,
                    "snippet": source.snippet,
                    "url": source.url,
                }
            )

    events = sorted(events, key=lambda item: (item["event_date"], item["days_until"], item["event_type"], item["title"]))
    return {
        "company_query": company_query,
        "search_queries": build_event_search_queries(company_query),
        "window_days": int(window_days),
        "window_start": today.isoformat(),
        "window_end": window_end.isoformat(),
        "events": events[:12],
    }


def build_taiwan_order_supply_chain_bundle(company_query, max_sources=5):
    sources = search_generic_sources(build_order_search_queries(company_query), max_results=max_sources + 2)
    fetched_sources = [fetch_source_text(source, max_chars=2200) for source in sources[: max_sources + 2]]

    matched_sources = []
    company_map = {}
    theme_counts = {}
    for source in fetched_sources:
        combined_text = " ".join(part for part in [source.title, source.snippet, source.extracted_text] if part)
        company_links = extract_company_links_from_text(combined_text, max_matches=10)
        if not company_links:
            continue

        matched_sources.append(
            {
                "title": source.title,
                "url": source.url,
                "domain": source.domain,
                "published_hint": source.published_hint,
                "snippet": source.snippet,
                "extracted_text": source.extracted_text,
                "matched_companies": company_links,
            }
        )
        for company in company_links:
            code = str(company.get("code") or "").zfill(4)
            if code and code not in company_map:
                company_map[code] = company
            for theme in company.get("themes") or []:
                normalized_theme = str(theme or "").strip()
                if normalized_theme:
                    theme_counts[normalized_theme] = theme_counts.get(normalized_theme, 0) + 1

    ranked_themes = [theme for theme, _ in sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))]
    matched_companies = sorted(
        company_map.values(),
        key=lambda item: (-len(item.get("themes") or []), str(item.get("name_zh") or "")),
    )

    return {
        "company_query": company_query,
        "search_queries": build_order_search_queries(company_query),
        "source_count": len(matched_sources),
        "sources": matched_sources[:max_sources],
        "matched_companies": matched_companies,
        "matched_themes": ranked_themes[:12],
    }


def build_tracking_company_schedule_payload_map(company_queries, window_days=30):
    payload_map = {}
    for company_query in company_queries:
        payload_map[company_query] = build_company_event_schedule_bundle(
            company_query,
            max_sources=5,
            window_days=window_days,
        )
    return payload_map
