from __future__ import annotations

import pandas as pd

from modules.news.news_ai import call_openai_structured_json, get_llm_backend_label, has_llm_backend
from modules.research.transcript_search import _normalize_text


def _fallback_keyword_analysis(text):
    patterns = {
        "bottlenecks": ["bottleneck", "constrained", "shortage", "lead time", "constraint"],
        "next_generation": ["next generation", "roadmap", "new architecture", "transition", "next platform"],
        "capex": ["capex", "capital expenditure", "investment", "buildout", "deployment"],
        "technology": ["CPO", "silicon photonics", "HBM", "liquid cooling", "CoWoS", "NVLink", "Ethernet", "BBU", "HVDC"],
    }
    lowered = text.lower()
    result = {}
    for key, keywords in patterns.items():
        result[key] = [keyword for keyword in keywords if keyword.lower() in lowered]
    return result


def _build_local_source_digest(bundle, max_chars_per_source=1200):
    sections = []
    for index, source in enumerate(bundle.get("sources") or [], start=1):
        excerpt = _normalize_text(source.get("extracted_text") or "")[:max_chars_per_source]
        snippet = _normalize_text(source.get("snippet") or "")
        sections.append(
            f"[Source {index}] {source.get('title')}\n"
            f"Snippet: {snippet}\n"
            f"Excerpt: {excerpt}"
        )
    return "\n\n".join(sections).strip()


def _build_fallback_result(combined_text):
    fallback = _fallback_keyword_analysis(combined_text)
    return {
        "summary_zh": "目前先用本地 fallback 規則整理出可能的重點關鍵字，建議搭配下方抓到的原文來源一起看。",
        "bottleneck_keywords": [{"keyword_en": item, "keyword_zh": "", "meaning": "", "evidence_excerpt": "", "taiwan_supply_chain": []} for item in fallback["bottlenecks"]],
        "next_generation_keywords": [{"keyword_en": item, "keyword_zh": "", "meaning": "", "evidence_excerpt": "", "taiwan_supply_chain": []} for item in fallback["next_generation"]],
        "capex_keywords": [{"keyword_en": item, "keyword_zh": "", "meaning": "", "evidence_excerpt": "", "taiwan_supply_chain": []} for item in fallback["capex"]],
        "needed_technology_keywords": [{"keyword_en": item, "keyword_zh": "", "meaning": "", "evidence_excerpt": "", "taiwan_supply_chain": []} for item in fallback["technology"]],
        "proper_terms": [],
        "overall_supply_chain": [],
        "research_takeaway": "本地模型暫時沒有穩定輸出完整結構化結果時，會先保底列出英文關鍵字候選。",
    }


def analyze_earnings_call_bundle(bundle):
    combined_text = _normalize_text(bundle.get("combined_text"))
    if not combined_text:
        return None

    if not has_llm_backend():
        fallback_result = _build_fallback_result(combined_text)
        fallback_result["summary_zh"] = "目前沒有可用的 AI backend，先顯示抓到的來源與英文關鍵字候選。"
        fallback_result["research_takeaway"] = "若要自動轉成中文研究摘要，請啟用 OpenAI 或本地 Ollama。"
        return fallback_result

    backend_label = get_llm_backend_label() or ""
    use_local_backend = backend_label.startswith("Ollama")

    full_schema = {
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

    local_schema = {
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
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "taiwan_supply_chain"],
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
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "taiwan_supply_chain"],
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
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "taiwan_supply_chain"],
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
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "taiwan_supply_chain"],
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
                        "taiwan_supply_chain": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["keyword_en", "keyword_zh", "meaning", "taiwan_supply_chain"],
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
        "你會收到系統從英文網頁抓回來的 earnings call transcript、investor relations release、earnings coverage 內容。"
        "先用繁體中文做精簡摘要，再抓出真正重要的英文關鍵字。"
        "請分成：瓶頸 / 受限、下一代方向、Capex、需要的技術、專有名詞。"
        "每一筆都要保留英文詞、中文詞、中文解釋、原文依據，以及對應的台股供應鏈方向。"
        "不要逐字翻譯整篇；只保留對研究最有價值的資訊。"
        "如果資料像新聞整理而不是逐字稿，也可以照樣抽取，但要保守。"
    )
    if use_local_backend:
        system_prompt = (
            "你是台股科技供應鏈研究員。"
            "根據英文法說或會議摘錄，請用繁體中文做短摘要，並抓出最重要的英文關鍵字。"
            "重點放在瓶頸、下一代方向、Capex、需要的技術、專有名詞。"
            "不用逐字翻譯，不確定就少寫。"
        )
        user_prompt = (
            f"Company query: {bundle.get('company_query')}\n\n"
            f"Sources digest:\n{_build_local_source_digest(bundle, max_chars_per_source=900)[:5000]}"
        )
        result = call_openai_structured_json(
            system_prompt,
            user_prompt,
            "web_fetched_earnings_call_analysis_local",
            local_schema,
        )
        return result or _build_fallback_result(combined_text)

    user_prompt = (
        f"Company query: {bundle.get('company_query')}\n\n"
        f"Fetched sources:\n{pd.DataFrame(bundle.get('sources') or []).to_json(force_ascii=False, orient='records')}\n\n"
        f"Combined content:\n{combined_text[:14000]}"
    )
    return call_openai_structured_json(
        system_prompt,
        user_prompt,
        "web_fetched_earnings_call_analysis",
        full_schema,
    )
