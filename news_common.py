from __future__ import annotations

from collections import Counter
from datetime import timedelta
from email.utils import parsedate_to_datetime
from functools import lru_cache
import re
import urllib.parse
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from company_links_db import extract_company_links_from_text, get_company_official_industry_df, infer_themes_from_text
from http_utils import request_text


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
US_EASTERN = ZoneInfo("America/New_York")


def _request_text(url):
    return request_text(
        url,
        headers={
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        },
        encoding="utf-8",
    )


def date_window_query(anchor_date, days_back):
    anchor_ts = pd.to_datetime(anchor_date).normalize()
    after_date = (anchor_ts - timedelta(days=days_back)).strftime("%Y-%m-%d")
    before_date = (anchor_ts + timedelta(days=1)).strftime("%Y-%m-%d")
    return f"after:{after_date} before:{before_date}"


def fetch_google_news(query, max_items=5, ceid="TW:zh-Hant", anchor_date=None, days_back=7):
    dated_query = query
    if anchor_date is not None:
        dated_query = f"{query} {date_window_query(anchor_date, days_back)}"

    if ceid.startswith("US:"):
        hl = "en-US"
        gl = "US"
    else:
        hl = "zh-TW"
        gl = "TW"

    url = (
        GOOGLE_NEWS_RSS
        + "?"
        + urllib.parse.urlencode(
            {
                "q": dated_query,
                "hl": hl,
                "gl": gl,
                "ceid": ceid,
            }
        )
    )
    xml_text = _request_text(url)
    root = ET.fromstring(xml_text)
    items = []
    seen_titles = set()
    for item in root.findall("./channel/item"):
        raw_title = (item.findtext("title") or "").strip()
        title = re.sub(r"\s*-\s*[^-]+$", "", raw_title).strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        items.append(
            {
                "title": title,
                "link": (item.findtext("link") or "").strip(),
                "source": (item.findtext("source") or "").strip(),
                "published_at": (item.findtext("pubDate") or "").strip(),
            }
        )
        if len(items) >= max_items:
            break
    return items


@lru_cache(maxsize=2048)
def translate_to_zh_tw(text):
    if not text:
        return ""

    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "en",
                "tl": "zh-TW",
                "dt": "t",
                "q": text,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        translated = "".join(part[0] for part in payload[0] if part and part[0])
        return translated or text
    except Exception:
        return text


def attach_zh_translation(items):
    return [
        {
            **item,
            "title_zh": translate_to_zh_tw(item.get("title", "")),
        }
        for item in items
    ]


def enrich_item_links(item):
    company_links = extract_company_links_from_text(
        item.get("title", ""),
        item.get("title_zh", ""),
    )
    theme_links = infer_themes_from_text(
        item.get("title", ""),
        item.get("title_zh", ""),
        company_links=company_links,
    )
    return {
        **item,
        "company_links": company_links,
        "theme_links": theme_links,
    }


def attach_company_and_theme_links(items):
    return [enrich_item_links(item) for item in items]


def headline_keywords(titles, top_n=3):
    stopwords = {
        "台股", "美股", "產業", "市場", "公司", "股價", "新聞", "今日", "最新", "分析",
        "industry", "market", "stock", "stocks", "news", "today", "latest",
    }
    tokens = []
    for title in titles:
        tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,}", title))
    cleaned_tokens = [token for token in tokens if token.lower() not in stopwords]
    keyword_counts = Counter(cleaned_tokens)
    return [token for token, _ in keyword_counts.most_common(top_n)]


def parse_pub_datetime(value):
    if not value:
        return None
    try:
        parsed_dt = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed_dt.tzinfo is None:
        return parsed_dt.replace(tzinfo=ZoneInfo("UTC"))
    return parsed_dt


def format_volume(value):
    if pd.isna(value):
        return "-"
    return f"{value/1000:,.1f} 張"


def format_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.2f}%"


def get_industry_mapping():
    return get_company_official_industry_df()
