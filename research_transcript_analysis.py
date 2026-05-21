import re

import pandas as pd

from news_ai import call_openai_structured_json, has_llm_backend

from research_transcript_constants import (
    KEYWORD_GROUP_DIRECTIONS,
    TERM_GLOSSARY,
    TRANSCRIPT_KEYWORD_GROUPS,
)
from research_transcript_search import build_company_event_schedule_bundle, build_taiwan_order_supply_chain_bundle
from transcript_research import analyze_earnings_call_bundle, build_earnings_call_material_bundle


def parse_tracking_companies(multiselect_values, custom_text):
    ordered = []
    seen = set()
    for item in list(multiselect_values or []):
        normalized = str(item or "").strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            ordered.append(normalized)

    for line in str(custom_text or "").replace("，", ",").split(","):
        normalized = line.strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            ordered.append(normalized)
    return ordered


def build_tracking_company_payload_map(company_queries):
    payload_map = {}
    for company_query in company_queries:
        bundle = build_earnings_call_material_bundle(company_query, max_sources=4)
        analysis_result = analyze_earnings_call_bundle(bundle) if bundle and bundle.get("sources") else None
        order_bundle = build_taiwan_order_supply_chain_bundle(company_query, max_sources=5)
        schedule_bundle = build_company_event_schedule_bundle(company_query, max_sources=5, window_days=30)
        payload_map[company_query] = {
            "bundle": bundle,
            "analysis": analysis_result,
            "order_bundle": order_bundle,
            "schedule_bundle": schedule_bundle,
        }
    return payload_map


def extract_tracking_summary_row(company_query, payload):
    bundle = payload.get("bundle") or {}
    analysis = payload.get("analysis") or {}
    sources = bundle.get("sources") or []
    published_hint = sources[0].get("published_hint") if sources else ""

    def _join_keywords(items, limit=3):
        keywords = [str(item.get("keyword_en") or "").strip() for item in (items or []) if str(item.get("keyword_en") or "").strip()]
        return ", ".join(keywords[:limit]) if keywords else "-"

    all_directions = analysis.get("overall_supply_chain", []) or []
    order_bundle = payload.get("order_bundle") or {}
    schedule_bundle = payload.get("schedule_bundle") or {}
    events = schedule_bundle.get("events") or []
    order_company_names = [
        str(item.get("name_zh") or "").strip()
        for item in (order_bundle.get("matched_companies") or [])[:4]
        if str(item.get("name_zh") or "").strip()
    ]
    return {
        "公司": company_query,
        "抓到來源": len(sources),
        "最近來源時間": published_hint or "-",
        "瓶頸": _join_keywords(analysis.get("bottleneck_keywords", [])),
        "下一代": _join_keywords(analysis.get("next_generation_keywords", [])),
        "Capex": _join_keywords(analysis.get("capex_keywords", [])),
        "技術": _join_keywords(analysis.get("needed_technology_keywords", [])),
        "台股方向": "、".join(all_directions[:4]) if all_directions else "-",
        "台灣接單公司": "、".join(order_company_names) if order_company_names else "-",
        "接單線索": int(len(order_bundle.get("sources") or [])),
        "一個月內活動": int(len(events)),
        "最近活動日": events[0].get("event_date_text") if events else "-",
    }


def normalize_transcript_text(text):
    return re.sub(r"\r\n?", "\n", (text or "")).strip()


def extract_transcript_analysis(text):
    normalized_text = normalize_transcript_text(text)
    if not normalized_text:
        return None

    lines = [line.strip() for line in normalized_text.split("\n") if line.strip()]
    if not lines:
        lines = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", normalized_text) if segment.strip()]

    keyword_hits = []
    matched_directions = []
    for group in TRANSCRIPT_KEYWORD_GROUPS:
        matched_keywords = []
        matched_lines = []
        for keyword in group["keywords"]:
            pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
            if pattern.search(normalized_text):
                matched_keywords.append(keyword)
                if len(matched_lines) < 4:
                    for line in lines:
                        if pattern.search(line):
                            matched_lines.append(line)
                            if len(matched_lines) >= 4:
                                break
        if matched_keywords:
            keyword_hits.append(
                {
                    "group": group["group"],
                    "keywords": sorted(set(matched_keywords)),
                    "focus": group["focus"],
                    "matched_lines": matched_lines[:4],
                }
            )
            matched_directions.extend(KEYWORD_GROUP_DIRECTIONS.get(group["group"], []))

    matched_terms = []
    for item in TERM_GLOSSARY:
        pattern = re.compile(rf"\b{re.escape(item['term'])}\b", re.IGNORECASE)
        if pattern.search(normalized_text):
            matched_terms.append(item)
            matched_directions.extend([part.strip() for part in item["taiwan_link"].split("、") if part.strip()])

    unique_directions = []
    seen = set()
    for direction in matched_directions:
        normalized_direction = direction.strip()
        if normalized_direction and normalized_direction not in seen:
            seen.add(normalized_direction)
            unique_directions.append(normalized_direction)

    return {
        "keyword_hits": keyword_hits,
        "matched_terms": matched_terms,
        "directions": unique_directions[:12],
    }


def analyze_transcript_excerpt_ai(text):
    normalized_text = normalize_transcript_text(text)
    if not normalized_text or not has_llm_backend():
        return None

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_zh": {"type": "string"},
            "bottleneck_keywords": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "keyword_en": {"type": "string"},
                        "keyword_zh": {"type": "string"},
                        "meaning": {"type": "string"},
                        "evidence_excerpt": {"type": "string"},
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "evidence_excerpt", "taiwan_supply_chain"],
                },
            },
            "next_generation_keywords": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "keyword_en": {"type": "string"},
                        "keyword_zh": {"type": "string"},
                        "meaning": {"type": "string"},
                        "evidence_excerpt": {"type": "string"},
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "evidence_excerpt", "taiwan_supply_chain"],
                },
            },
            "capex_keywords": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "keyword_en": {"type": "string"},
                        "keyword_zh": {"type": "string"},
                        "meaning": {"type": "string"},
                        "evidence_excerpt": {"type": "string"},
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "evidence_excerpt", "taiwan_supply_chain"],
                },
            },
            "needed_technology_keywords": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "keyword_en": {"type": "string"},
                        "keyword_zh": {"type": "string"},
                        "meaning": {"type": "string"},
                        "evidence_excerpt": {"type": "string"},
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "evidence_excerpt", "taiwan_supply_chain"],
                },
            },
            "proper_terms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "keyword_en": {"type": "string"},
                        "keyword_zh": {"type": "string"},
                        "meaning": {"type": "string"},
                        "evidence_excerpt": {"type": "string"},
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "evidence_excerpt", "taiwan_supply_chain"],
                },
            },
            "overall_supply_chain": {"type": "array", "items": {"type": "string"}},
            "research_takeaway": {"type": "string"},
        },
        "required": [
            "summary_zh",
            "bottleneck_keywords",
            "next_generation_keywords",
            "capex_keywords",
            "needed_technology_keywords",
            "proper_terms",
            "overall_supply_chain",
            "research_takeaway",
        ],
    }

    system_prompt = (
        "你是台股科技供應鏈研究員。"
        "使用者會貼上英文財報電話會議或法說逐字稿片段。"
        "你的任務不是逐字翻譯，而是先用繁體中文做一段簡短摘要，"
        "然後把法說內容裡真正重要的英文關鍵字抓出來。"
        "請按照這五類輸出：瓶頸、下一代方向、Capex、需要的技術、專有名詞。"
        "每一筆都要保留英文詞、中文詞、中文解釋、原文依據，以及對應的台股供應鏈方向。"
        "要保守、具體、偏研究筆記，不要發明原文沒提到的內容。"
        "如果某一類沒有明確資訊，就回空陣列。"
    )
    return call_openai_structured_json(system_prompt, normalized_text, "transcript_excerpt_summary", schema)


def build_tracking_overview_stats(summary_df):
    if summary_df is None or summary_df.empty:
        return {"tracked_count": 0, "source_count": 0, "top_direction": "-", "direction_coverage": 0, "upcoming_events": 0}

    source_count = int(summary_df["抓到來源"].fillna(0).sum()) if "抓到來源" in summary_df.columns else 0
    direction_counter = {}
    for value in summary_df.get("台股方向", pd.Series(dtype="object")).fillna("-"):
        for part in str(value).split("、"):
            normalized = part.strip()
            if not normalized or normalized == "-":
                continue
            direction_counter[normalized] = direction_counter.get(normalized, 0) + 1

    if direction_counter:
        top_direction = max(direction_counter.items(), key=lambda item: item[1])[0]
        direction_coverage = len(direction_counter)
    else:
        top_direction = "-"
        direction_coverage = 0

    return {
        "tracked_count": int(len(summary_df)),
        "source_count": source_count,
        "top_direction": top_direction,
        "direction_coverage": direction_coverage,
        "upcoming_events": int(summary_df.get("一個月內活動", pd.Series(dtype="float")).fillna(0).sum()),
    }


def build_tracking_company_card_rows(valid_payloads):
    rows = []
    for company_query, payload in valid_payloads.items():
        bundle = payload.get("bundle") or {}
        analysis = payload.get("analysis") or {}
        sources = bundle.get("sources") or []
        rows.append(
            {
                "公司": company_query,
                "來源數": len(sources),
                "瓶頸數": len(analysis.get("bottleneck_keywords", []) or []),
                "技術詞數": len(analysis.get("needed_technology_keywords", []) or []) + len(analysis.get("proper_terms", []) or []),
                "Capex數": len(analysis.get("capex_keywords", []) or []),
                "台股方向": "、".join((analysis.get("overall_supply_chain") or [])[:3]) or "-",
                "接單台廠數": len((payload.get("order_bundle") or {}).get("matched_companies") or []),
                "一個月內活動數": len((payload.get("schedule_bundle") or {}).get("events") or []),
                "最近活動日": (((payload.get("schedule_bundle") or {}).get("events") or [{}])[0]).get("event_date_text", "-"),
                "摘要": analysis.get("summary_zh") or "目前沒有 AI 摘要。",
            }
        )
    return rows
