"""Fine-sector rotation scores, verified institutional shares, and market pressure."""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median

import pandas as pd

from modules.backtest.signals.initial_rise import analyze_initial_rise_candidate
from modules.core.http_utils import request_bytes
from modules.core.project_paths import data_path, db_path
from modules.data_sources.chip_data import DB_PATH as CHIP_DB, fetch_tpex_institutional_trading, fetch_twse_institutional_trading
from modules.industry.electronics_universe import DB_PATH
from modules.industry.fine_classification import init_fine_db
from modules.industry.classification_v4 import init_classification_v4

PRICE_DB = db_path('price_cache.db')
SPEC = json.loads(data_path('sector_rotation/flow_rotation_spec_v3.json').read_text())
WEIGHTS = SPEC['rotation_score']
WINDOWS = (1, 3, 5, 20)


@contextmanager
def _connection(path: Path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _clip(v: float, low: float, high: float) -> float:
    return max(low,min(high,v))


def init_rotation_db(path: Path = DB_PATH) -> None:
    init_fine_db(path)
    init_classification_v4(path)
    with _connection(path) as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS benchmark_daily (
          market TEXT NOT NULL,trade_date TEXT NOT NULL,close REAL NOT NULL,source_url TEXT NOT NULL,
          PRIMARY KEY(market,trade_date));
        CREATE TABLE IF NOT EXISTS rotation_stock_daily (
          trade_date TEXT NOT NULL,market TEXT NOT NULL,stock_id TEXT NOT NULL,
          primary_sector_key TEXT,return_1d REAL,return_5d REAL,return_20d REAL,
          turnover REAL,volume_ratio REAL,breakout INTEGER,cmf_20 REAL,mfi_14 REAL,
          pressure REAL,early_rise INTEGER,institutional_net_shares INTEGER,
          foreign_net_shares INTEGER,trust_net_shares INTEGER,dealer_net_shares INTEGER,
          PRIMARY KEY(trade_date,market,stock_id));
        CREATE TABLE IF NOT EXISTS rotation_daily (
          trade_date TEXT NOT NULL,level INTEGER NOT NULL,sector_key TEXT NOT NULL,
          l1 TEXT NOT NULL,l2 TEXT,l3 TEXT,constituent_count INTEGER NOT NULL,
          observed_count INTEGER NOT NULL,coverage_ratio REAL NOT NULL,
          return_1d REAL,return_5d REAL,return_20d REAL,breadth REAL,
          turnover REAL,turnover_share REAL,turnover_share_delta REAL,turnover_expansion REAL,
          breakout_participation REAL,accumulation_pressure REAL,relative_strength REAL,
          rs_momentum REAL,rotation_score REAL,stage TEXT,rank_eligible INTEGER NOT NULL,
          top1_turnover_share REAL,top3_turnover_share REAL,concentrated INTEGER NOT NULL,
          institutional_net_shares INTEGER,institutional_coverage REAL,
          breadth_quality TEXT NOT NULL,pressure_source TEXT NOT NULL,
          PRIMARY KEY(trade_date,level,sector_key));
        CREATE INDEX IF NOT EXISTS idx_rotation_rank ON rotation_daily(trade_date,level,rotation_score DESC);
        ''')


def refresh_benchmarks(*, anchor: str | None = None, months: int = 4, path: Path = DB_PATH) -> dict:
    init_rotation_db(path)
    today = date.fromisoformat(anchor) if anchor else date.today()
    month_starts=[]
    for offset in range(months):
        y=today.year; m=today.month-offset
        while m <= 0: m+=12; y-=1
        month_starts.append(date(y,m,1))
    records=[]; errors=[]
    for day in month_starts:
        twse_url=f'https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={day:%Y%m%d}&response=json'
        tpex_url=f'https://www.tpex.org.tw/www/zh-tw/indexInfo/inx?date={day.year-1911}/{day.month:02d}'
        for market,url in [('TWSE',twse_url),('TPEx',tpex_url)]:
            try:
                payload=json.loads(request_bytes(url,timeout=30).decode('utf-8-sig'))
                rows=payload.get('data',[]) if market=='TWSE' else payload.get('tables',[{}])[0].get('data',[])
                for item in rows:
                    raw=item[0].replace('/','-')
                    if market=='TWSE':
                        year,month,d=map(int,raw.split('-')); raw=f'{year+1911:04d}-{month:02d}-{d:02d}'
                    records.append((market,raw,float(str(item[4]).replace(',','')),url))
            except Exception as exc:
                errors.append(f'{market}:{day:%Y-%m}:{type(exc).__name__}')
    with _connection(path) as conn:
        conn.executemany('INSERT INTO benchmark_daily VALUES(?,?,?,?) ON CONFLICT(market,trade_date) DO UPDATE SET close=excluded.close,source_url=excluded.source_url',records)
    return {'rows':len(records),'errors':errors}


def refresh_institutional(*, trade_days: int = 20, price_path: Path = PRICE_DB) -> dict:
    with _connection(price_path) as conn:
        days=[r[0] for r in conn.execute('''SELECT trade_date FROM price_history
          WHERE symbol LIKE '%.TW' OR symbol LIKE '%.TWO' GROUP BY trade_date
          HAVING COUNT(DISTINCT symbol)>=500 ORDER BY trade_date DESC LIMIT ?''',(trade_days,))]
    counts={'TWSE':0,'TPEx':0}; missing=[]
    for day in reversed(days):
        for market,fetch in [('TWSE',fetch_twse_institutional_trading),('TPEx',fetch_tpex_institutional_trading)]:
            try: rows=fetch(day)
            except Exception: rows=[]
            if rows: counts[market]+=1
            else: missing.append(f'{market}:{day}')
    return {'trade_days':len(days),'covered_days':counts,'missing':missing}


def _features(history: list[tuple], anchor: str) -> dict | None:
    if len(history)<26 or history[-1][0]!=anchor: return None
    latest=history[-1]; close=float(latest[4] or 0); volume=float(latest[5] or 0)
    if close<=0 or volume<=0 or any(float(history[-1-n][4] or 0)<=0 for n in WINDOWS): return None
    returns={n:100*(close/float(history[-1-n][4])-1) for n in WINDOWS}
    turnover=close*volume
    prior_turnovers=[float(x[4] or 0)*float(x[5] or 0) for x in history[-6:-1]]
    avg_turnover=mean(prior_turnovers) if prior_turnovers else 0
    previous_high=max(float(x[2] or 0) for x in history[-21:-1])
    # CMF20 uses close location within the day's range, weighted by reported volume.
    mfv=0.0; total_volume=0.0
    for _,low,high,_,c,v in history[-20:]:
        low=float(low or 0);high=float(high or 0);c=float(c or 0);v=float(v or 0)
        if high>low and v>0:
            mfv+=((2*c-high-low)/(high-low))*v;total_volume+=v
    cmf=mfv/total_volume if total_volume else None
    positive=negative=0.0
    for prior,current in zip(history[-15:-1],history[-14:]):
        typical=lambda r: mean([float(r[1] or 0),float(r[2] or 0),float(r[4] or 0)])
        flow=typical(current)*float(current[5] or 0)
        if typical(current)>typical(prior): positive+=flow
        elif typical(current)<typical(prior): negative+=flow
    mfi=100*positive/(positive+negative) if positive+negative>0 else None
    pressure=(0.5*(cmf or 0)+0.5*((mfi-50)/50 if mfi is not None else 0))
    return {'returns':returns,'turnover':turnover,'turnover_expansion':turnover/avg_turnover if avg_turnover>0 else None,
            'volume_ratio':volume/mean(float(x[5] or 0) for x in history[-21:-1]) if mean(float(x[5] or 0) for x in history[-21:-1])>0 else None,
            'breakout':int(previous_high>0 and close>previous_high),'cmf':cmf,'mfi':mfi,'pressure':pressure}


def _stock_history(anchor: str, price_path: Path) -> dict[str,list[tuple]]:
    cutoff=(date.fromisoformat(anchor)-timedelta(days=100)).isoformat()
    history=defaultdict(list)
    with _connection(price_path) as conn:
        for symbol,trade_date,low,high,open_,close,volume in conn.execute('''SELECT symbol,trade_date,low,high,open,close,volume
          FROM price_history WHERE trade_date BETWEEN ? AND ? AND (symbol LIKE '%.TW' OR symbol LIKE '%.TWO')
          ORDER BY symbol,trade_date''',(cutoff,anchor)):
            history[symbol].append((trade_date,low,high,open_,close,volume))
    return history


def _stage(score: float, rs: float, momentum: float, breadth: float, concentrated: bool) -> str:
    if score>=72 and rs>0 and breadth>=0.55: return 'Crowded' if concentrated and score>=80 else 'Leading'
    if rs>0 and momentum>0 and score>=56: return 'Early Rotation'
    if momentum>0 and score>=45: return 'Improving'
    if momentum<0 and rs>0: return 'Weakening'
    return 'Dormant'


def _sector_metrics(stocks: list[dict], *, total_turnover: float, prior_share: float | None,
                    benchmark_returns: dict[str,float | None], constituents: int, minimum: int=5) -> dict:
    n=len(stocks)
    if not n: return {}
    returns=lambda window:[_clip(s[f'return_{window}d'],-60,60) for s in stocks if s[f'return_{window}d'] is not None]
    r1=returns(1);r5=returns(5);r20=returns(20)
    if not r1: return {}
    breadth=sum(r>0 for r in r1)/len(r1)
    # Rotation signals use all verified constituents; additive amounts use only
    # companies whose single primary classification belongs to this sector.
    primary_stocks=[s for s in stocks if 'primary_sector_key' not in s or
                    (s['primary_sector_key'] and (
                     s['primary_sector_key']==s.get('_group_sector_key') or
                     s['primary_sector_key'].startswith(s.get('_group_sector_key','')+' > ')))]
    turnover=sum(s['turnover'] for s in primary_stocks)
    share=turnover/total_turnover if total_turnover>0 else 0
    expansion=median([s['turnover_expansion'] for s in stocks if s['turnover_expansion'] is not None]) if any(s['turnover_expansion'] is not None for s in stocks) else 1
    breakout=mean(s['breakout'] for s in stocks)
    pressure=median(s['pressure'] for s in stocks)
    comparable=[s['return_20d']-benchmark_returns[s['market']] for s in stocks if s['return_20d'] is not None and benchmark_returns.get(s['market']) is not None]
    rs=median(comparable) if comparable else None
    rs5=[s['return_5d']-benchmark_returns.get(s['market']+'_5',0) for s in stocks if s['return_5d'] is not None and benchmark_returns.get(s['market']+'_5') is not None]
    rs_momentum=(median(rs5)-((rs or 0)/4)) if rs5 and rs is not None else None
    ranked_turnovers=sorted((s['turnover'] for s in primary_stocks),reverse=True)
    top1=ranked_turnovers[0]/turnover if turnover and ranked_turnovers else 0
    top3=sum(ranked_turnovers[:3])/turnover if turnover else 0
    concentrated=top1>=0.4 or (n>=5 and top3>=0.7)
    institutional=[s['institutional_net_shares'] for s in primary_stocks if s['institutional_net_shares'] is not None]
    signals={
      'relative_strength':_clip(50+4*(rs or 0),0,100),
      'breadth':breadth*100,
      'turnover_expansion':_clip(50+30*math.log2(max(expansion,0.01)),0,100),
      'price_momentum':_clip(50+4*median(r5 or [0]),0,100),
      'breakout_participation':breakout*100,
      'accumulation_pressure':_clip(50+50*pressure,0,100),
    }
    score=sum(WEIGHTS[k]*signals[k] for k in WEIGHTS)
    quality='good' if n/constituents>=0.8 and n>=minimum else 'partial' if n/constituents>=0.5 else 'low'
    return {'constituent_count':constituents,'observed_count':n,'coverage_ratio':n/constituents,
            'return_1d':median(r1),'return_5d':median(r5) if r5 else None,'return_20d':median(r20) if r20 else None,
            'breadth':breadth,'turnover':turnover,'turnover_share':share,
            'turnover_share_delta':share-prior_share if prior_share is not None else None,
            'turnover_expansion':expansion,'breakout_participation':breakout,'accumulation_pressure':pressure,
            'relative_strength':rs,'rs_momentum':rs_momentum,'rotation_score':round(score,2),
            'stage':_stage(score,rs or 0,rs_momentum or 0,breadth,concentrated),
            'rank_eligible':int(n>=minimum and n/constituents>=0.6 and rs is not None),
            'top1_turnover_share':top1,'top3_turnover_share':top3,'concentrated':int(concentrated),
            'institutional_net_shares':sum(institutional) if institutional else None,
            'institutional_coverage':len(institutional)/len(primary_stocks) if primary_stocks else 0,
            'breadth_quality':quality,
            'pressure_source':'OHLCV_ESTIMATE_CMF_MFI'}


def refresh_rotation(*, anchor: str | None = None, path: Path = DB_PATH, price_path: Path = PRICE_DB,
                     chip_path: Path = CHIP_DB, compute_early_rise: bool = True) -> dict:
    init_rotation_db(path)
    with _connection(price_path) as conn:
        anchor=anchor or conn.execute('SELECT MAX(trade_date) FROM price_history').fetchone()[0]
    if not anchor: return {'trade_date':None,'rows':0}
    with _connection(path) as conn:
        conn.row_factory=sqlite3.Row
        members=[dict(r) for r in conn.execute('''SELECT DISTINCT c.market,c.stock_id,c.name,t.l1,t.l2,t.l3,m.sector_key,
          p.sector_key AS primary_sector_key
          FROM stock_sector_memberships m JOIN fine_companies c USING(market,stock_id)
          JOIN fine_taxonomy t ON t.sector_key=m.sector_key
          LEFT JOIN stock_primary_sector p ON p.market=m.market AND p.stock_id=m.stock_id AND p.valid_to IS NULL
          WHERE c.active=1 AND c.is_target=1 AND m.valid_to IS NULL''')]
        benchmarks=defaultdict(dict)
        for market,d,close in conn.execute('SELECT market,trade_date,close FROM benchmark_daily WHERE trade_date<=? ORDER BY trade_date',(anchor,)):
            benchmarks[market][d]=close
    if not members: return {'trade_date':anchor,'rows':0,'reason':'classification_empty'}
    histories=_stock_history(anchor,price_path)
    institutional={}
    with _connection(chip_path) as conn:
        for row in conn.execute('''SELECT market,code,total_net,foreign_net,trust_net,dealer_net
          FROM institutional_trading WHERE trade_date=?''',(anchor,)):
            institutional[(row[0],row[1])]=row[2:]
    benchmark_returns={}
    for market,series in benchmarks.items():
        dates=sorted(d for d in series if d<=anchor)
        if anchor in series and len(dates)>=21:
            for n,suffix in [(20,''),(5,'_5')]: benchmark_returns[market+suffix]=100*(series[anchor]/series[dates[-n-1]]-1)
    stock_rows=[];features_by_key={}
    for member in members:
        key=(member['market'],member['stock_id'])
        if key in features_by_key: continue
        symbol=member['stock_id']+('.TW' if member['market']=='TWSE' else '.TWO')
        history=histories.get(symbol,[])
        feature=_features(history,anchor)
        if feature is None: continue
        inst=institutional.get(key)
        early=0
        if compute_early_rise and len(history)>=26:
            frame=pd.DataFrame([{'Open':r[3],'High':r[2],'Low':r[1],'Close':r[4],'Volume':r[5]} for r in history],
                               index=pd.to_datetime([r[0] for r in history]))
            try:
                signal=analyze_initial_rise_candidate(frame,stock_id=member['stock_id'],as_of_date=anchor)
                early=int(bool(signal and signal.get('matched')))
            except Exception: early=0
        row={'trade_date':anchor,'market':key[0],'stock_id':key[1],'primary_sector_key':member['primary_sector_key'],
             **{f'return_{n}d':feature['returns'][n] for n in (1,5,20)},
             'turnover':feature['turnover'],'turnover_expansion':feature['turnover_expansion'],
             'volume_ratio':feature['volume_ratio'],'breakout':feature['breakout'],
             'cmf_20':feature['cmf'],'mfi_14':feature['mfi'],'pressure':feature['pressure'],
             'early_rise':early,'institutional_net_shares':inst[0] if inst else None,
             'foreign_net_shares':inst[1] if inst else None,'trust_net_shares':inst[2] if inst else None,
             'dealer_net_shares':inst[3] if inst else None}
        stock_rows.append(row);features_by_key[key]=row
    total_turnover=sum(r['turnover'] for r in stock_rows if r['primary_sector_key'])
    groups=defaultdict(list);all_counts=defaultdict(int);labels={};seen_members=set()
    for m in members:
        for level,sector in [(1,m['l1']),(2,' > '.join((m['l1'],m['l2']))),(3,m['sector_key'])]:
            group=(level,sector);member_key=(*group,m['market'],m['stock_id'])
            if member_key in seen_members: continue
            seen_members.add(member_key);all_counts[group]+=1
            labels[group]=(m['l1'],m['l2'] if level>=2 else None,m['l3'] if level==3 else None)
            if (m['market'],m['stock_id']) in features_by_key:
                groups[group].append({**features_by_key[(m['market'],m['stock_id'])], '_group_sector_key':sector})
    with _connection(path) as conn:
        previous_date=conn.execute('SELECT MAX(trade_date) FROM rotation_daily WHERE trade_date<?',(anchor,)).fetchone()[0]
        prior_shares={(r[0],r[1]):r[2] for r in conn.execute(
            'SELECT level,sector_key,turnover_share FROM rotation_daily WHERE trade_date=?',(previous_date,))} if previous_date else {}
    daily_rows=[]
    for group,stocks in groups.items():
        level,sector=group
        result=_sector_metrics(stocks,total_turnover=total_turnover,prior_share=prior_shares.get(group),
                               benchmark_returns=benchmark_returns,constituents=all_counts[group])
        if result:
            l1,l2,l3=labels[group]
            daily_rows.append({'trade_date':anchor,'level':level,'sector_key':sector,'l1':l1,'l2':l2,'l3':l3,**result})
    stock_fields=['trade_date','market','stock_id','primary_sector_key','return_1d','return_5d','return_20d',
                  'turnover','volume_ratio','breakout','cmf_20','mfi_14','pressure','early_rise',
                  'institutional_net_shares','foreign_net_shares','trust_net_shares','dealer_net_shares']
    metric_fields=['trade_date','level','sector_key','l1','l2','l3','constituent_count','observed_count','coverage_ratio',
                   'return_1d','return_5d','return_20d','breadth','turnover','turnover_share','turnover_share_delta',
                   'turnover_expansion','breakout_participation','accumulation_pressure','relative_strength','rs_momentum',
                   'rotation_score','stage','rank_eligible','top1_turnover_share','top3_turnover_share','concentrated',
                   'institutional_net_shares','institutional_coverage','breadth_quality','pressure_source']
    with _connection(path) as conn:
        conn.execute('DELETE FROM rotation_stock_daily WHERE trade_date=?',(anchor,))
        conn.execute('DELETE FROM rotation_daily WHERE trade_date=?',(anchor,))
        conn.executemany(f'INSERT INTO rotation_stock_daily({",".join(stock_fields)}) VALUES({",".join("?" for _ in stock_fields)})',
                         [tuple(r.get(f) for f in stock_fields) for r in stock_rows])
        conn.executemany(f'INSERT INTO rotation_daily({",".join(metric_fields)}) VALUES({",".join("?" for _ in metric_fields)})',
                         [tuple(r.get(f) for f in metric_fields) for r in daily_rows])
    return {'trade_date':anchor,'stocks':len(stock_rows),'rows':len(daily_rows),
            'ranked_l3':sum(r['rank_eligible'] for r in daily_rows if r['level']==3),
            'institutional_covered':sum(r['institutional_net_shares'] is not None for r in stock_rows),
            'benchmark_markets':sorted(k for k in benchmark_returns if not k.endswith('_5'))}


def backfill_rotation(*, trade_days: int = 20, path: Path = DB_PATH, price_path: Path = PRICE_DB) -> list[dict]:
    with _connection(price_path) as conn:
        days=[r[0] for r in conn.execute('''SELECT trade_date FROM price_history WHERE symbol LIKE '%.TW' OR symbol LIKE '%.TWO'
          GROUP BY trade_date HAVING COUNT(DISTINCT symbol)>=500 ORDER BY trade_date DESC LIMIT ?''',(trade_days,))]
    return [refresh_rotation(anchor=day,path=path,price_path=price_path,compute_early_rise=day==days[0]) for day in reversed(days)]


def _dicts(conn,query,params=()):
    conn.row_factory=sqlite3.Row
    return [dict(r) for r in conn.execute(query,params)]


def get_rotation_ranking(*, trade_date: str | None=None,level: int=3,l1: str | None=None,l2: str | None=None,
                         include_small: bool=False,path: Path=DB_PATH) -> list[dict]:
    if level not in (1,2,3): raise ValueError('level must be 1, 2, or 3')
    init_rotation_db(path)
    with _connection(path) as conn:
        trade_date=trade_date or conn.execute('SELECT MAX(trade_date) FROM rotation_daily').fetchone()[0]
        if not trade_date:return []
        return _dicts(conn,'''SELECT * FROM rotation_daily WHERE trade_date=? AND level=?
          AND (? IS NULL OR l1=?) AND (? IS NULL OR l2=?) AND (? OR rank_eligible=1)
          ORDER BY rank_eligible DESC,rotation_score DESC,observed_count DESC''',
          (trade_date,level,l1,l1,l2,l2,int(include_small)))


def get_rotation_filters(path: Path=DB_PATH) -> list[dict]:
    init_rotation_db(path)
    with _connection(path) as conn:
        return _dicts(conn,'''SELECT DISTINCT t.l1,t.l2 FROM fine_taxonomy t
          JOIN stock_sector_memberships m ON m.sector_key=t.sector_key
          JOIN fine_companies c ON c.market=m.market AND c.stock_id=m.stock_id
          WHERE c.active=1 AND c.is_target=1 AND m.valid_to IS NULL
          ORDER BY t.l1,t.l2''')


def get_rotation_detail(sector_key: str,*,trade_date: str | None=None,path: Path=DB_PATH) -> dict:
    init_rotation_db(path)
    with _connection(path) as conn:
        trade_date=trade_date or conn.execute('SELECT MAX(trade_date) FROM rotation_daily').fetchone()[0]
        if not trade_date:return {'sector':None,'stocks':[],'timeline':[],'diff':None}
        level=sector_key.count(' > ')+1
        sector=_dicts(conn,'SELECT * FROM rotation_daily WHERE trade_date=? AND level=? AND sector_key=?',(trade_date,level,sector_key))
        if not sector:return {'sector':None,'stocks':[],'timeline':[],'diff':None}
        where='t.l1=?' if level==1 else 't.l1||" > "||t.l2=?' if level==2 else 'm.sector_key=?'
        stocks=_dicts(conn,f'''SELECT c.market,c.stock_id,c.name,c.official_industry_code,
          s.trade_date,s.primary_sector_key,s.return_1d,s.return_5d,s.return_20d,
          s.turnover,s.volume_ratio,s.breakout,s.early_rise,s.institutional_net_shares,
          MAX(CASE WHEN p.sector_key=? OR p.sector_key LIKE ? THEN 1 ELSE 0 END) AS is_primary_here,
          GROUP_CONCAT(DISTINCT m.source) AS classification_source
          FROM stock_sector_memberships m JOIN fine_companies c
            ON c.market=m.market AND c.stock_id=m.stock_id AND c.active=1 AND c.is_target=1
          JOIN fine_taxonomy t ON t.sector_key=m.sector_key
          LEFT JOIN stock_primary_sector p ON p.market=c.market AND p.stock_id=c.stock_id AND p.valid_to IS NULL
          LEFT JOIN rotation_stock_daily s ON s.market=c.market AND s.stock_id=c.stock_id AND s.trade_date=?
          WHERE m.valid_to IS NULL AND {where}
          GROUP BY c.market,c.stock_id ORDER BY s.return_1d DESC''',
          (sector_key,sector_key+' > %',trade_date,sector_key))
        timeline=_dicts(conn,'''SELECT trade_date,rotation_score,stage,relative_strength,rs_momentum,breadth,turnover_share,
          institutional_net_shares FROM rotation_daily WHERE level=? AND sector_key=? AND trade_date<=?
          ORDER BY trade_date DESC LIMIT 20''',(level,sector_key,trade_date))
        timeline.reverse()
        previous=timeline[-2] if len(timeline)>1 else None
        current=sector[0]
        rank_change=None
        if previous:
            def rank_for(day: str) -> int | None:
                ranked=[r[0] for r in conn.execute('''SELECT sector_key FROM rotation_daily
                  WHERE trade_date=? AND level=? AND rank_eligible=1 ORDER BY rotation_score DESC''',(day,level))]
                return ranked.index(sector_key)+1 if sector_key in ranked else None
            current_rank=rank_for(trade_date)
            previous_rank=rank_for(previous['trade_date'])
            if current_rank is not None and previous_rank is not None:
                rank_change=previous_rank-current_rank
        diff={'score_delta':current['rotation_score']-previous['rotation_score'],
              'rank_change':rank_change,'stage_from':previous['stage'],'stage_to':current['stage'],
              'breadth_delta':current['breadth']-previous['breadth']} if previous else None
        return {'sector':current,'stocks':stocks,'timeline':timeline,'diff':diff,
                'leaders':sorted([s for s in stocks if s['return_5d'] is not None],
                                 key=lambda s:s['return_5d'],reverse=True)[:8],
                'early_rotation':sorted([s for s in stocks if s['early_rise'] or (s['return_1d'] or 0)>0 and (s['return_5d'] or 0)<8],key=lambda s:(s['early_rise'],s['volume_ratio'] or 0),reverse=True)[:8],
                'followers':sorted([s for s in stocks if (s['return_1d'] or 0)>0 and (s['return_5d'] or 0)<5],key=lambda s:s['return_1d'],reverse=True)[:8],
                'institutional_buy':sorted([s for s in stocks if (s['institutional_net_shares'] or 0)>0],key=lambda s:s['institutional_net_shares'],reverse=True)[:8],
                'volume_surge':sorted([s for s in stocks if s['volume_ratio'] is not None],
                                      key=lambda s:s['volume_ratio'],reverse=True)[:8],
                'breakouts':[s for s in stocks if s['breakout']][:8]}
