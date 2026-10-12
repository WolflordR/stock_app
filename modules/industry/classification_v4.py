"""Evidence-backed v4 L3 classification and independent primary/membership records."""
from __future__ import annotations

import csv
import re
import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.core.project_paths import data_path
from modules.industry.electronics_universe import DB_PATH
from modules.industry.fine_classification import _connection, _key, normalize_name, fetch_business
from modules.industry.official_company_evidence import init_evidence_db

PACKAGE = data_path('sector_rotation/v4')
REVIEW_FILE = data_path('review_queue_after_v4.csv')


def _csv(name: str) -> list[dict]:
    with (PACKAGE / name).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def init_classification_v4(path: Path = DB_PATH) -> None:
    init_evidence_db(path)
    with _connection(path) as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS stock_primary_sector (
          market TEXT NOT NULL,stock_id TEXT NOT NULL,sector_key TEXT NOT NULL,
          source TEXT NOT NULL,source_url TEXT,confidence REAL NOT NULL,
          valid_from TEXT NOT NULL,valid_to TEXT,updated_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id));
        CREATE INDEX IF NOT EXISTS idx_stock_primary_sector ON stock_primary_sector(sector_key);
        CREATE TABLE IF NOT EXISTS stock_sector_memberships (
          market TEXT NOT NULL,stock_id TEXT NOT NULL,sector_key TEXT NOT NULL,
          source TEXT NOT NULL,source_url TEXT,confidence REAL NOT NULL,
          valid_from TEXT NOT NULL,valid_to TEXT,updated_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id,sector_key,source));
        CREATE INDEX IF NOT EXISTS idx_stock_sector_memberships_sector
          ON stock_sector_memberships(sector_key,market,stock_id);
        CREATE TABLE IF NOT EXISTS classification_review_v4 (
          market TEXT NOT NULL,stock_id TEXT NOT NULL,reason TEXT NOT NULL,
          possible_category TEXT,updated_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id));
        CREATE TABLE IF NOT EXISTS stock_classification_levels (
          market TEXT NOT NULL,stock_id TEXT NOT NULL,l1 TEXT NOT NULL,l2 TEXT,
          source TEXT NOT NULL,updated_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id,l1,l2));
        ''')


def refresh_mops_business(*, path: Path = DB_PATH, max_workers: int = 16) -> dict:
    """Fetch MOPS company-submitted mainBusiness for any target without a cached row."""
    with _connection(path) as conn:
        work=conn.execute('''SELECT c.market,c.stock_id FROM fine_companies c
          WHERE c.active=1 AND c.is_target=1 AND NOT EXISTS (
          SELECT 1 FROM fine_business b WHERE b.market=c.market AND b.stock_id=c.stock_id)''').fetchall()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        rows=[f.result() for f in as_completed([pool.submit(fetch_business,*key) for key in work])]
    now=datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    with _connection(path) as conn:
        conn.executemany('''INSERT INTO fine_business VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(market,stock_id) DO UPDATE SET main_business=excluded.main_business,
          description=excluded.description,source_url=excluded.source_url,
          fetch_status=excluded.fetch_status,fetched_at=excluded.fetched_at''',
          [(r['market'],r['stock_id'],r['main_business'],r['description'],r['source_url'],r['fetch_status'],now)
           for r in rows])
    return {'requests':len(work),'ok':sum(r['fetch_status']=='ok' for r in rows)}


# These are explicit translations of concrete TPEx company-chain items. Generic
# "other" nodes and investment themes are kept in the raw evidence snapshot.
CHAIN_VERTICAL = {
    '半導體': '半導體', '印刷電路板': 'PCB', '連接器': '連接器',
    '被動元件': '被動元件', '通信網路': '網通',
    '電腦及週邊設備': '電腦及週邊', '平面顯示器': '顯示/光學',
    'LED照明產業': 'LED', '軟體服務': '軟體服務',
    '資通訊安全': '資安', '太陽能產業': '太陽能',
    '能源元件': '能源元件', '觸控面板': '顯示/光學',
    '太空衛星科技': '網通', '電動車輛產業': '電動車',
}
THEME_VERTICAL = {'人工智慧','大數據','雲端運算','汽車','醫療器材','電子商務',
                  '金融科技','智慧電網','其他','體驗科技','休閒娛樂','電機機械',
                  '建材營造','石化及塑橡膠','鋼鐵'}
GENERIC_ITEMS = {'其他','其他零組件','其他電腦及週邊設備','其他電腦及週邊設備之零組件',
                 '其他電子產品及電子服務產業','主/被動元件','生產製程、檢測設備及原物料',
                 '其他IC/二極體製造','硬板、軟板、IC載板製造',
                 '印表機、傳真機、掃瞄器、多功能事務機、投影機',
                 '大功率鋰電池芯/模組、電池管理系統、動力馬達等零組件'}

ITEM_PATHS = {
    ('被動元件','電容器'): ('被動元件','電容','電容器'),
    ('被動元件','電阻器'): ('被動元件','電阻','電阻器'),
    ('被動元件','電感器'): ('被動元件','電感','電感器'),
    ('被動元件','濾波器、振盪器'): ('被動元件','濾波器','濾波器/振盪器'),
    ('電腦及週邊設備','光學鏡片、鏡頭'): ('顯示/光學','光學元件','光學鏡片/鏡頭'),
    ('電腦及週邊設備','散熱片、風扇馬達、散熱模組'): ('散熱','散熱模組','散熱模組/風扇'),
    ('電腦及週邊設備','機殼'): ('電腦及週邊','機構件','機殼'),
    ('電腦及週邊設備','電源供應器'): ('電源','電源供應器','電源供應器'),
    ('電腦及週邊設備','工業電腦'): ('電腦及週邊','工業電腦','工業電腦'),
    ('電腦及週邊設備','機構樞紐'): ('電腦及週邊','機構件','樞紐/轉軸'),
    ('電腦及週邊設備','筆記型電腦'): ('電腦及週邊','電腦系統','筆記型電腦'),
    ('電腦及週邊設備','桌上型電腦'): ('電腦及週邊','電腦系統','桌上型電腦'),
    ('電腦及週邊設備','主機板'): ('電腦及週邊','電腦零組件','主機板'),
    ('電腦及週邊設備','連接線'): ('連接器','線材','連接線/線束'),
    ('電腦及週邊設備','光碟片'): ('電腦及週邊','儲存媒體','光碟片'),
    ('電腦及週邊設備','硬碟機'): ('電腦及週邊','儲存設備','硬碟機'),
    ('電腦及週邊設備','記憶體'): ('半導體','記憶體','記憶體模組'),
    ('半導體','IC通路'): ('半導體','通路','IC通路'),
    ('半導體','消費性IC'): ('半導體','IC設計','消費性IC'),
    ('半導體','電源管理IC'): ('半導體','IC設計','PMIC/Power IC'),
    ('半導體','微控制器IC'): ('半導體','IC設計','CPU/MCU'),
    ('半導體','網路通訊IC'): ('半導體','IC設計','網路通訊IC'),
    ('半導體','平面顯示器驅動IC'): ('半導體','IC設計','Driver IC'),
    ('半導體','LED驅動IC'): ('半導體','IC設計','LED驅動IC'),
    ('半導體','IC封裝測試'): ('半導體','封裝測試','IC封裝測試'),
    ('半導體','生產製程及檢測設備'): ('半導體','設備','製程與檢測設備'),
    ('半導體','晶圓製造'): ('半導體','晶圓製造','晶圓製造'),
    ('半導體','化學品'): ('半導體','材料','半導體化學品'),
    ('半導體','IP設計/IC設計代工服務'): ('半導體','IC設計服務','IP/設計服務'),
    ('印刷電路板','銅箔基板'): ('PCB','上游材料','銅箔基板'),
    ('印刷電路板','生產製程及檢測設備'): ('PCB','設備','PCB製程與檢測設備'),
    ('印刷電路板','基板組裝加工及相關製造'): ('PCB','組裝加工','基板組裝加工'),
    ('連接器','連接器設計、組裝及製造'): ('連接器','製造','連接器'),
    ('通信網路','網路設備(如數據機、網路卡、閘道器、路由器、網路電話)'): ('網通','網路設備','路由器/交換器/數據機'),
    ('通信網路','無線通訊設備(如行動電話、衛星定位系統、衛星通訊設備、微波通訊設備、數位機上盒)'): ('網通','無線通訊設備','無線通訊設備'),
    ('通信網路','光通訊設備(如光纖電纜、光傳輸設備)'): ('光通訊','設備','光通訊設備'),
    ('通信網路','線材'): ('連接器','線材','通信線材'),
    ('平面顯示器','面板'): ('顯示/光學','顯示面板','面板'),
    ('平面顯示器','顯示器模組'): ('顯示/光學','顯示模組','顯示器模組'),
    ('平面顯示器','監視器/顯示器'): ('顯示/光學','顯示器','監視器/顯示器'),
    ('觸控面板','觸控面板'): ('顯示/光學','觸控面板','觸控面板'),
    ('LED照明產業','燈具/應用'): ('LED','照明','燈具/照明應用'),
    ('LED照明產業','封裝/模組'): ('LED','封裝模組','LED封裝/模組'),
    ('LED照明產業','光源/磊晶'): ('LED','上游','LED磊晶/光源'),
    ('軟體服務','系統整合服務'): ('軟體服務','系統整合','系統整合服務'),
    ('軟體服務','應用/系統軟體設計開發'): ('軟體服務','軟體開發','應用/系統軟體'),
    ('軟體服務','資料處理服務'): ('軟體服務','資料服務','資料處理服務'),
    ('資通訊安全','網路安全防護'): ('資安','網路安全','網路安全防護'),
    ('資通訊安全','端點安全防護'): ('資安','端點安全','端點安全防護'),
    ('資通訊安全','資料安全'): ('資安','資料安全','資料安全'),
    ('太陽能產業','太陽能電池'): ('太陽能','電池','太陽能電池'),
    ('太陽能產業','太陽能電池模組'): ('太陽能','模組','太陽能模組'),
    ('太陽能產業','太陽能發電設備/系統及系統工程'): ('太陽能','系統工程','太陽能電廠工程'),
    ('太陽能產業','太陽能電廠'): ('太陽能','電廠','太陽能電廠'),
    ('能源元件','電池模組'): ('能源元件','電池','電池模組'),
    ('太空衛星科技','天線/射頻基頻'): ('網通','衛星通訊','天線/射頻基頻'),
}


def _chain_path(vertical: str, item: str) -> tuple[str,str,str] | None:
    if vertical in THEME_VERTICAL or vertical not in CHAIN_VERTICAL or item in GENERIC_ITEMS:
        return None
    explicit = ITEM_PATHS.get((vertical,item))
    if explicit:
        return explicit
    if any(token in item for token in ('其他','及相關','等零組件','如','、')):
        return None
    if len(item) > 32 or len(item) < 2:
        return None
    # The official company-chain item itself is an L3 only when it names a
    # specific product/service, never the broad industry code.
    return CHAIN_VERTICAL[vertical], vertical, item


def _text_score(path: tuple[str,str,str], product: str, business: str) -> float:
    l1,l2,l3 = path
    candidates = [l3]
    aliases = {
        '製程與檢測設備': ['製程設備','檢測設備','半導體設備','測試設備'],
        'IC封裝測試': ['封裝','測試服務'], '路由器/交換器/數據機': ['路由器','交換器','數據機','網通設備'],
        '無線通訊設備': ['無線通訊','衛星通訊','微波通訊','行動電話'],
        '光通訊設備': ['光通訊','光纖','光傳輸'],
        '應用/系統軟體': ['應用軟體','系統軟體','軟體開發'],
        '系統整合服務': ['系統整合','系統集成'],
        'PMIC/Power IC': ['電源管理IC','電源管理晶片','Power IC'],
        'CPU/MCU': ['微控制器','MCU'],
        '散熱模組/風扇': ['散熱','風扇','熱管'],
        '光學鏡片/鏡頭': ['光學鏡頭','光學鏡片','相機鏡頭','鏡頭'],
        '連接線/線束': ['連接線','線束','纜線'],
        '銅箔基板': ['銅箔基板','CCL'],
        '工業電腦': ['工業電腦','IPC'],
        '太陽能電廠工程': ['太陽能電廠','太陽能發電系統'],
        'IC通路': ['IC通路','半導體通路','電子零組件代理'],
        '監視器/顯示器': ['顯示器','液晶顯示器','LCD TV'],
        '顯示器模組': ['顯示器模組','液晶顯示器模組','LCM'],
        '液晶顯示模組': ['液晶顯示器模組','LCM'],
        '玻璃纖維/玻纖布': ['玻璃纖維布','玻纖布','玻璃纖維紗'],
        'PCB製程與檢測設備': ['PCB製程','電路板自動檢測','自動光學檢測','曝光機'],
        '連接器': ['連接器','端子'],
        '連接器設計/組裝/製造': ['連接器','端子'],
        '顯示製程/檢測設備': ['顯示器製程','LCD製程'],
        '機殼': ['機殼','外殼','金屬機殼'],
        '晶圓製造': ['晶圓製造服務','晶圓代工'],
        '雷射膜': ['雷射膜'],
        '家庭劇院/音響': ['Home Theater System','音響系統'],
        '功率分離式元件': ['分離式元器件','功率分離式元件'],
        '讀卡機/POS終端': ['讀卡機','POS','銷售點終端機'],
        '變壓器線架': ['變壓器線架'],
        '電子銲錫材料': ['銲錫','錫膏'],
        '砷化鎵/磷化銦磊晶': ['砷化鎵','磷化銦','GaAs','InP'],
        '影像感測模組': ['影像感測器模組','CIS','線性感測模組'],
        '薄膜觸控開關': ['薄膜觸控開關'],
        '鐵氧體磁芯': ['鐵氧磁','磁鐵芯'],
    }
    candidates += aliases.get(l3, [])
    headings=[line.split('；',1)[0].strip() for line in product.splitlines() if line.strip()]
    business_items=[part.strip() for part in business.split('；') if part.strip()]
    # Headings identify an actual company product. Descriptions often mention
    # downstream applications, so a mention there has much lower weight.
    score=0.0
    for term in candidates:
        if len(term)<2: continue
        needle=term.casefold()
        item_score=0.0
        if headings and needle in headings[0].casefold(): item_score=6.0
        elif any(needle in h.casefold() for h in headings[1:]): item_score=4.0
        elif product and needle in product.casefold(): item_score=3.0
        if business_items and needle in business_items[0].casefold(): item_score+=2.0
        elif any(needle in item.casefold() for item in business_items[1:]): item_score+=1.0
        score=max(score,item_score)
    return score


def _concept(path: tuple[str,str,str]) -> str:
    l1,_,l3=path
    if l1=='連接器' and ('連接器' in l3 or l3=='端子'):
        return '連接器:連接器'
    if l1=='電腦及週邊' and l3 in {'工業電腦','工業/嵌入式電腦'}:
        return '電腦:工業電腦'
    if l1=='顯示/光學' and l3 in {'面板','LCD Panel'}:
        return '顯示:面板'
    if l1=='顯示/光學' and l3 in {'顯示器模組','液晶顯示模組'}:
        return '顯示:顯示模組'
    if l1=='顯示/光學' and l3 in {'光學鏡片/鏡頭','光學鏡頭'}:
        return '光學:鏡頭'
    if l1=='半導體' and l3 in {'IP/設計服務','IP設計/IC設計代工服務'}:
        return '半導體:設計服務'
    if l1=='被動元件' and l3=='濾波器/振盪器':
        return '被動:濾波振盪'
    return f'{l1}:{l3}'


def _product_specific_paths(product: str, business: str) -> list[tuple[str,str,str]]:
    # Only direct product descriptions, never the company name or market code.
    product_headings='\n'.join(line.split('；',1)[0] for line in product.splitlines() if line.strip())
    text = f'{product_headings}\n{business}'
    rules = [
        (r'積層陶瓷電容|MLCC', ('被動元件','電容','MLCC')),
        (r'伺服器.{0,8}(導軌|滑軌|理線器)', ('AI伺服器','機構/互連','Rail/Slide')),
        (r'鋼珠導軌', ('電腦及週邊','機構件','鋼珠導軌')),
        (r'蕭特基二極管|整流二極管|二極體', ('半導體','分離式元件','二極體')),
        (r'高密度互連|HDI', ('PCB','PCB製造','HDI')),
        (r'軟性印刷電路板|軟性電路板|\bFPCB\b', ('PCB','PCB製造','FPCB')),
        (r'硬式印刷電路板|多層印刷電路板|多層板', ('PCB','PCB製造','Rigid PCB')),
        (r'鍵盤(按鍵|機構|製造|產品)|筆記型電腦鍵盤', ('電腦及週邊','輸入裝置','鍵盤')),
        (r'光學鏡頭|相機鏡頭', ('顯示/光學','光學元件','光學鏡頭')),
        (r'濺鍍靶材|ITO靶材', ('顯示/光學','材料','濺鍍靶材')),
        (r'無塵室.{0,15}(工程|系統)|高科技.{0,8}建廠', ('半導體','廠務工程','無塵室/廠務工程')),
        (r'掃描器|掃瞄器', ('電腦及週邊','辦公設備','掃描器')),
        (r'光碟片|藍光光碟|BD-R|DVD-R', ('電腦及週邊','儲存媒體','光碟片')),
        (r'影印機|多功能事務機|相片印表機|列印機|印表機', ('電腦及週邊','辦公設備','列印/複合機')),
        (r'揚聲器|喇叭|音箱|音響系統', ('消費電子','聲學','揚聲器/音響')),
        (r'蜂鳴器', ('消費電子','聲學','蜂鳴器')),
        (r'耳機產品|耳機之製造|無線耳機', ('消費電子','聲學','耳機')),
        (r'示波器|頻譜分析儀|訊號產生器', ('電子儀器','測試量測','電子量測儀器')),
        (r'電磁相容.{0,12}(測試|檢測|認證)|EMC.{0,12}(測試|認證)', ('電子服務','檢測認證','EMC/安規檢測')),
        (r'材料分析|故障分析|失效分析|FIB線路修補', ('半導體','檢測服務','材料/失效分析')),
        (r'無線通訊模組|Wifi module|Wi-?Fi模組', ('網通','模組','無線通訊模組')),
        (r'毫米波天線|射頻.{0,8}天線|天線模組', ('網通','射頻元件','天線/射頻模組')),
        (r'薄膜濾光片|光學濾光片', ('光通訊','被動元件','薄膜濾光片')),
        (r'液晶顯示.{0,6}模組|TFT模組', ('顯示/光學','顯示模組','液晶顯示模組')),
        (r'智慧電表|智能電表|低壓AMI', ('電力電子','智慧電網','智慧電表')),
        (r'鋰電池模組', ('能源元件','電池','鋰電池模組')),
        (r'電感器|(?:^|[；\n])電感(?:$|[；\n])|功率電感', ('被動元件','電感','電感器')),
        (r'RFID電子標籤|RFID標籤', ('電子零組件','識別元件','RFID電子標籤')),
        (r'繼電器', ('被動元件','開關元件','繼電器')),
        (r'電容器材料|化成鋁箔|電蝕鋁箔', ('被動元件','電容材料','電容用鋁箔')),
        (r'陶瓷基板|氧化鋁基板', ('被動元件','基板材料','陶瓷基板')),
        (r'太陽能導電銲帶', ('太陽能','材料','太陽能銲帶')),
        (r'導線架|Lead Frame', ('半導體','材料','Lead Frame')),
        (r'功率半導體封裝測試|半導體封裝測試', ('半導體','封裝測試','功率半導體封測')),
        (r'顯示器驅動IC|顯示驅動IC', ('半導體','IC設計','Driver IC')),
        (r'觸控IC|觸控晶片', ('半導體','IC設計','Touch IC')),
        (r'AI高效能運算|高密度伺服器', ('AI伺服器','系統','AI/HPC伺服器')),
        (r'液冷整機櫃|液冷散熱', ('AI伺服器','散熱','Liquid Cooling')),
        (r'射頻.{0,8}測試|天線.{0,8}測試', ('網通','檢測認證','射頻/天線檢測')),
        (r'光學鍍膜|薄膜濺鍍靶材|ITO靶材', ('顯示/光學','材料','濺鍍/鍍膜材料')),
        (r'PCB.{0,8}(鑽針|鑽孔)|電子線路板專用微型鑽針', ('PCB','設備耗材','PCB鑽針')),
        (r'高精細金屬遮罩|AMOLED.{0,8}遮罩', ('顯示/光學','OLED材料','精細金屬遮罩')),
        (r'倒車雷達|胎壓監測|停車輔助系統', ('汽車電子','感測','車用感測/雷達')),
        (r'數位扭力扳手', ('電子儀器','工業量測','數位扭力工具')),
        (r'電子秤', ('電子儀器','工業量測','電子秤')),
        (r'電腦.{0,8}(通路|代理銷售)|科技產品通路經營', ('電腦及週邊','通路','資訊產品通路')),
        (r'晶圓製造服務|晶圓代工服務', ('半導體','晶圓製造','晶圓製造')),
        (r'雷射膜', ('顯示/光學','光學膜','雷射膜')),
        (r'Home Theater System|家庭劇院.{0,4}音響', ('消費電子','聲學','家庭劇院/音響')),
        (r'功率分離式元件|分離式元器件', ('半導體','分離式元件','功率分離式元件')),
        (r'讀卡機|銷售點終端機', ('電腦及週邊','終端設備','讀卡機/POS終端')),
        (r'唱盤|混音器|MIDI控制器', ('消費電子','聲學','音訊設備')),
        (r'硬碟機零組件', ('電腦及週邊','儲存設備','硬碟零組件')),
        (r'變壓器線架', ('被動元件','變壓器材料','變壓器線架')),
        (r'耳溫槍|額溫槍|紅外線溫度量測儀', ('電子儀器','醫療量測','紅外線體溫計')),
        (r'銲錫條|銲錫絲|錫膏', ('電子材料','銲接材料','電子銲錫材料')),
        (r'砷化鎵.{0,35}磊晶片|磷化銦.{0,35}磊晶片', ('半導體','磊晶材料','砷化鎵/磷化銦磊晶')),
        (r'影像感測器模組|線性感測模組', ('顯示/光學','影像感測','影像感測模組')),
        (r'薄膜觸控開關', ('被動元件','開關元件','薄膜觸控開關')),
        (r'線上遊戲|Online.{0,6}Game', ('軟體服務','遊戲內容','線上遊戲')),
        (r'高速電/光傳輸線', ('連接器','線材','高速傳輸線')),
        (r'陶瓷電路板', ('PCB','特殊基板','陶瓷電路板')),
        (r'太陽能電池片.{0,6}網版|精密網版', ('太陽能','設備耗材','太陽能網版')),
        (r'鐵氧磁|磁鐵芯', ('被動元件','磁性材料','鐵氧體磁芯')),
        (r'柴油發電機組', ('電力電子','備援電源','柴油發電機組')),
        (r'電腦割字機|雷射雕刻機', ('電子儀器','加工設備','雷射雕刻/割字機')),
        (r'端點銷售管理系統|行動POS', ('電腦及週邊','終端設備','POS終端')),
        (r'電子業無塵室|生化無菌室', ('半導體','廠務工程','無塵室/廠務工程')),
        (r'低功耗相機模組|影像感測相機模組', ('顯示/光學','影像模組','相機模組')),
    ]
    paths=[path for pattern,path in rules if re.search(pattern,text,re.I)]
    # Product descriptions may identify the product when the table heading is
    # merely "PCB" or "smart grid". Require company-specific wording here.
    descriptive=[
        (r'本公司.{0,30}聚焦.{0,30}智慧電表', ('電力電子','智慧電網','智慧電表')),
        (r'本公司.{0,30}專注.{0,35}HDI', ('PCB','PCB製造','HDI')),
        (r'本公司主要從事TFT-LCD沖壓零組件', ('顯示/光學','機構件','TFT面板機構件')),
        (r'本公司.{0,25}彩色CISM.{0,25}供應商', ('顯示/光學','影像感測','影像感測模組')),
    ]
    for pattern,path in descriptive:
        if re.search(pattern,product,re.I): paths.append(path)
    return paths


def run_sanity_audit(path: Path = DB_PATH) -> dict:
    with _connection(path) as conn:
        results=[]
        for row in _csv('sanity_audit_v4.csv'):
            key=_key(row['l1'],row['l2'],row['l3'])
            present=bool(conn.execute('''SELECT 1 FROM stock_sector_memberships m
              JOIN fine_companies c USING(market,stock_id)
              WHERE m.stock_id=? AND c.name LIKE ? AND m.sector_key=? AND m.valid_to IS NULL''',
              (row['stock_id'],row['name'].rstrip('*')+'%',key)).fetchone())
            results.append({'stock_id':row['stock_id'],'sector_key':key,'passed':present})
        bad=[r for r in results if not r['passed']]
        if bad:
            raise AssertionError(f'v4 sanity audit failed: {bad}')
        orphan_primary=conn.execute('''SELECT p.stock_id,p.sector_key FROM stock_primary_sector p
          WHERE p.valid_to IS NULL AND NOT EXISTS (
          SELECT 1 FROM stock_sector_memberships m WHERE m.market=p.market
          AND m.stock_id=p.stock_id AND m.sector_key=p.sector_key AND m.valid_to IS NULL)''').fetchall()
        if orphan_primary:
            raise AssertionError(f'primary L3 absent from memberships: {orphan_primary[:5]}')
        if conn.execute("SELECT 1 FROM stock_sector_memberships WHERE sector_key LIKE '%official_only%' LIMIT 1").fetchone():
            raise AssertionError('official_only cannot be completed L3')
        return {'total':len(results),'passed':len(results),'all_passed':True}


def get_stock_classification(stock_id: str, *, path: Path = DB_PATH) -> dict | None:
    init_classification_v4(path)
    with _connection(path) as conn:
        conn.row_factory=sqlite3.Row
        company=conn.execute('''SELECT market,stock_id,name,official_industry_code
          FROM fine_companies WHERE stock_id=? AND active=1 AND is_target=1''',(stock_id,)).fetchone()
        if company is None: return None
        key=(company['market'],company['stock_id'])
        primary=conn.execute('''SELECT p.sector_key,t.l1,t.l2,t.l3,p.source,p.source_url,p.confidence
          FROM stock_primary_sector p JOIN fine_taxonomy t ON t.sector_key=p.sector_key
          WHERE p.market=? AND p.stock_id=? AND p.valid_to IS NULL''',key).fetchone()
        members=[dict(r) for r in conn.execute('''SELECT DISTINCT m.sector_key,t.l1,t.l2,t.l3,
          GROUP_CONCAT(DISTINCT m.source) AS sources,
          GROUP_CONCAT(DISTINCT m.source_url) AS source_urls,
          MAX(m.confidence) AS confidence
          FROM stock_sector_memberships m JOIN fine_taxonomy t ON t.sector_key=m.sector_key
          WHERE m.market=? AND m.stock_id=? AND m.valid_to IS NULL
          GROUP BY m.sector_key ORDER BY t.l1,t.l2,t.l3''',key)]
        review=conn.execute('''SELECT reason,possible_category FROM classification_review_v4
          WHERE market=? AND stock_id=?''',key).fetchone()
        business=conn.execute('''SELECT main_business,source_url FROM fine_business
          WHERE market=? AND stock_id=?''',key).fetchone()
        product=conn.execute('''SELECT source_url,status FROM official_product_evidence
          WHERE market=? AND stock_id=?''',key).fetchone()
        levels=[dict(r) for r in conn.execute('''SELECT DISTINCT l1,l2 FROM stock_classification_levels
          WHERE market=? AND stock_id=? ORDER BY l1,l2''',key)]
        return {'company':dict(company),'primary':dict(primary) if primary else None,
                'memberships':members,'review':dict(review) if review else None,
                'levels':levels,'main_business':business['main_business'] if business else None,
                'business_source_url':business['source_url'] if business else None,
                'product_source_url':product['source_url'] if product and product['status']=='ok' else None,
                'status':'confirmed_primary' if primary else 'needs_review'}


def sync_classification_v4(*, path: Path = DB_PATH, export: bool = True,
                           require_audit: bool = True) -> dict:
    """Apply v4 evidence to an already synced company universe; reruns are safe."""
    init_classification_v4(path)
    now=datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    today=now[:10]
    curated=_csv('fine_classification_v4.csv')
    chains=_csv('official_value_chain_memberships_v4.csv')
    package_paths=defaultdict(set)
    for row in curated+chains:
        package_paths[(row['l1'],row['l3'])].add(row['l2'])
    canonical_l2={key:next(iter(values)) for key,values in package_paths.items() if len(values)==1}
    with _connection(path) as conn:
        conn.row_factory=sqlite3.Row
        companies={(r['market'],r['stock_id']):dict(r) for r in conn.execute(
            'SELECT * FROM fine_companies WHERE active=1 AND is_target=1')}
        if not companies:
            raise ValueError('Synchronize official stock universe before v4 classification')
        names=defaultdict(list)
        for key,c in companies.items():
            for name in (c['name'],c['company_name']):
                if key not in names[normalize_name(name)]: names[normalize_name(name)].append(key)
        business={ (r['market'],r['stock_id']):dict(r) for r in conn.execute('SELECT * FROM fine_business')}
        products={ (r['market'],r['stock_id']):dict(r) for r in conn.execute('SELECT * FROM official_product_evidence')}
        snapshots=defaultdict(list)
        for r in conn.execute('SELECT * FROM official_chain_snapshot'):
            snapshots[(r['market'],r['stock_id'])].append(dict(r))
        manual=[dict(r) for r in conn.execute('''SELECT * FROM fine_memberships
          WHERE source='manual_verified' AND valid_to IS NULL''')]
        legacy=[dict(r) for r in conn.execute('''SELECT * FROM fine_memberships
          WHERE source='official_business_rule' AND valid_to IS NULL''')]
    memberships=defaultdict(dict)
    primary_candidates=defaultdict(list)
    taxonomy={}
    missing_package=[]

    def add(key, path3, source, url, confidence, primary_rank=0):
        if key not in companies or not all(path3) or 'official_only' in path3:
            return
        if source=='tpex_company_chain' and (path3[0],path3[2]) in canonical_l2:
            path3=(path3[0],canonical_l2[(path3[0],path3[2])],path3[2])
        sector=_key(*path3)
        taxonomy[sector]=path3
        memberships[key][(sector,source)]=(url or '',confidence)
        if primary_rank:
            primary_candidates[key].append((primary_rank,confidence,sector,source,url or ''))

    for r in manual:
        path3=tuple(r['sector_key'].split(' > '))
        if len(path3)==3:
            add((r['market'],r['stock_id']),path3,'manual_verified',r['source_url'],r['confidence'] or 1,1000 if r['primary_for_flow'] else 0)
    for r in curated:
        keys=[key for key in companies if key[1]==r['stock_id']]
        if len(keys)!=1:
            missing_package.append(('curated',r['stock_id'],r['name']))
            continue
        add(keys[0],(r['l1'],r['l2'],r['l3']),'curated_v4',
            'package:fine_classification_v4.csv',float(r['confidence'] or 0),900)
    for r in chains:
        candidates=names.get(normalize_name(r['company_name']),[])
        if not candidates:
            # A renamed holding company may retain its prior TPEx chain label.
            # Require a unique stock whose current company-chain page also
            # contains this exact item; a name prefix alone is insufficient.
            stem=normalize_name(r['company_name'])
            candidates=[key for key,c in companies.items()
                        if normalize_name(c['name']).startswith(stem)
                        and any(item['chain_item']==r['l3'] for item in snapshots[key])]
        hinted=[key for key in candidates if key[0]==r['market_hint']]
        keys=hinted or candidates
        if len(keys)!=1:
            missing_package.append(('value_chain',r['company_name'],_key(r['l1'],r['l2'],r['l3'])))
            continue
        add(keys[0],(r['l1'],r['l2'],r['l3']),'official_value_chain_v4',
            r['source'],float(r['confidence'] or 0))
    for key,rows in snapshots.items():
        for r in rows:
            path3=_chain_path(r['chain_l1'],r['chain_item'])
            if path3:
                add(key,path3,'tpex_company_chain',r['source_url'],.91)
    for r in legacy:
        key=(r['market'],r['stock_id'])
        path3=tuple(r['sector_key'].split(' > '))
        if len(path3)==3 and key not in primary_candidates:
            add(key,path3,'mops_business_rule',r['source_url'],r['confidence'] or .65,400)
    for key,c in companies.items():
        p=products.get(key,{})
        b=business.get(key,{})
        product=p.get('product_text','') if p.get('status')=='ok' else ''
        biz='；'.join(filter(None,(b.get('main_business',''),b.get('description',''))))
        product_paths=list(dict.fromkeys(_product_specific_paths(product,biz)))
        for path3 in product_paths:
            direct_primary=(len(product_paths)==1 and _text_score(path3,product,biz)>=5)
            add(key,path3,'official_product_text' if product else 'mops_main_business',
                p.get('source_url') if product else b.get('source_url'),.88 if product else .78,
                500 if direct_primary else 0)

    levels=defaultdict(set)
    for key,entries in memberships.items():
        for sector,_source in entries:
            l1,l2,_l3=taxonomy[sector]
            levels[key].add((l1,l2,'verified_l3_membership'))
    for key,rows in snapshots.items():
        for r in rows:
            vertical,item=r['chain_l1'],r['chain_item']
            if vertical in CHAIN_VERTICAL and item not in {'其他','其他零組件',
              '其他電腦及週邊設備','其他電腦及週邊設備之零組件'}:
                path3=_chain_path(vertical,item)
                l1=path3[0] if path3 else CHAIN_VERTICAL[vertical]
                l2=path3[1] if path3 else None
                levels[key].add((l1,l2,'tpex_company_chain'))

    reviews=[]
    selected={}
    for key,c in companies.items():
        ranked=sorted(primary_candidates[key],reverse=True)
        if ranked:
            _,confidence,sector,source,url=ranked[0]
            selected[key]=(sector,source,url,confidence)
            continue
        choices={sector: (url,conf) for (sector,source),(url,conf) in memberships[key].items()
                 if source in {'tpex_company_chain','official_value_chain_v4','official_product_text','mops_main_business'}}
        p=products.get(key,{})
        b=business.get(key,{})
        product=p.get('product_text','') if p.get('status')=='ok' else ''
        biz='；'.join(filter(None,(b.get('main_business',''),b.get('description',''))))
        if choices:
            scores=sorted(((_text_score(taxonomy[sector],product,biz),sector) for sector in choices),reverse=True)
            winner=None
            if len(scores)==1:
                winner=scores[0][1]
            elif len({_concept(taxonomy[sector]) for sector in choices})==1:
                winner=max(choices,key=lambda sector:(
                    any(s=='official_value_chain_v4' for sec,s in memberships[key] if sec==sector),
                    choices[sector][1],sector))
            elif scores[0][0]>=3 and scores[0][0]>=scores[1][0]+1.0:
                winner=scores[0][1]
            if winner:
                url,conf=choices[winner]
                selected[key]=(winner,'official_evidence_primary',url,conf)
                continue
        reason='ambiguous_official_products' if choices else 'no_specific_official_l3_evidence'
        possible=' | '.join(sorted(choices))
        reviews.append((key,reason,possible))

    with _connection(path) as conn:
        with conn:
            conn.executemany('''INSERT INTO fine_taxonomy VALUES(?,?,?,?,?)
              ON CONFLICT(sector_key) DO NOTHING''',
              [(sector,*path3,'v4_official_evidence') for sector,path3 in taxonomy.items()])
            conn.execute('DELETE FROM stock_primary_sector')
            conn.execute('DELETE FROM stock_sector_memberships')
            conn.execute('DELETE FROM classification_review_v4')
            conn.execute('DELETE FROM stock_classification_levels')
            conn.executemany('''INSERT INTO stock_sector_memberships VALUES(?,?,?,?,?,?,?,?,?)''',
              [(key[0],key[1],sector,source,url,conf,today,None,now)
               for key,entries in memberships.items() for (sector,source),(url,conf) in entries.items()])
            conn.executemany('''INSERT INTO stock_primary_sector VALUES(?,?,?,?,?,?,?,?,?)''',
              [(key[0],key[1],sector,source,url,conf,today,None,now)
               for key,(sector,source,url,conf) in selected.items()])
            conn.executemany('INSERT INTO classification_review_v4 VALUES(?,?,?,?,?)',
              [(key[0],key[1],reason,possible,now) for key,reason,possible in reviews])
            conn.executemany('INSERT OR IGNORE INTO stock_classification_levels VALUES(?,?,?,?,?,?)',
              [(key[0],key[1],l1,l2,source,now) for key,items in levels.items()
               for l1,l2,source in items])
            conn.execute("INSERT INTO fine_metadata VALUES('classification_version','v4') ON CONFLICT(key) DO UPDATE SET value='v4'")
            conn.execute("INSERT INTO fine_metadata VALUES('last_sync_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(now,))
    audit=run_sanity_audit(path) if require_audit else None
    if export:
        with _connection(path) as conn:
            conn.row_factory=sqlite3.Row
            rows=[dict(r) for r in conn.execute('''SELECT c.stock_id,c.name,c.market,c.official_industry_code AS official_industry,
              b.main_business,t.l1 AS current_l1,t.l2 AS current_l2,t.l3 AS current_l3,
              q.reason,q.possible_category,p.product_text,p.source_url AS product_source_url
              FROM classification_review_v4 q JOIN fine_companies c USING(market,stock_id)
              LEFT JOIN fine_business b USING(market,stock_id)
              LEFT JOIN stock_primary_sector s USING(market,stock_id)
              LEFT JOIN fine_taxonomy t ON t.sector_key=s.sector_key
              LEFT JOIN official_product_evidence p USING(market,stock_id)
              ORDER BY c.market,c.stock_id''')]
            for row in rows:
                key=(row['market'],row['stock_id'])
                choices=levels[key]
                l1s={item[0] for item in choices}
                l2s={item[1] for item in choices if item[1]}
                row['current_l1']=row['current_l1'] or (next(iter(l1s)) if len(l1s)==1 else '')
                row['current_l2']=row['current_l2'] or (next(iter(l2s)) if len(l2s)==1 else '')
        with REVIEW_FILE.open('w',encoding='utf-8-sig',newline='') as handle:
            fields=['stock_id','name','market','official_industry','main_business','current_l1',
                    'current_l2','current_l3','reason','possible_category','product_text','product_source_url']
            writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore')
            writer.writeheader();writer.writerows(rows)
    with _connection(path) as conn:
        total=len(companies)
        primary=conn.execute('SELECT COUNT(*) FROM stock_primary_sector WHERE valid_to IS NULL').fetchone()[0]
        member=conn.execute('''SELECT COUNT(DISTINCT market||':'||stock_id)
          FROM stock_sector_memberships WHERE valid_to IS NULL''').fetchone()[0]
        l1_count=conn.execute('SELECT COUNT(DISTINCT market||":"||stock_id) FROM stock_classification_levels').fetchone()[0]
        l2_count=conn.execute('''SELECT COUNT(DISTINCT market||":"||stock_id) FROM stock_classification_levels
          WHERE l2 IS NOT NULL''').fetchone()[0]
    return {'target_total':total,'l1_mapped_total':l1_count,'l1_mapped_pct':round(100*l1_count/total,1),
            'l2_mapped_total':l2_count,'l2_mapped_pct':round(100*l2_count/total,1),
            'l3_mapped_total':member,'l3_mapped_pct':round(100*member/total,1),
            'primary_l3_total':primary,'review_queue_total':len(reviews),
            'review_queue_pct':round(100*len(reviews)/total,1),
            'remaining_stock_ids':[key[1] for key,_,_ in reviews],
            'unmatched_package_rows':missing_package,'sanity_audit':audit,
            'review_file':str(REVIEW_FILE)}
