"""Official TPEx value-chain and company-submitted product evidence by stock code."""
from __future__ import annotations

import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from modules.core.http_utils import request_bytes
from modules.industry.electronics_universe import DB_PATH

CHAIN_URL = 'https://ic.tpex.org.tw/company_chain.php'
PRODUCT_URL = 'https://ic.tpex.org.tw/company_list.php'


def init_evidence_db(path: Path = DB_PATH) -> None:
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS official_chain_snapshot (
              market TEXT NOT NULL,stock_id TEXT NOT NULL,chain_l1 TEXT NOT NULL,
              chain_item TEXT NOT NULL,source_url TEXT NOT NULL,fetched_at TEXT NOT NULL,
              PRIMARY KEY(market,stock_id,chain_l1,chain_item));
            CREATE TABLE IF NOT EXISTS official_chain_fetch (
              market TEXT NOT NULL,stock_id TEXT NOT NULL,status TEXT NOT NULL,
              fetched_at TEXT NOT NULL,PRIMARY KEY(market,stock_id));
            CREATE TABLE IF NOT EXISTS official_product_evidence (
              market TEXT NOT NULL,stock_id TEXT NOT NULL,product_text TEXT NOT NULL,
              source_url TEXT NOT NULL,status TEXT NOT NULL,fetched_at TEXT NOT NULL,
              PRIMARY KEY(market,stock_id));
            ''')
    finally:
        conn.close()


def parse_chain_page(raw: bytes, stock_id: str) -> list[tuple[str,str]]:
    soup = BeautifulSoup(raw.decode('utf-8', errors='replace'), 'html.parser')
    headings = [tag.get_text(' ', strip=True) for tag in soup.find_all('h4')]
    if not any(re.search(rf'\b{re.escape(stock_id)}\b.*所屬產業鏈', text) for text in headings):
        raise ValueError('company id absent from official chain page')
    rows = []
    for text in headings:
        match = re.match(r'^►\s*(.+?)\s*>\s*(.+)$', text)
        if match:
            rows.append((match.group(1).strip(), match.group(2).strip()))
    return list(dict.fromkeys(rows))


def parse_product_page(raw: bytes) -> str:
    soup = BeautifulSoup(raw.decode('utf-8', errors='replace'), 'html.parser')
    rows = []
    for tr in soup.find_all('tr'):
        cells = [td.get_text(' ', strip=True) for td in tr.find_all('td')]
        if len(cells) >= 2 and (cells[0] or cells[1]):
            rows.append('；'.join(cells[:2]))
    return '\n'.join(rows)


def fetch_chain(stock_id: str) -> tuple[str,list[tuple[str,str]],str]:
    url = f'{CHAIN_URL}?stk_code={stock_id}'
    try:
        return url, parse_chain_page(request_bytes(url, timeout=20, retries=1), stock_id), 'ok'
    except Exception as exc:
        return url, [], f'error:{type(exc).__name__}'


def fetch_product(stock_id: str, name: str) -> tuple[str,str,str]:
    url = f'{PRODUCT_URL}?{urlencode({"t":"company_product","stk":stock_id,"stkName":name})}'
    try:
        content = parse_product_page(request_bytes(url, timeout=20, retries=1))
        return url, content, 'ok' if content else 'empty'
    except Exception as exc:
        return url, '', f'error:{type(exc).__name__}'


def refresh_company_evidence(*, path: Path = DB_PATH, product_for_unmapped: bool = True,
                             max_workers: int = 16, max_age_days: int = 30) -> dict:
    """Fetch every target chain and product descriptions, with a 30-day cache."""
    init_evidence_db(path)
    now = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    stale_before = (datetime.fromisoformat(now) - timedelta(days=max_age_days)).isoformat(timespec='seconds')
    conn = sqlite3.connect(path)
    try:
        targets = conn.execute('''SELECT c.market,c.stock_id,c.name,
          EXISTS(SELECT 1 FROM fine_memberships m WHERE m.market=c.market AND m.stock_id=c.stock_id
          AND m.primary_for_flow=1 AND m.valid_to IS NULL) AS has_primary
          FROM fine_companies c WHERE c.active=1 AND c.is_target=1''').fetchall()
        chain_cache = {(r[0],r[1]):(r[2],r[3]) for r in conn.execute(
            'SELECT market,stock_id,status,fetched_at FROM official_chain_fetch')}
        product_cache = {(r[0],r[1]):(r[2],r[3]) for r in conn.execute(
            'SELECT market,stock_id,status,fetched_at FROM official_product_evidence')}
    finally:
        conn.close()
    work = []
    for market,stock_id,name,has_primary in targets:
        key = (market,stock_id)
        if key not in chain_cache or chain_cache[key][1] < stale_before:
            work.append(('chain',market,stock_id,name))
        if product_for_unmapped and (
            key not in product_cache or product_cache[key][1] < stale_before):
            work.append(('product',market,stock_id,name))
    results=[]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures={pool.submit(fetch_chain, stock_id) if kind=='chain' else pool.submit(fetch_product, stock_id, name):
                 (kind,market,stock_id) for kind,market,stock_id,name in work}
        for future in as_completed(futures):
            kind,market,stock_id=futures[future]
            try: result=future.result()
            except Exception as exc: result=('',[] if kind=='chain' else '',f'error:{type(exc).__name__}')
            results.append((kind,market,stock_id,result))
    conn=sqlite3.connect(path)
    try:
        with conn:
            for kind,market,stock_id,(url,payload,status) in results:
                if kind=='chain':
                    if status=='ok':
                        conn.execute('DELETE FROM official_chain_snapshot WHERE market=? AND stock_id=?',(market,stock_id))
                        conn.executemany('INSERT INTO official_chain_snapshot VALUES(?,?,?,?,?,?)',
                                         [(market,stock_id,l1,item,url,now) for l1,item in payload])
                    conn.execute('''INSERT INTO official_chain_fetch VALUES(?,?,?,?)
                      ON CONFLICT(market,stock_id) DO UPDATE SET status=excluded.status,fetched_at=excluded.fetched_at''',
                      (market,stock_id,status,now))
                else:
                    conn.execute('''INSERT INTO official_product_evidence VALUES(?,?,?,?,?,?)
                      ON CONFLICT(market,stock_id) DO UPDATE SET product_text=excluded.product_text,
                      source_url=excluded.source_url,status=excluded.status,fetched_at=excluded.fetched_at''',
                      (market,stock_id,payload,url,status,now))
    finally:
        conn.close()
    return {'targets':len(targets),'requests':len(work),
            'chain_requests':sum(r[0]=='chain' for r in results),
            'product_requests':sum(r[0]=='product' for r in results),
            'chain_ok':sum(r[0]=='chain' and r[3][2]=='ok' for r in results),
            'product_ok':sum(r[0]=='product' and r[3][2]=='ok' for r in results),
            'errors':[(r[1],r[2],r[3][2]) for r in results if r[3][2].startswith('error:')]}
