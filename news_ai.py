import json
import os
from functools import lru_cache

import requests

from company_links_db import THEME_DEFINITIONS


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_NEWS_MODEL = "gpt-5-mini"
OLLAMA_GENERATE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
OLLAMA_TAGS_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b").strip() or "qwen3:4b"


def get_openai_api_key():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return api_key or None


@lru_cache(maxsize=1)
def get_local_llm_model():
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=10)
        response.raise_for_status()
        models = response.json().get("models") or []
        available_models = [str(item.get("name") or "").strip() for item in models if str(item.get("name") or "").strip()]
        if DEFAULT_OLLAMA_MODEL in available_models:
            return DEFAULT_OLLAMA_MODEL
        if available_models:
            return available_models[0]
    except Exception:
        return None
    return None


def has_llm_backend():
    return bool(get_openai_api_key() or get_local_llm_model())


def get_llm_backend_label():
    if get_openai_api_key():
        return "OpenAI"
    if get_local_llm_model():
        return f"Ollama ({get_local_llm_model()})"
    return None


def _extract_response_text(payload):
    output_text = payload.get("output_text")
    if output_text:
        return output_text

    text_parts = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                text_parts.append(content["text"])
    return "".join(text_parts).strip()


def _extract_json_payload(text):
    normalized = str(text or "").strip()
    if not normalized:
        return None
    try:
        return json.loads(normalized)
    except Exception:
        pass

    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(normalized[start : end + 1])
    except Exception:
        return None


@lru_cache(maxsize=128)
def _call_openai_structured_json_cached(model, system_prompt, user_prompt, schema_name, schema_json):
    api_key = get_openai_api_key()
    if not api_key:
        return None

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_prompt,
                    }
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": json.loads(schema_json),
                "strict": True,
            }
        },
    }
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    response_payload = response.json()
    raw_text = _extract_response_text(response_payload)
    if not raw_text:
        return None
    return json.loads(raw_text)


def call_openai_structured_json(system_prompt, user_prompt, schema_name, schema, model=None):
    api_key = get_openai_api_key()
    if api_key:
        resolved_model = model or os.getenv("OPENAI_NEWS_MODEL", DEFAULT_OPENAI_NEWS_MODEL).strip() or DEFAULT_OPENAI_NEWS_MODEL
        schema_json = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        try:
            return _call_openai_structured_json_cached(
                resolved_model,
                system_prompt,
                user_prompt,
                schema_name,
                schema_json,
            )
        except Exception:
            return None

    try:
        return call_local_structured_json(
            system_prompt,
            user_prompt,
            schema_name,
            schema,
            model=model,
        )
    except Exception:
        return None


def call_local_structured_json(system_prompt, user_prompt, schema_name, schema, model=None):
    resolved_model = model or get_local_llm_model()
    if not resolved_model:
        return None

    prompt = (
        "You are a careful analyst.\n"
        "Return one JSON object only. Do not include markdown fences, notes, or extra text.\n"
        f"Schema name: {schema_name}\n"
        f"JSON schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"System instructions:\n{system_prompt}\n\n"
        f"User input:\n{user_prompt}\n"
    )
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json={
            "model": resolved_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        },
        timeout=180,
    )
    response.raise_for_status()
    raw_text = (response.json() or {}).get("response") or ""
    return _extract_json_payload(raw_text)


def build_ai_news_section_analysis(section_name, items, focus_hint):
    if not items or not has_llm_backend():
        return None

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "section_summary": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "tone": {"type": "string", "enum": ["偏利多", "偏利空", "偏中性"]},
                        "analysis": {"type": "string"},
                        "taiwan_themes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "tone", "analysis", "taiwan_themes"],
                },
            },
        },
        "required": ["section_summary", "items"],
    }

    serializable_items = []
    for item in items:
        reaction = item.get("reaction") or {}
        serializable_items.append(
            {
                "title": item.get("title"),
                "title_zh": item.get("title_zh"),
                "source": item.get("source"),
                "published_at": item.get("published_at"),
                "qqq_reaction_date": reaction.get("reaction_date"),
                "qqq_one_day_pct": reaction.get("one_day_pct"),
                "qqq_three_day_pct": reaction.get("three_day_pct"),
            }
        )

    system_prompt = (
        "你是台股與美股跨市場新聞分析助手。"
        "你要用繁體中文，根據新聞標題、來源、時間與 QQQ 市場反應，"
        "寫出簡潔、實戰導向的新聞摘要。"
        "不要假裝看過內文全文；只能根據提供的資訊做保守推論。"
        "如果資訊不足，要明確說不確定。"
    )
    user_prompt = json.dumps(
        {
            "section_name": section_name,
            "focus_hint": focus_hint,
            "available_taiwan_themes": [definition["theme"] for definition in THEME_DEFINITIONS],
            "items": serializable_items,
        },
        ensure_ascii=False,
    )
    return call_openai_structured_json(
        system_prompt,
        user_prompt,
        f"{section_name.lower().replace(' ', '_')}_analysis",
        schema,
    )
