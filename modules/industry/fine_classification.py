"""Live fine-sector memberships with auditable official/curated provenance."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.core.http_utils import request_bytes
from modules.core.project_paths import data_path
from modules.industry.electronics_universe import DB_PATH, ELECTRONIC_CODES, fetch_official_companies

PACKAGE = data_path('sector_rotation/final')
BUSINESS_URL = 'https://dsp.tpex.org.tw/storage/company_basic/company_basic.php'
# Every rule uses official business text only. Multiple matches require human review.
BUSINESS_RULES = [
    (r'成熟製程.*晶圓代工|晶圓代工.*成熟製程', ('半導體','晶圓製造','Mature-node Foundry')),
    (r'微控制器|MCU', ('半導體','IC設計','CPU/MCU')),
    (r'先進封裝|CoWoS', ('半導體','封裝測試','Advanced Packaging')),
    (r'半導體測試|晶圓測試', ('半導體','封裝測試','IC Testing')),
    (r'晶圓級.*封裝|WLP|金凸塊', ('半導體','封裝測試','Bumping/Wafer-level Packaging')),
    (r'積體電路.*封裝|IC封裝', ('半導體','封裝測試','IC Packaging')),
    (r'DRAM|動態隨機存取記憶體', ('半導體','記憶體','DRAM')),
    (r'NAND\s*Flash|NAND快閃', ('半導體','記憶體','NAND Flash')),
    (r'NOR\s*Flash|NOR快閃', ('半導體','記憶體','NOR Flash')),
    (r'電源管理晶片|電源管理IC|Power IC|功率積體電路', ('半導體','IC設計','PMIC/Power IC')),
    (r'音效晶片|音效IC|音頻晶片', ('半導體','IC設計','Audio IC')),
    (r'顯示器驅動IC|顯示驅動晶片', ('半導體','IC設計','Driver IC')),
    (r'觸控晶片|觸控IC', ('半導體','IC設計','Touch IC')),
    (r'影像處理IC', ('半導體','IC設計','GPU/Display IC')),
    (r'高速訊號傳輸介面.*晶片|高速傳輸介面IC', ('半導體','IC設計','High-Speed Interface IC')),
    (r'探針卡|Probe Card', ('半導體','測試介面','Probe Card')),
    (r'測試插座|Test Socket', ('半導體','測試介面','Test Socket')),
    (r'IC測試分選機|半導體測試設備', ('半導體','設備','Test Equipment')),
    (r'光罩|Photomask', ('半導體','材料','Photomask')),
    (r'矽晶圓|矽晶片', ('半導體','材料','Silicon Wafer')),
    (r'光阻劑|光阻材料', ('半導體','材料','Photoresist/Chemicals')),
    (r'導線架', ('半導體','材料','Lead Frame')),
    (r'硬式印刷電路板|硬板', ('PCB','PCB製造','Rigid PCB')),
    (r'軟性電路板|軟板', ('PCB','PCB製造','FPCB')),
    (r'高密度.*印刷電路板|HDI板', ('PCB','PCB製造','HDI')),
    (r'ABF載板', ('PCB','IC載板','ABF Substrate')),
    (r'BT載板', ('PCB','IC載板','BT Substrate')),
    (r'板對板連接器', ('連接器','應用','Board-to-Board')),
    (r'晶片電阻', ('被動元件','電阻','Chip Resistor')),
    (r'電容器|陶瓷電容', ('被動元件','電容','MLCC')),
    (r'功率電感', ('被動元件','電感','Power Inductor')),
    (r'企業交換器', ('網通','網路設備','Enterprise Switch')),
    (r'光收發模組', ('光通訊','主動元件','Optical Transceiver')),
    (r'光纖連接器', ('光通訊','被動元件','Fiber Connector')),
    (r'伺服器主機板', ('AI伺服器','系統','Server Motherboard')),
    (r'自動化設備', ('自動化/機器人','系統','Automation Equipment')),
    (r'液晶顯示面板|LCD面板', ('顯示/光學','顯示','LCD Panel')),
    (r'偏光板', ('顯示/光學','光學','Optical Film')),
    (r'光學鏡頭|相機鏡頭', ('顯示/光學','光學','Camera Lens')),
    (r'液冷散熱|液體冷卻', ('AI伺服器','散熱','Liquid Cooling')),
    (r'伺服器.*(滑軌|導軌)|伺服器用導軌', ('AI伺服器','機構/互連','Rail/Slide')),
    (r'不斷電系統|UPS', ('AI伺服器','電源','UPS')),
    (r'工業電腦|IPC', ('電腦及週邊','系統','Industrial PC')),
    (r'嵌入式電腦|嵌入式系統', ('電腦及週邊','系統','Embedded System')),
    (r'固態硬碟|SSD', ('電腦及週邊','儲存','SSD')),
    (r'鉸鏈', ('電腦及週邊','零組件','Hinge')),
    (r'衛星.*天線|天線.*衛星', ('衛星/航太','衛星通訊','Satellite Antenna')),
    (r'汽車.*(ADAS|先進駕駛輔助)|ADAS', ('汽車電子','電子零組件','ADAS')),
    (r'資訊安全|網路安全|資安服務', ('資安/軟體','科技服務','Cybersecurity')),
]


@contextmanager
def _connection(path: Path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _rows(name: str) -> list[dict]:
    with (PACKAGE / name).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _now() -> str:
    return datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')


def _key(l1: str, l2: str, l3: str) -> str:
    return ' > '.join((l1.strip(), l2.strip(), l3.strip()))


def normalize_name(value: str) -> str:
    return re.sub(r'[\s＊*\-－·‧（）()]', '', unicodedata.normalize('NFKC', value or '')).strip()


def init_fine_db(path: Path = DB_PATH) -> None:
    with _connection(path) as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS fine_companies (
          market TEXT NOT NULL, stock_id TEXT NOT NULL, name TEXT NOT NULL, company_name TEXT,
          official_industry_code TEXT, is_target INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          last_seen_at TEXT NOT NULL, PRIMARY KEY(market,stock_id));
        CREATE TABLE IF NOT EXISTS fine_taxonomy (
          sector_key TEXT PRIMARY KEY, l1 TEXT NOT NULL, l2 TEXT NOT NULL, l3 TEXT NOT NULL,
          origin TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS fine_memberships (
          market TEXT NOT NULL, stock_id TEXT NOT NULL, sector_key TEXT NOT NULL,
          source TEXT NOT NULL, source_url TEXT, confidence REAL,
          primary_for_flow INTEGER NOT NULL DEFAULT 0, valid_from TEXT NOT NULL,
          valid_to TEXT, observed_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id,sector_key,source));
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_fine_primary ON fine_memberships(market,stock_id)
          WHERE primary_for_flow=1 AND valid_to IS NULL;
        CREATE INDEX IF NOT EXISTS idx_fine_sector ON fine_memberships(sector_key);
        CREATE TABLE IF NOT EXISTS fine_themes (
          market TEXT NOT NULL,stock_id TEXT NOT NULL,theme TEXT NOT NULL,source TEXT NOT NULL,
          source_url TEXT,confidence REAL,observed_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id,theme,source));
        CREATE TABLE IF NOT EXISTS fine_business (
          market TEXT NOT NULL,stock_id TEXT NOT NULL,main_business TEXT,
          description TEXT,source_url TEXT,fetch_status TEXT NOT NULL,fetched_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id));
        CREATE TABLE IF NOT EXISTS fine_review_queue (
          market TEXT NOT NULL,stock_id TEXT NOT NULL,name TEXT NOT NULL,
          official_industry_code TEXT,main_business TEXT,reason TEXT NOT NULL,updated_at TEXT NOT NULL,
          PRIMARY KEY(market,stock_id));
        CREATE TABLE IF NOT EXISTS fine_unresolved (
          source_type TEXT NOT NULL,company_name TEXT NOT NULL,market_hint TEXT,
          sector_or_theme TEXT NOT NULL,source_url TEXT,reason TEXT NOT NULL,
          PRIMARY KEY(source_type,company_name,market_hint,sector_or_theme));
        CREATE TABLE IF NOT EXISTS fine_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')


def fetch_business(market: str, stock_id: str) -> dict:
    url = f'{BUSINESS_URL}?s={stock_id}&m={22 if market == "TWSE" else 21}'
    try:
        payload = request_bytes(url, timeout=20).decode('utf-8-sig')
        match = re.search(r'^getCompanyBasic\((.*)\);?\s*$', payload, re.S)
        if not match:
            raise ValueError('Invalid JSONP response')
        obj = json.loads(match.group(1))
        if str(obj.get('COMPANY_ID')) != stock_id:
            raise ValueError('Mismatched company id')
        main = '；'.join(str(obj.get(f'MAIN_BUSINESS{i}') or '').strip() for i in range(1, 4)).strip('；')
        description = str(obj.get('MAIN_BUSINESS4') or '').strip()
        return {'market': market,'stock_id': stock_id,'main_business': main,
                'description': description,'source_url': url,'fetch_status': 'ok' if main or description else 'empty'}
    except Exception as exc:
        return {'market': market,'stock_id': stock_id,'main_business': '',
                'description': '', 'source_url': url,'fetch_status': f'error:{type(exc).__name__}'}


def classify_business(text: str, valid_keys: set[str]) -> tuple[str | None, str]:
    if not text.strip():
        return None, 'business_unavailable'
    matches = {_key(*path) for pattern,path in BUSINESS_RULES if re.search(pattern,text,re.I) and _key(*path) in valid_keys}
    if len(matches) == 1:
        return next(iter(matches)), 'official_business_rule'
    return None, 'ambiguous_business' if matches else 'no_matching_business_rule'


def _resolve(name: str, market: str, by_name: dict) -> tuple[str,str] | None:
    candidates = by_name.get(normalize_name(name), [])
    candidates = [key for key in candidates if key[0] == market] if market in ('TWSE','TPEx') else candidates
    return candidates[0] if len(candidates) == 1 else None


def _export(path: Path, rows: list[dict], fields: list[str]) -> None:
    temp = path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf-8-sig',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
    temp.replace(path)


def sync_fine_classification(*, companies: list[dict] | None = None, path: Path = DB_PATH,
                             fetch_descriptions: bool = True, max_workers: int = 12,
                             export: bool = True) -> dict:
    """Refresh source rows while retaining previously verified fine primary mappings."""
    if companies is None:
        companies,_ = fetch_official_companies()
    if not companies or any(not any(r['market']==m for r in companies) for m in ('TWSE','TPEx')):
        raise ValueError('Both live ordinary-company markets are required')
    init_fine_db(path)
    now = _now(); today = now[:10]
    company_by_key = {(r['market'],r['stock_id']): r for r in companies}
    if len(company_by_key) != len(companies):
        raise ValueError('Duplicate company identifiers')
    by_name: dict[str,list[tuple[str,str]]] = defaultdict(list)
    for key,row in company_by_key.items():
        for name in {row['name'],row.get('company_name','')}:
            normalized = normalize_name(name)
            if normalized and key not in by_name[normalized]: by_name[normalized].append(key)
    curated = _rows('fine_classification_v2.csv')
    chains = _rows('official_value_chain_memberships.csv')
    themes = _rows('official_theme_memberships.csv')
    taxonomy = _rows('fine_taxonomy_v2.csv')
    official_keys = {_key(r['l1'],r['l2'],r['l3']) for r in taxonomy}
    electronic_l1 = {r['l1'] for r in taxonomy}
    targets = {key for key,r in company_by_key.items() if r['official_industry_code'] in ELECTRONIC_CODES}
    proposed: dict[tuple[str,str],list[dict]] = defaultdict(list)
    unresolved = []
    for r in curated:
        matches = [key for key in company_by_key if key[1]==r['stock_id']]
        if len(matches)!=1:
            unresolved.append(('curated',r['name'],'',_key(r['l1'],r['l2'],r['l3']),'','stock_id_missing_or_ambiguous'))
            continue
        key = matches[0]
        # The package also has broad-market seeds (banks, shipping, restaurants).
        # Keep this product focused on electronic businesses and the supplied fine taxonomy.
        if company_by_key[key]['official_industry_code'] not in ELECTRONIC_CODES and r['l1'] not in electronic_l1:
            continue
        targets.add(key)
        proposed[key].append({'sector_key':_key(r['l1'],r['l2'],r['l3']),'source':'curated_product',
                              'source_url':'package:fine_classification_v2.csv','confidence':float(r['confidence'] or 0),
                              'priority':300,'review_status':r['review_status']})
    for r in chains:
        key = _resolve(r['company_name'],r['market_hint'],by_name)
        sector = _key(r['l1'],r['l2'],r['l3'])
        if key is None:
            unresolved.append(('value_chain',r['company_name'],r['market_hint'],sector,r['source'],'name_missing_or_ambiguous'))
            continue
        targets.add(key)
        proposed[key].append({'sector_key':sector,'source':'official_value_chain','source_url':r['source'],
                              'confidence':float(r['confidence'] or 0),'priority':200,'review_status':'fine_mapped'})
    theme_rows = []
    for r in themes:
        key = _resolve(r['company_name'],r['market_hint'],by_name)
        if key is None:
            unresolved.append(('theme',r['company_name'],r['market_hint'],r['theme'],r['source'],'name_missing_or_ambiguous'))
            continue
        targets.add(key)
        theme_rows.append((*key,r['theme'],'official_value_chain',r['source'],float(r['confidence'] or 0),now))
    with _connection(path) as conn:
        conn.row_factory = sqlite3.Row
        cached = {(r['market'],r['stock_id']):dict(r) for r in conn.execute('SELECT * FROM fine_business')}
        prior = {(r['market'],r['stock_id']):dict(r) for r in conn.execute('SELECT * FROM fine_memberships WHERE primary_for_flow=1 AND valid_to IS NULL')}
    refresh_before = (datetime.fromisoformat(now) - timedelta(days=30)).isoformat(timespec='seconds')
    needs_fetch = [key for key in targets if key not in proposed and (
        key not in cached or cached[key]['fetch_status']!='ok' or cached[key]['fetched_at'] < refresh_before)]
    fetched = []
    if fetch_descriptions and needs_fetch:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_business,*key): key for key in needs_fetch}
            for future in as_completed(futures): fetched.append(future.result())
    fetched = [{**item,'fetched_at':now} for item in fetched]
    for item in fetched: cached[(item['market'],item['stock_id'])] = item
    nodes = {key:(*key.split(' > '),'package_taxonomy') for key in official_keys}
    for entries in proposed.values():
        for e in entries:
            k=e['sector_key']
            if k not in nodes:
                nodes[k]=(*k.split(' > '),'official_value_chain' if e['source']=='official_value_chain' else 'curated_product')
    valid_keys = set(nodes)
    for key in targets:
        if proposed[key]: continue
        business = cached.get(key,{})
        text = '；'.join(filter(None,[business.get('main_business',''),business.get('description','')]))
        sector,reason = classify_business(text,valid_keys)
        if sector:
            proposed[key].append({'sector_key':sector,'source':'official_business_rule',
                                  'source_url':business.get('source_url'),'confidence':0.65,
                                  'priority':100,'review_status':'fine_mapped'})
        else:
            proposed[key].append({'sector_key':None,'reason':reason,'priority':0})
    # Preserve prior primary on source outage or when a lower-priority match would replace it.
    priority = {'manual_verified':400,'curated_product':300,'official_value_chain':200,'official_business_rule':100}
    for key,old in prior.items():
        if key not in targets: continue
        best = max((e.get('priority',0) for e in proposed[key]),default=0)
        if priority.get(old['source'],0)>best:
            proposed[key].append({'sector_key':old['sector_key'],'source':old['source'],'source_url':old['source_url'],
                                  'confidence':old['confidence'],'priority':priority.get(old['source'],0),
                                  'review_status':'fine_mapped','preserved':True})
            if old['sector_key'] not in nodes:
                nodes[old['sector_key']]=(*old['sector_key'].split(' > '),'preserved')
    with _connection(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('UPDATE fine_companies SET active=0,is_target=0')
        conn.executemany('''INSERT INTO fine_companies VALUES(?,?,?,?,?,?,1,?)
          ON CONFLICT(market,stock_id) DO UPDATE SET name=excluded.name,company_name=excluded.company_name,
          official_industry_code=excluded.official_industry_code,is_target=excluded.is_target,active=1,last_seen_at=excluded.last_seen_at''',
          [(r['market'],r['stock_id'],r['name'],r.get('company_name'),r['official_industry_code'],int((r['market'],r['stock_id']) in targets),now) for r in companies])
        conn.executemany('INSERT INTO fine_taxonomy VALUES(?,?,?,?,?) ON CONFLICT(sector_key) DO UPDATE SET origin=CASE WHEN fine_taxonomy.origin="package_taxonomy" THEN fine_taxonomy.origin ELSE excluded.origin END',
                         [(key,*value) for key,value in nodes.items()])
        conn.executemany('''INSERT INTO fine_business VALUES(?,?,?,?,?,?,?) ON CONFLICT(market,stock_id)
          DO UPDATE SET main_business=excluded.main_business,description=excluded.description,source_url=excluded.source_url,
          fetch_status=excluded.fetch_status,fetched_at=excluded.fetched_at''',
          [(r['market'],r['stock_id'],r['main_business'],r['description'],r['source_url'],r['fetch_status'],r['fetched_at']) for r in fetched])
        conn.execute("DELETE FROM fine_memberships WHERE source!='manual_verified'")
        conn.execute("DELETE FROM fine_themes WHERE source='official_value_chain'")
        conn.executemany('INSERT OR IGNORE INTO fine_themes VALUES(?,?,?,?,?,?,?)',theme_rows)
        conn.execute('DELETE FROM fine_review_queue')
        conn.execute('DELETE FROM fine_unresolved')
        conn.executemany('INSERT INTO fine_unresolved VALUES(?,?,?,?,?,?)',unresolved)
        for key in sorted(targets):
            market,stock_id=key; entries=proposed[key]
            manual=conn.execute("SELECT 1 FROM fine_memberships WHERE market=? AND stock_id=? AND source='manual_verified' AND primary_for_flow=1 AND valid_to IS NULL",key).fetchone()
            best=max((e for e in entries if e.get('sector_key')),key=lambda e:(e['priority'],e['sector_key']),default=None)
            for e in entries:
                if not e.get('sector_key') or (e.get('preserved') and e['source']=='manual_verified'): continue
                is_primary=int(not manual and e is best)
                previous = prior.get(key)
                valid_from = previous['valid_from'] if previous and previous['sector_key']==e['sector_key'] and previous['source']==e['source'] else today
                conn.execute('''INSERT INTO fine_memberships VALUES(?,?,?,?,?,?,?,?,?,?)''',
                             (market,stock_id,e['sector_key'],e['source'],e.get('source_url'),e.get('confidence'),is_primary,valid_from,None,now))
            official_choices={e['sector_key'] for e in entries if e.get('source')=='official_value_chain'}
            provisional_primary=best is not None and best['source']=='official_value_chain' and len(official_choices)>1
            if best is None or best.get('review_status') in ('needs_product_refinement','mapped') or provisional_primary:
                r=company_by_key[key]; business=cached.get(key,{})
                reason=(entries[0].get('reason','needs_product_refinement') if best is None
                        else 'multiple_official_l3_primary_provisional' if provisional_primary else best['review_status'])
                conn.execute('INSERT INTO fine_review_queue VALUES(?,?,?,?,?,?,?)',
                             (market,stock_id,r['name'],r['official_industry_code'],business.get('main_business',''),reason,now))
        for k,v in {'last_sync_at':now,'twse_ordinary_total':str(sum(r['market']=='TWSE' for r in companies)),
                    'tpex_ordinary_total':str(sum(r['market']=='TPEx' for r in companies))}.items():
            conn.execute('INSERT INTO fine_metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
    if export:
        with _connection(path) as conn:
            conn.row_factory=sqlite3.Row
            all_rows=[dict(r) for r in conn.execute('''SELECT c.market,c.stock_id,c.name,c.official_industry_code,
              t.l1,t.l2,t.l3,m.sector_key,m.source,m.primary_for_flow,m.confidence
              FROM fine_companies c LEFT JOIN fine_memberships m ON m.market=c.market AND m.stock_id=c.stock_id AND m.valid_to IS NULL
              LEFT JOIN fine_taxonomy t ON t.sector_key=m.sector_key WHERE c.active=1 AND c.is_target=1
              ORDER BY c.market,c.stock_id,m.primary_for_flow DESC''')]
            review=[dict(r) for r in conn.execute('SELECT * FROM fine_review_queue ORDER BY market,stock_id')]
            missing=[dict(r) for r in conn.execute('SELECT * FROM fine_unresolved ORDER BY source_type,company_name')]
        _export(data_path('all_twse_tpex_electronics_fine.csv'),all_rows,
                ['market','stock_id','name','official_industry_code','l1','l2','l3','sector_key','source','primary_for_flow','confidence'])
        _export(data_path('review_queue.csv'),review,['market','stock_id','name','official_industry_code','main_business','reason','updated_at'])
        _export(data_path('unresolved_official_memberships.csv'),missing,
                ['source_type','company_name','market_hint','sector_or_theme','source_url','reason'])
    return get_fine_coverage(path)


def get_fine_coverage(path: Path = DB_PATH) -> dict:
    init_fine_db(path)
    with _connection(path) as conn:
        cur=conn.cursor()
        scalar=lambda q: cur.execute(q).fetchone()[0]
        version=cur.execute("SELECT value FROM fine_metadata WHERE key='classification_version'").fetchone()
        if version and version[0]=='v4' and cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stock_primary_sector'").fetchone():
            target=scalar('SELECT COUNT(*) FROM fine_companies WHERE active=1 AND is_target=1')
            l1=scalar('SELECT COUNT(DISTINCT market||":"||stock_id) FROM stock_classification_levels')
            l2=scalar('SELECT COUNT(DISTINCT market||":"||stock_id) FROM stock_classification_levels WHERE l2 IS NOT NULL')
            l3=scalar('SELECT COUNT(DISTINCT market||":"||stock_id) FROM stock_sector_memberships WHERE valid_to IS NULL')
            review=scalar('SELECT COUNT(*) FROM classification_review_v4')
            data={r[0]:r[1] for r in cur.execute('SELECT key,value FROM fine_metadata')}
            return {'twse_ordinary_total':int(data.get('twse_ordinary_total',0)),
                    'tpex_ordinary_total':int(data.get('tpex_ordinary_total',0)),
                    'twse_target':scalar("SELECT COUNT(*) FROM fine_companies WHERE active=1 AND is_target=1 AND market='TWSE'"),
                    'tpex_target':scalar("SELECT COUNT(*) FROM fine_companies WHERE active=1 AND is_target=1 AND market='TPEx'"),
                    'target_total':target,'l1_mapped_total':l1,'l1_mapped_pct':round(100*l1/target,1) if target else 0,
                    'l2_mapped_total':l2,'l2_mapped_pct':round(100*l2/target,1) if target else 0,
                    'l3_mapped_total':l3,'l3_mapped_pct':round(100*l3/target,1) if target else 0,
                    'primary_l3_total':scalar('SELECT COUNT(*) FROM stock_primary_sector WHERE valid_to IS NULL'),
                    'review_queue_total':review,'review_queue_pct':round(100*review/target,1) if target else 0,
                    'unresolved_membership_total':scalar('SELECT COUNT(*) FROM fine_unresolved'),
                    'classification_version':'v4','last_sync_at':data.get('last_sync_at')}
        target=scalar('SELECT COUNT(*) FROM fine_companies WHERE active=1 AND is_target=1')
        mapped=scalar('''SELECT COUNT(*) FROM fine_memberships m JOIN fine_companies c USING(market,stock_id)
          WHERE c.active=1 AND c.is_target=1 AND m.primary_for_flow=1 AND m.valid_to IS NULL''')
        review=scalar('SELECT COUNT(*) FROM fine_review_queue')
        data={r[0]:r[1] for r in cur.execute('SELECT key,value FROM fine_metadata')}
        return {'twse_ordinary_total':int(data.get('twse_ordinary_total',0)),
                'tpex_ordinary_total':int(data.get('tpex_ordinary_total',0)),
                'twse_target':scalar("SELECT COUNT(*) FROM fine_companies WHERE active=1 AND is_target=1 AND market='TWSE'"),
                'tpex_target':scalar("SELECT COUNT(*) FROM fine_companies WHERE active=1 AND is_target=1 AND market='TPEx'"),
                'target_total':target,'l3_mapped_total':mapped,'l3_mapped_pct':round(100*mapped/target,1) if target else 0,
                'review_queue_total':review,'review_queue_pct':round(100*review/target,1) if target else 0,
                'unresolved_membership_total':scalar('SELECT COUNT(*) FROM fine_unresolved'),
                'last_sync_at':data.get('last_sync_at')}
