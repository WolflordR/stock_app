from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse

from bs4 import BeautifulSoup

from http_utils import request_text


DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SOURCE_DOMAIN_SCORES = {
    "investor.": 6,
    "ir.": 6,
    "fool.com": 5,
    "seekingalpha.com": 5,
    "stockanalysis.com": 4,
    "finance.yahoo.com": 4,
    "nasdaq.com": 4,
    "marketscreener.com": 3,
}


@dataclass
class SourceRecord:
    title: str
    url: str
    snippet: str
    domain: str
    score: float
    source_type: str
    published_hint: str
    extracted_text: str = ""


def _normalize_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _unwrap_duckduckgo_url(url):
    if not url:
        return ""
    normalized = url.strip()
    if normalized.startswith("//"):
        normalized = "https:" + normalized
    parsed = urlparse(normalized)
    if "duckduckgo.com" not in parsed.netloc:
        return normalized
    target = parse_qs(parsed.query).get("uddg", [""])[0]
    return target or normalized


def _infer_source_type(title, url):
    text = f"{title} {url}".lower()
    if "transcript" in text or "earnings call" in text:
        return "transcript"
    if "investor" in text or "press release" in text or "results" in text:
        return "investor_release"
    return "coverage"


def _score_source(title, url, snippet):
    lowered = f"{title} {url} {snippet}".lower()
    score = 0.0
    if "earnings call" in lowered:
        score += 5.0
    if "transcript" in lowered:
        score += 5.0
    if "quarterly results" in lowered or "financial results" in lowered:
        score += 3.0
    if "prepared remarks" in lowered:
        score += 2.5
    if "guidance" in lowered or "capex" in lowered:
        score += 1.5

    domain = urlparse(url).netloc.lower()
    for pattern, bonus in SOURCE_DOMAIN_SCORES.items():
        if pattern in domain:
            score += bonus
    return score


def _extract_snippet(result_node):
    snippet_node = result_node.select_one(".result__snippet")
    return _normalize_text(snippet_node.get_text(" ", strip=True) if snippet_node else "")


def _search_duckduckgo(query, max_results=8):
    html = request_text(
        DUCKDUCKGO_HTML_URL + "?" + urlencode({"q": query}),
        headers=SEARCH_HEADERS,
        timeout=30,
        encoding="utf-8",
    )
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result_node in soup.select(".result"):
        link = result_node.select_one("a.result__a")
        if not link:
            continue
        title = _normalize_text(link.get_text(" ", strip=True))
        raw_url = link.get("href") or ""
        url = _unwrap_duckduckgo_url(raw_url)
        if not title or not url.startswith("http"):
            continue
        snippet = _extract_snippet(result_node)
        published_hint = ""
        extras_node = result_node.select_one(".result__extras__url")
        if extras_node:
            published_hint = _normalize_text(extras_node.get_text(" ", strip=True))
        results.append(
            SourceRecord(
                title=title,
                url=url,
                snippet=snippet,
                domain=urlparse(url).netloc.lower(),
                score=_score_source(title, url, snippet),
                source_type=_infer_source_type(title, url),
                published_hint=published_hint,
            )
        )
        if len(results) >= max_results:
            break
    return results


def _build_search_queries(company_query):
    normalized = _normalize_text(company_query)
    return [
        f"{normalized} earnings call transcript",
        f"{normalized} quarterly results guidance capex",
        f"{normalized} investor relations earnings release transcript",
    ]


def search_earnings_call_sources(company_query, max_results=6):
    merged = {}
    for query in _build_search_queries(company_query):
        for result in _search_duckduckgo(query, max_results=max_results):
            current = merged.get(result.url)
            if current is None or result.score > current.score:
                merged[result.url] = result
    ranked = sorted(merged.values(), key=lambda item: (-item.score, item.domain, item.title))
    return ranked[:max_results]


def search_generic_sources(search_queries, max_results=6):
    merged = {}
    for query in search_queries:
        for result in _search_duckduckgo(query, max_results=max_results):
            current = merged.get(result.url)
            if current is None or result.score > current.score:
                merged[result.url] = result
    ranked = sorted(merged.values(), key=lambda item: (-item.score, item.domain, item.title))
    return ranked[:max_results]
