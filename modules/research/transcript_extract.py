from __future__ import annotations

from datetime import datetime
from typing import Iterable

from bs4 import BeautifulSoup

from modules.core.http_utils import request_text
from modules.research.transcript_search import SEARCH_HEADERS, SourceRecord, _normalize_text, search_earnings_call_sources


TRANSCRIPT_SELECTORS = [
    "div.article-body",
    "article",
    "main",
    "[itemprop='articleBody']",
    ".caas-body",
    ".article__content",
    ".article-content",
    ".content-body",
]


def _pick_best_content_node(soup):
    best_text = ""
    for selector in TRANSCRIPT_SELECTORS:
        for node in soup.select(selector):
            text = _normalize_text(node.get_text(" ", strip=True))
            if len(text) > len(best_text):
                best_text = text
        if len(best_text) >= 1200:
            break
    return best_text


def _extract_meta_description(soup):
    node = soup.select_one("meta[name='description'], meta[property='og:description']")
    if not node:
        return ""
    return _normalize_text(node.get("content") or "")


def _extract_published_hint(soup):
    for selector in [
        "meta[property='article:published_time']",
        "meta[name='article:published_time']",
        "meta[name='publish-date']",
        "time[datetime]",
    ]:
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content") or node.get("datetime") or node.get_text(" ", strip=True)
        value = _normalize_text(value)
        if value:
            return value
    return ""


def fetch_source_text(source: SourceRecord, max_chars=5000):
    try:
        html = request_text(
            source.url,
            headers=SEARCH_HEADERS,
            timeout=30,
            encoding="utf-8",
        )
    except Exception:
        return source

    soup = BeautifulSoup(html, "html.parser")
    extracted_text = _pick_best_content_node(soup)
    if len(extracted_text) < 300:
        extracted_text = _extract_meta_description(soup)

    source.extracted_text = extracted_text[:max_chars]
    published_hint = _extract_published_hint(soup)
    if published_hint:
        source.published_hint = published_hint
    return source


def _is_usable_source(source: SourceRecord):
    text = _normalize_text(source.extracted_text).lower()
    if len(text) < 120:
        return False
    quality_markers = [
        "earnings call",
        "transcript",
        "call participants",
        "prepared remarks",
        "quarterly results",
        "financial results",
        "guidance",
        "capex",
    ]
    return any(marker in text for marker in quality_markers)


def _serialize_sources(sources: Iterable[SourceRecord]):
    rows = []
    for source in sources:
        rows.append(
            {
                "title": source.title,
                "url": source.url,
                "domain": source.domain,
                "source_type": source.source_type,
                "published_hint": source.published_hint,
                "snippet": source.snippet,
                "extracted_text": source.extracted_text,
            }
        )
    return rows


def build_earnings_call_material_bundle(company_query, max_sources=4):
    sources = search_earnings_call_sources(company_query, max_results=max_sources + 2)
    fetched_sources = [fetch_source_text(source) for source in sources]
    usable_sources = [source for source in fetched_sources if _is_usable_source(source)]
    usable_sources = usable_sources[:max_sources]

    combined_sections = []
    for index, source in enumerate(usable_sources, start=1):
        excerpt = source.extracted_text[:4000]
        combined_sections.append(
            f"[Source {index}] {source.title}\nURL: {source.url}\nPublished: {source.published_hint}\nContent: {excerpt}"
        )

    return {
        "company_query": company_query,
        "source_count": len(usable_sources),
        "sources": _serialize_sources(usable_sources),
        "combined_text": "\n\n".join(combined_sections).strip(),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
