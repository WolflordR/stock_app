from __future__ import annotations

from industry_taxonomy import THEME_DEFINITIONS


MARKET_MAP_TAXONOMY_VERSION = "2026-05-market-map-step1-v1"

GROUP_DEFINITIONS = [
    {"name": "半導體", "sort_order": 10, "is_tech": True, "description": "晶圓製造、IC 設計、記憶體、封測與半導體設備。"},
    {"name": "AI伺服器與電腦系統", "sort_order": 20, "is_tech": True, "description": "AI 伺服器、ODM、邊緣運算、PC 與系統整機。"},
    {"name": "光學顯示", "sort_order": 30, "is_tech": True, "description": "面板、鏡頭、LED、光學模組與顯示技術。"},
    {"name": "網通通訊", "sort_order": 40, "is_tech": True, "description": "交換器、射頻、低軌衛星、矽光子與高速光通訊。"},
    {"name": "電子零組件", "sort_order": 50, "is_tech": True, "description": "PCB、載板、連接器、MLCC 與電子零件材料。"},
    {"name": "電子通路", "sort_order": 60, "is_tech": True, "description": "IC 與電子零組件代理分銷。"},
    {"name": "軟體資服", "sort_order": 70, "is_tech": True, "description": "企業軟體、資安、系統整合與 AI 應用服務。"},
    {"name": "電力基建與工業設備", "sort_order": 80, "is_tech": False, "description": "重電、工具機、自動化、線纜與工業設備。"},
    {"name": "車用", "sort_order": 90, "is_tech": False, "description": "車用電子、EV 與汽車零組件。"},
    {"name": "綠能環保", "sort_order": 100, "is_tech": False, "description": "太陽能、電池材料、儲能、環保與再生能源。"},
    {"name": "航運旅遊", "sort_order": 110, "is_tech": False, "description": "航空、航運與旅運服務。"},
    {"name": "生技醫療", "sort_order": 120, "is_tech": False, "description": "新藥、製藥、醫材、醫療通路與保健。"},
    {"name": "化學材料", "sort_order": 130, "is_tech": False, "description": "基礎化工、電子化學、樹脂、電池材料與塑化。"},
    {"name": "原物料", "sort_order": 140, "is_tech": False, "description": "鋼鐵、玻璃、陶瓷、橡膠與基礎原材料。"},
    {"name": "民生消費", "sort_order": 150, "is_tech": False, "description": "食品、飲料、紡織、家用消費與零售平台。"},
    {"name": "金融", "sort_order": 160, "is_tech": False, "description": "銀行、保險與金融服務。"},
    {"name": "建材營造", "sort_order": 170, "is_tech": False, "description": "建材、營造與工程相關題材。"},
    {"name": "綜合", "sort_order": 999, "is_tech": False, "description": "尚未細分或待後續整理的綜合題材。"},
]

GROUP_BY_PARENT_INDUSTRY = {
    "半導體業": "半導體",
    "電腦及週邊設備業": "AI伺服器與電腦系統",
    "光電業": "光學顯示",
    "通信網路業": "網通通訊",
    "電子零組件業": "電子零組件",
    "電子通路業": "電子通路",
    "資訊服務業": "軟體資服",
    "其他電子業": "電子零組件",
    "數位雲端": "軟體資服",
    "電機機械": "電力基建與工業設備",
    "電器電纜": "電力基建與工業設備",
    "汽車工業": "車用",
    "綠能環保": "綠能環保",
    "航運業": "航運旅遊",
    "生技醫療業": "生技醫療",
    "化學工業": "化學材料",
    "塑膠工業": "化學材料",
    "橡膠工業": "原物料",
    "玻璃陶瓷": "原物料",
    "鋼鐵工業": "原物料",
    "食品工業": "民生消費",
    "紡織纖維": "民生消費",
    "居家生活": "民生消費",
    "貿易百貨": "民生消費",
    "運動休閒": "民生消費",
    "文化創意業": "民生消費",
    "農業科技": "民生消費",
    "金融保險業": "金融",
    "金融業": "金融",
    "建材營造": "建材營造",
    "水泥工業": "建材營造",
    "油電燃氣業": "綠能環保",
    "造紙工業": "原物料",
    "存託憑證": "綜合",
    "其他": "綜合",
}

THEME_GROUP_OVERRIDES = {
    "AI伺服器": "AI伺服器與電腦系統",
    "伺服器ODM / 機櫃": "AI伺服器與電腦系統",
    "散熱 / 液冷": "AI伺服器與電腦系統",
    "BBU / 電源管理": "AI伺服器與電腦系統",
    "NB / PC品牌 / 電競": "AI伺服器與電腦系統",
    "邊緣AI / IPC": "AI伺服器與電腦系統",
    "EMS / 消費電子組裝": "AI伺服器與電腦系統",
    "網路平台 / 數位娛樂": "民生消費",
    "資服 / AI Agent": "軟體資服",
    "機器人 / 自動化": "電力基建與工業設備",
    "重電 / 電力設備": "電力基建與工業設備",
    "工具機": "電力基建與工業設備",
    "工業感測 / 製程自動化": "電力基建與工業設備",
    "太陽能 / 綠能光電": "綠能環保",
    "車用電子 / EV": "車用",
    "低軌衛星 / 微波通訊": "網通通訊",
    "矽光子 / CPO / 光通訊": "網通通訊",
}

FALLBACK_TOPIC_BY_INDUSTRY = {
    "水泥工業": "水泥建材 / 綜合",
    "食品工業": "食品民生 / 綜合",
    "塑膠工業": "塑化製品 / 綜合",
    "紡織纖維": "紡織纖維 / 綜合",
    "電機機械": "電機機械 / 綜合",
    "電器電纜": "電器電纜 / 綜合",
    "化學工業": "化學材料 / 綜合",
    "生技醫療業": "生技醫療 / 綜合",
    "玻璃陶瓷": "玻璃陶瓷 / 綜合",
    "鋼鐵工業": "鋼鐵材料 / 綜合",
    "橡膠工業": "橡膠製品 / 綜合",
    "汽車工業": "汽車零組件 / 綜合",
    "電子零組件業": "電子零組件 / 綜合",
    "電腦及週邊設備業": "電腦週邊設備 / 綜合",
    "半導體業": "半導體 / 綜合",
    "通信網路業": "通信網路 / 綜合",
    "電子通路業": "電子通路 / 綜合",
    "資訊服務業": "資訊服務 / 綜合",
    "其他電子業": "電子設備整合 / 綜合",
    "建材營造": "建材營造 / 綜合",
    "航運業": "航運物流 / 綜合",
    "觀光餐旅": "觀光餐旅 / 綜合",
    "金融保險業": "金融保險 / 綜合",
    "貿易百貨": "零售貿易 / 綜合",
    "油電燃氣業": "能源公用 / 綜合",
    "居家生活": "居家生活 / 綜合",
    "數位雲端": "數位雲端 / 綜合",
    "綠能環保": "綠能環保 / 綜合",
    "運動休閒": "運動休閒 / 綜合",
    "文化創意業": "文化創意 / 綜合",
    "農業科技": "農業科技 / 綜合",
    "存託憑證": "存託憑證 / 綜合",
    "金融業": "金融服務 / 綜合",
    "造紙工業": "造紙紙器 / 綜合",
    "其他": "綜合產業 / 綜合",
}


def resolve_group_name(theme_name: str, parent_industry: str, is_tech: bool) -> str:
    if theme_name in THEME_GROUP_OVERRIDES:
        return THEME_GROUP_OVERRIDES[theme_name]
    if parent_industry in GROUP_BY_PARENT_INDUSTRY:
        return GROUP_BY_PARENT_INDUSTRY[parent_industry]
    if is_tech:
        return "半導體"
    return "綜合"


def resolve_fallback_topic_name(industry: str) -> str:
    normalized = str(industry or "").strip()
    if not normalized:
        return "待確認 / 綜合標的"
    return FALLBACK_TOPIC_BY_INDUSTRY.get(normalized, f"{normalized} / 綜合")


def build_seed_topics():
    topics = []
    for index, definition in enumerate(THEME_DEFINITIONS, start=1):
        theme_name = str(definition["theme"]).strip()
        parent_industry = str(definition.get("parent_industry") or "").strip()
        is_tech = bool(definition.get("is_tech"))
        topics.append(
            {
                "topic_name": theme_name,
                "display_name": theme_name,
                "group_name": resolve_group_name(theme_name, parent_industry, is_tech),
                "parent_industry": parent_industry,
                "topic_type": "seed",
                "is_tech": is_tech,
                "description": "、".join(str(keyword).strip() for keyword in definition.get("keywords", []) if str(keyword).strip()),
                "news_query": str(definition.get("news_query") or "").strip(),
                "sort_order": index * 10,
                "keywords": [str(keyword).strip() for keyword in definition.get("keywords", []) if str(keyword).strip()],
                "aliases": [str(alias).strip() for alias in definition.get("aliases", []) if str(alias).strip()],
                "codes": [str(code).strip().zfill(4) for code in definition.get("codes", []) if str(code).strip()],
            }
        )
    return topics
