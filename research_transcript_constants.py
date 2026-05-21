import re


TRANSCRIPT_SHORTCUTS = [
    {"label": "NVIDIA", "symbol": "NVDA", "transcript_url": "https://seekingalpha.com/symbol/NVDA/earnings/transcripts"},
    {"label": "Microsoft", "symbol": "MSFT", "transcript_url": "https://seekingalpha.com/symbol/MSFT/earnings/transcripts"},
    {"label": "TSMC", "symbol": "TSM", "transcript_url": "https://seekingalpha.com/symbol/TSM/earnings/transcripts"},
    {"label": "Apple", "symbol": "AAPL", "transcript_url": "https://seekingalpha.com/symbol/AAPL/earnings/transcripts"},
    {"label": "Amazon", "symbol": "AMZN", "transcript_url": "https://seekingalpha.com/symbol/AMZN/earnings/transcripts"},
    {"label": "Alphabet", "symbol": "GOOGL", "transcript_url": "https://seekingalpha.com/symbol/GOOGL/earnings/transcripts"},
    {"label": "Meta", "symbol": "META", "transcript_url": "https://seekingalpha.com/symbol/META/earnings/transcripts"},
    {"label": "Tesla", "symbol": "TSLA", "transcript_url": "https://seekingalpha.com/symbol/TSLA/earnings/transcripts"},
]

TRANSCRIPT_KEYWORD_GROUPS = [
    {
        "group": "Bottleneck / Constraint",
        "keywords": ["bottleneck", "constrained", "constraint", "shortage", "lead time", "supply tightness"],
        "focus": "抓缺貨、瓶頸、交期拉長，通常代表下一個最先缺的零組件。",
    },
    {
        "group": "Next Generation / Roadmap",
        "keywords": ["next generation", "roadmap", "next platform", "new architecture", "transition"],
        "focus": "抓下一代規格、封裝、互連或散熱架構會往哪裡走。",
    },
    {
        "group": "Capex / Buildout",
        "keywords": ["capex", "capital expenditure", "buildout", "deployment", "investment"],
        "focus": "抓公司把錢砸在哪，通常是下一波最確定的需求方向。",
    },
]

TERM_GLOSSARY = [
    {"term": "CoWoS", "meaning": "Chip-on-Wafer-on-Substrate 先進封裝", "why_it_matters": "AI GPU / ASIC 出貨瓶頸常卡在這裡", "taiwan_link": "先進封裝、ABF載板、封測"},
    {"term": "HBM", "meaning": "High Bandwidth Memory 高頻寬記憶體", "why_it_matters": "AI 算力提升時最容易被點名", "taiwan_link": "記憶體、封裝測試、基板"},
    {"term": "CPO", "meaning": "Co-Packaged Optics 共封裝光學", "why_it_matters": "解高速互連與功耗問題", "taiwan_link": "矽光子、光通訊、交換器"},
    {"term": "Silicon Photonics", "meaning": "矽光子", "why_it_matters": "AI 傳輸升級的核心名詞", "taiwan_link": "光通訊、CPO、晶圓代工"},
    {"term": "Retimer", "meaning": "高速訊號重整晶片", "why_it_matters": "高速傳輸升級時常被帶出", "taiwan_link": "高速傳輸 IC、交換器"},
    {"term": "Switch ASIC", "meaning": "交換器專用晶片", "why_it_matters": "資料中心網路升級時會放量", "taiwan_link": "網通、交換器、ASIC"},
    {"term": "Liquid Cooling", "meaning": "液冷散熱", "why_it_matters": "GPU 功耗升高後的直接受惠方向", "taiwan_link": "散熱、冷卻模組、機殼"},
    {"term": "TDP", "meaning": "Thermal Design Power 散熱設計功耗", "why_it_matters": "功耗往上就是散熱商機", "taiwan_link": "散熱、電源、伺服器"},
    {"term": "Rack Scale", "meaning": "整櫃級架構", "why_it_matters": "代表需求從單機走向整櫃建置", "taiwan_link": "伺服器、機櫃、電源、散熱"},
    {"term": "BBU", "meaning": "Battery Backup Unit 備援電池模組", "why_it_matters": "AI 資料中心供電穩定的重要配件", "taiwan_link": "BBU、電源管理、儲能"},
    {"term": "Power Delivery", "meaning": "供電架構 / 配電", "why_it_matters": "算力提升後常往電力基礎設施延伸", "taiwan_link": "電源、重電、BBU"},
    {"term": "HVDC", "meaning": "High-Voltage Direct Current 高壓直流", "why_it_matters": "資料中心供電新架構常見詞", "taiwan_link": "重電、電源管理、資料中心"},
    {"term": "Yield", "meaning": "良率", "why_it_matters": "法說只要提良率卡關，通常供應鏈機會很大", "taiwan_link": "設備、材料、封裝測試"},
    {"term": "Qualification", "meaning": "客戶驗證 / 認證", "why_it_matters": "代表新供應商或新規格要開始放量前的前哨", "taiwan_link": "新供應鏈切入、新材料"},
    {"term": "Ramp", "meaning": "放量爬坡", "why_it_matters": "從試產走向正式出貨的關鍵字", "taiwan_link": "整體供應鏈同步受惠"},
]

KEYWORD_GROUP_DIRECTIONS = {
    "Bottleneck / Constraint": ["先進封裝", "設備", "材料", "ABF載板", "光通訊", "散熱"],
    "Next Generation / Roadmap": ["CPO", "矽光子", "HBM", "液冷", "新平台供應鏈"],
    "Capex / Buildout": ["資料中心", "伺服器", "重電", "BBU", "交換器"],
}

DEFAULT_RESEARCH_COMPANIES = [
    "NVIDIA",
    "Microsoft",
    "Amazon",
    "Alphabet",
    "Meta",
    "Apple",
    "Tesla",
    "AMD",
    "Broadcom",
    "TSMC",
]

ORDER_SEARCH_KEYWORDS = [
    "taiwan supplier",
    "taiwan supply chain",
    "order supplier taiwan",
    "manufacturing partner taiwan",
    "server supplier taiwan",
    "component supplier taiwan",
]

COMPANY_TICKER_MAP = {
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "alphabet": "GOOGL",
    "googl": "GOOGL",
    "google": "GOOGL",
    "meta": "META",
    "meta platforms": "META",
    "apple": "AAPL",
    "aapl": "AAPL",
    "tesla": "TSLA",
    "tsla": "TSLA",
    "amd": "AMD",
    "advanced micro devices": "AMD",
    "broadcom": "AVGO",
    "avgo": "AVGO",
    "tsmc": "TSM",
    "tsm": "TSM",
    "taiwan semiconductor": "TSM",
}

EVENT_SEARCH_KEYWORDS = [
    "earnings date investor relations",
    "earnings call date",
    "investor relations calendar",
    "conference event calendar",
    "keynote event",
    "product launch event",
]

EVENT_MONTH_PATTERN = re.compile(
    r"\b(?:"
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
    r")\s+\d{1,2}(?:,\s*|\s+)(?:20\d{2})?\b",
    re.IGNORECASE,
)
EVENT_ISO_PATTERN = re.compile(r"\b20\d{2}-\d{1,2}-\d{1,2}\b")
EVENT_SLASH_PATTERN = re.compile(r"\b(?:20\d{2}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2}/20\d{2})\b")
