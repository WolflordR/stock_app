from __future__ import annotations

import pandas as pd


VALUE_CHAIN_PRESETS = {
    "被動元件 / MLCC": {
        "upstream": ["電子化學材料 / 樹脂", "銅箔基板 / CCL", "半導體 / 綜合"],
        "midstream": ["被動元件 / MLCC"],
        "downstream": ["AI伺服器", "車用電子 / EV", "邊緣AI / IPC"],
    },
    "ASIC / IC設計": {
        "upstream": ["晶圓代工 / 特用製程", "CoWoS / 先進封裝", "ABF載板"],
        "midstream": ["ASIC / IC設計"],
        "downstream": ["AI伺服器", "網通 / 交換器", "邊緣AI / IPC"],
    },
    "CoWoS / 先進封裝": {
        "upstream": ["晶圓代工 / 特用製程", "半導體設備", "ABF載板"],
        "midstream": ["CoWoS / 先進封裝"],
        "downstream": ["ASIC / IC設計", "AI伺服器", "矽光子 / CPO / 光通訊"],
    },
    "矽光子 / CPO / 光通訊": {
        "upstream": ["ASIC / IC設計", "CoWoS / 先進封裝", "半導體 / 綜合"],
        "midstream": ["矽光子 / CPO / 光通訊"],
        "downstream": ["網通 / 交換器", "AI伺服器", "低軌衛星 / 微波通訊"],
    },
    "散熱 / 液冷": {
        "upstream": ["重電 / 電力設備", "電子零組件 / 綜合", "塑化製品 / 綜合"],
        "midstream": ["散熱 / 液冷"],
        "downstream": ["AI伺服器", "車用電子 / EV", "邊緣AI / IPC"],
    },
    "AI伺服器": {
        "upstream": ["ASIC / IC設計", "CoWoS / 先進封裝", "散熱 / 液冷"],
        "midstream": ["AI伺服器", "伺服器ODM / 機櫃"],
        "downstream": ["邊緣AI / IPC", "網通 / 交換器", "數位雲端 / 綜合"],
    },
    "ABF載板": {
        "upstream": ["電子化學材料 / 樹脂", "銅箔基板 / CCL", "玻璃纖維 / 材料"],
        "midstream": ["ABF載板"],
        "downstream": ["ASIC / IC設計", "CoWoS / 先進封裝", "AI伺服器"],
    },
}


GROUP_DOWNSTREAM_FALLBACKS = {
    "半導體": ["AI伺服器", "邊緣AI / IPC", "網通 / 交換器"],
    "電子零組件": ["AI伺服器", "車用電子 / EV", "邊緣AI / IPC"],
    "網通通訊": ["AI伺服器", "低軌衛星 / 微波通訊", "數位雲端 / 綜合"],
    "AI伺服器與電腦系統": ["邊緣AI / IPC", "網通 / 交換器", "數位雲端 / 綜合"],
    "電力基建與工業設備": ["AI伺服器", "綠能環保 / 綜合", "車用電子 / EV"],
}


def _topic_lookup(topic_snapshot_df):
    if topic_snapshot_df is None or topic_snapshot_df.empty:
        return {}
    return {
        str(row["topic_name"]): row.to_dict()
        for _, row in topic_snapshot_df.iterrows()
    }


def _topic_card_payload(topic_name, lookup):
    row = lookup.get(topic_name)
    if not row:
        return None
    return {
        "topic_name": topic_name,
        "parent_industry": row.get("parent_industry") or "",
        "avg_change_pct": row.get("avg_change_pct"),
        "representative_stocks": row.get("representative_stocks") or "-",
    }


def _generic_chain(topic_row, topic_snapshot_df):
    group_name = str(topic_row.get("group_name") or "")
    topic_name = str(topic_row.get("topic_name") or "")
    same_group_df = topic_snapshot_df[topic_snapshot_df["group_name"] == group_name].copy()
    same_group_df = same_group_df[same_group_df["topic_name"] != topic_name]
    upstream_topics = same_group_df.sort_values(["total_turnover", "heat_score"], ascending=[False, False])["topic_name"].head(2).tolist()
    downstream_topics = GROUP_DOWNSTREAM_FALLBACKS.get(group_name, [])[:3]
    return {
        "upstream": upstream_topics,
        "midstream": [topic_name],
        "downstream": downstream_topics,
    }


def build_topic_value_chain(topic_row, topic_snapshot_df):
    if not topic_row or topic_snapshot_df is None or topic_snapshot_df.empty:
        return []

    topic_name = str(topic_row.get("topic_name") or "")
    lookup = _topic_lookup(topic_snapshot_df)
    preset = VALUE_CHAIN_PRESETS.get(topic_name) or _generic_chain(topic_row, topic_snapshot_df)

    sections = []
    for section_name, display_name in [
        ("upstream", "上游"),
        ("midstream", "中游"),
        ("downstream", "下游"),
    ]:
        items = []
        for related_topic in preset.get(section_name, []):
            payload = _topic_card_payload(related_topic, lookup)
            if payload:
                items.append(payload)
        sections.append(
            {
                "key": section_name,
                "title": display_name,
                "items": items,
            }
        )
    return sections
