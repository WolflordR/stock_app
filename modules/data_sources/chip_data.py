import json
import sqlite3
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

from modules.core.project_paths import data_path
from modules.data_sources.market_watch import fetch_tpex_daily_quotes
from modules.data_sources.market_watch import fetch_twse_daily_quotes

DB_PATH = data_path("chip_cache.db")
TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
INVESTOR_COLUMN_MAP = {
    "三大法人": "total_net",
    "外資": "foreign_net",
    "投信": "trust_net",
    "自營商": "dealer_net",
}


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_chip_cache():
    """建立三大法人籌碼快取表。"""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS institutional_trading (
                market TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                code TEXT NOT NULL,
                name_zh TEXT NOT NULL,
                foreign_buy INTEGER NOT NULL,
                foreign_sell INTEGER NOT NULL,
                foreign_net INTEGER NOT NULL,
                trust_buy INTEGER NOT NULL,
                trust_sell INTEGER NOT NULL,
                trust_net INTEGER NOT NULL,
                dealer_buy INTEGER NOT NULL,
                dealer_sell INTEGER NOT NULL,
                dealer_net INTEGER NOT NULL,
                total_net INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (market, trade_date, code)
            )
            """
        )
        conn.commit()


def _parse_int(value):
    if value is None:
        return 0
    text = str(value).strip().replace(",", "")
    if text in {"", "--", "---", "nan"}:
        return 0
    return int(float(text))


def _fetch_json(url, params):
    ssl_context = ssl._create_unverified_context()
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", context=ssl_context, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _save_rows(market, trade_date, rows):
    fetched_at = datetime.now().isoformat(timespec="seconds")
    payload = [
        (
            market,
            trade_date,
            row["code"],
            row["name_zh"],
            row["foreign_buy"],
            row["foreign_sell"],
            row["foreign_net"],
            row["trust_buy"],
            row["trust_sell"],
            row["trust_net"],
            row["dealer_buy"],
            row["dealer_sell"],
            row["dealer_net"],
            row["total_net"],
            fetched_at,
        )
        for row in rows
    ]

    with _get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO institutional_trading (
                market, trade_date, code, name_zh,
                foreign_buy, foreign_sell, foreign_net,
                trust_buy, trust_sell, trust_net,
                dealer_buy, dealer_sell, dealer_net,
                total_net, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market, trade_date, code) DO UPDATE SET
                name_zh=excluded.name_zh,
                foreign_buy=excluded.foreign_buy,
                foreign_sell=excluded.foreign_sell,
                foreign_net=excluded.foreign_net,
                trust_buy=excluded.trust_buy,
                trust_sell=excluded.trust_sell,
                trust_net=excluded.trust_net,
                dealer_buy=excluded.dealer_buy,
                dealer_sell=excluded.dealer_sell,
                dealer_net=excluded.dealer_net,
                total_net=excluded.total_net,
                fetched_at=excluded.fetched_at
            """,
            payload,
        )
        conn.commit()


def _load_rows(market, trade_date):
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                code, name_zh,
                foreign_buy, foreign_sell, foreign_net,
                trust_buy, trust_sell, trust_net,
                dealer_buy, dealer_sell, dealer_net,
                total_net
            FROM institutional_trading
            WHERE market = ? AND trade_date = ?
            ORDER BY code
            """,
            (market, trade_date),
        ).fetchall()

    return [dict(row) for row in rows]


def _load_exact_cached_rows(market, trade_date):
    """只讀取指定日期本身的快取，不把更早資料冒充成當天資料。"""
    trade_date_str = pd.to_datetime(trade_date).strftime("%Y-%m-%d")
    # 週末本來就不應該有法人日資料；若舊快取裡有週末列，這裡直接忽略掉。
    if pd.to_datetime(trade_date_str).weekday() >= 5:
        return []
    return _load_rows(market, trade_date_str)


def _load_latest_cached_rows_on_or_before(market, trade_date):
    with _get_connection() as conn:
        latest_row = conn.execute(
            """
            SELECT trade_date
            FROM institutional_trading
            WHERE market = ? AND trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (market, trade_date),
        ).fetchone()

    if not latest_row:
        return None, []

    latest_trade_date = latest_row["trade_date"]
    return latest_trade_date, _load_rows(market, latest_trade_date)


def _load_recent_quote_df(fetcher, trade_date, max_calendar_lookback=5):
    trade_dt = pd.to_datetime(trade_date)
    for offset in range(max_calendar_lookback + 1):
        probe_dt = trade_dt - timedelta(days=offset)
        if probe_dt.weekday() >= 5:
            continue
        try:
            quote_df = fetcher(probe_dt.strftime("%Y-%m-%d"))
        except Exception:
            continue
        if quote_df.empty or not {"code", "close"}.issubset(quote_df.columns):
            continue
        return {
            "trade_date": probe_dt.strftime("%Y-%m-%d"),
            "quote_df": quote_df[["code", "close"]].copy(),
        }
    return None


def _load_quote_df_for_trade_date(trade_date, max_calendar_lookback=5):
    """
    上市 / 上櫃收盤價分開回退到最近可用交易日，再合併。
    避免單一市場暫時缺資料時，把另一個市場也一起拖掉。
    """
    listed_payload = _load_recent_quote_df(fetch_twse_daily_quotes, trade_date, max_calendar_lookback=max_calendar_lookback)
    otc_payload = _load_recent_quote_df(fetch_tpex_daily_quotes, trade_date, max_calendar_lookback=max_calendar_lookback)

    quote_frames = []
    trade_date_parts = []
    if listed_payload:
        quote_frames.append(listed_payload["quote_df"])
        trade_date_parts.append(f"上市:{listed_payload['trade_date']}")
    if otc_payload:
        quote_frames.append(otc_payload["quote_df"])
        trade_date_parts.append(f"上櫃:{otc_payload['trade_date']}")

    if not quote_frames:
        return None

    quote_df = pd.concat(quote_frames, ignore_index=True).drop_duplicates(subset=["code"], keep="first")
    return {
        "trade_date": " / ".join(trade_date_parts),
        "quote_df": quote_df,
    }


def _normalize_display_trade_date(trade_date):
    trade_ts = pd.to_datetime(trade_date)
    while trade_ts.weekday() >= 5:
        trade_ts -= timedelta(days=1)
    return trade_ts.strftime("%Y-%m-%d")


def fetch_twse_institutional_trading(trade_date):
    """抓取上市三大法人日資料，只接受指定日期本身的結果。"""
    init_chip_cache()
    trade_date_str = pd.to_datetime(trade_date).strftime("%Y-%m-%d")
    if pd.to_datetime(trade_date_str).weekday() >= 5:
        return []

    cached_rows = _load_exact_cached_rows("TWSE", trade_date_str)
    if cached_rows:
        return cached_rows

    try:
        payload = _fetch_json(
            TWSE_T86_URL,
            {
                "response": "json",
                "date": pd.to_datetime(trade_date).strftime("%Y%m%d"),
                "selectType": "ALLBUT0999",
            },
        )
    except Exception:
        return []

    data_rows = payload.get("data") or []
    parsed_rows = []
    for row in data_rows:
        if len(row) < 19:
            continue

        code = str(row[0]).strip()
        name_zh = str(row[1]).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue

        dealer_buy = _parse_int(row[12]) + _parse_int(row[15])
        dealer_sell = _parse_int(row[13]) + _parse_int(row[16])

        parsed_rows.append(
            {
                "code": code,
                "name_zh": name_zh,
                "foreign_buy": _parse_int(row[2]),
                "foreign_sell": _parse_int(row[3]),
                "foreign_net": _parse_int(row[4]),
                "trust_buy": _parse_int(row[8]),
                "trust_sell": _parse_int(row[9]),
                "trust_net": _parse_int(row[10]),
                "dealer_buy": dealer_buy,
                "dealer_sell": dealer_sell,
                "dealer_net": _parse_int(row[11]),
                "total_net": _parse_int(row[18]),
            }
        )

    if parsed_rows:
        _save_rows("TWSE", trade_date_str, parsed_rows)
        return parsed_rows

    return []


def build_institutional_rankings(trade_date, investor_type="三大法人", top_n=20, code_filter=""):
    """把指定日期的籌碼資料整理成買超、賣超排行與個股明細。"""
    snapshots = get_recent_institutional_snapshots(trade_date, trading_days=1)
    if not snapshots:
        return None

    effective_trade_date = _normalize_display_trade_date(snapshots[-1]["trade_date"])
    rows = snapshots[-1]["rows"]
    if not rows:
        return None

    df = pd.DataFrame(rows)
    if df.empty:
        return None

    column = INVESTOR_COLUMN_MAP[investor_type]
    quote_payload = _load_quote_df_for_trade_date(effective_trade_date)
    has_price_data = False
    price_trade_date = None
    if quote_payload is not None:
        merged_df = df.merge(quote_payload["quote_df"], on="code", how="left")
        if merged_df["close"].notna().any():
            df = merged_df
            df["estimated_amount"] = df[column] * df["close"]
            has_price_data = True
            price_trade_date = quote_payload["trade_date"]
        else:
            df["estimated_amount"] = pd.NA
    else:
        df["estimated_amount"] = pd.NA

    code_filter = (code_filter or "").strip()
    detail_row = None
    if code_filter:
        matched_df = df[df["code"] == code_filter]
        if not matched_df.empty:
            detail_row = matched_df.iloc[0].to_dict()

    buy_df = (
        df[df[column] > 0]
        .sort_values("estimated_amount" if has_price_data else column, ascending=False)
        .head(top_n)
        .copy()
    )
    sell_df = (
        df[df[column] < 0]
        .sort_values("estimated_amount" if has_price_data else column, ascending=True)
        .head(top_n)
        .copy()
    )

    if has_price_data:
        buy_df["estimated_amount"] = (buy_df["estimated_amount"] / 1_000_000).round(2)
        sell_df["estimated_amount"] = (sell_df["estimated_amount"] / 1_000_000).round(2)
    buy_df[column] = (buy_df[column] / 1000).round(1)
    sell_df[column] = (sell_df[column] / 1000).round(1)

    display_columns = ["code", "name_zh", "estimated_amount", column]
    rename_map = {
        "code": "代碼",
        "name_zh": "名稱",
        "estimated_amount": "估算資金(百萬元)",
        column: "買賣超股數(張)",
    }

    return {
        "trade_date": effective_trade_date,
        "price_trade_date": price_trade_date,
        "investor_type": investor_type,
        "has_price_data": has_price_data,
        "buy_rank_df": buy_df[display_columns].rename(columns=rename_map),
        "sell_rank_df": sell_df[display_columns].rename(columns=rename_map),
        "detail_row": detail_row,
        "data_count": len(df),
    }


def get_recent_institutional_snapshots(anchor_date, trading_days=3, max_calendar_lookback=14):
    """往前找最近幾個有資料的交易日。"""
    anchor_dt = pd.to_datetime(anchor_date)
    snapshots = []
    seen_trade_dates = set()

    for offset in range(max_calendar_lookback):
        current_dt = anchor_dt - timedelta(days=offset)
        current_date_str = current_dt.strftime("%Y-%m-%d")
        if current_dt.weekday() >= 5:
            continue

        rows = _load_exact_cached_rows("TWSE", current_date_str)
        if not rows:
            rows = fetch_twse_institutional_trading(current_date_str)

        normalized_trade_date = _normalize_display_trade_date(current_date_str)
        if not rows or normalized_trade_date in seen_trade_dates:
            continue

        seen_trade_dates.add(normalized_trade_date)
        snapshots.append(
            {
                "trade_date": normalized_trade_date,
                "rows": rows,
            }
        )
        if len(snapshots) >= trading_days:
            break

    return list(reversed(snapshots))


def _normalize_market_code(market):
    text = str(market or "").strip().upper()
    if text in {"TWSE", "上市"}:
        return "TWSE"
    if text in {"TPEX", "TPEx", "上櫃", "OTC"}:
        return "TPEX"
    return text or "TWSE"


def get_institutional_detail_for_stock(stock_code, trade_date, market="TWSE"):
    """直接回傳單一股票在指定交易日的三大法人淨買賣超。"""
    init_chip_cache()
    trade_date_str = _normalize_display_trade_date(trade_date)
    market_code = _normalize_market_code(market)
    if market_code != "TWSE":
        return None

    rows = _load_exact_cached_rows("TWSE", trade_date_str)
    if not rows:
        rows = fetch_twse_institutional_trading(trade_date_str)

    matched = next((row for row in rows if str(row.get("code")) == str(stock_code)), None)
    if not matched:
        return None

    return {
        "trade_date": trade_date_str,
        "foreign_net": matched.get("foreign_net"),
        "trust_net": matched.get("trust_net"),
        "dealer_net": matched.get("dealer_net"),
        "total_net": matched.get("total_net"),
    }


def build_consecutive_institutional_rankings(
    anchor_date,
    investor_type="三大法人",
    consecutive_days=3,
    top_n=10,
):
    """找出最近 N 個交易日每天都排進前 N 名，且以估算資金力道排序的股票。"""
    snapshots = get_recent_institutional_snapshots(anchor_date, consecutive_days)
    if len(snapshots) < consecutive_days:
        return None

    investor_column = INVESTOR_COLUMN_MAP[investor_type]
    ordered_dates = [snapshot["trade_date"] for snapshot in snapshots]
    buy_top_sets = []
    sell_top_sets = []
    daily_frames = []

    for snapshot in snapshots:
        trade_date = snapshot["trade_date"]
        day_df = pd.DataFrame(snapshot["rows"])[["code", "name_zh", investor_column]].copy()
        if day_df.empty:
            return None

        quote_payload = _load_quote_df_for_trade_date(trade_date)
        has_price_data = False
        if quote_payload is not None:
            merged_df = day_df.merge(quote_payload["quote_df"], on="code", how="left")
            if merged_df["close"].notna().any():
                day_df = merged_df
                day_df["estimated_amount"] = day_df[investor_column] * day_df["close"]
                has_price_data = True
            else:
                day_df["estimated_amount"] = pd.NA
        else:
            day_df["estimated_amount"] = pd.NA
        buy_top_sets.append(
            set(
                day_df[day_df[investor_column] > 0]
                .sort_values("estimated_amount" if has_price_data else investor_column, ascending=False)
                .head(top_n)["code"]
            )
        )
        sell_top_sets.append(
            set(
                day_df[day_df[investor_column] < 0]
                .sort_values("estimated_amount" if has_price_data else investor_column, ascending=True)
                .head(top_n)["code"]
            )
        )

        day_subset = day_df[["code", "name_zh", investor_column, "estimated_amount"]].rename(
            columns={
                investor_column: f"{trade_date}_股數",
                "estimated_amount": f"{trade_date}_金額",
            }
        )
        daily_frames.append(day_subset)

    if not daily_frames:
        return None

    buy_intersection = set.intersection(*buy_top_sets) if buy_top_sets else set()
    sell_intersection = set.intersection(*sell_top_sets) if sell_top_sets else set()

    merged_df = daily_frames[0]
    for day_subset in daily_frames[1:]:
        merged_df = merged_df.merge(day_subset, on=["code", "name_zh"], how="inner")

    if merged_df.empty:
        return None

    amount_columns = [f"{trade_date}_金額" for trade_date in ordered_dates]
    share_columns = [f"{trade_date}_股數" for trade_date in ordered_dates]
    merged_df["累計資金"] = merged_df[amount_columns].sum(axis=1, min_count=1)
    merged_df["累計股數"] = merged_df[share_columns].sum(axis=1)

    has_amount_data = merged_df[amount_columns].notna().any().any()
    sort_column = "累計資金" if has_amount_data else "累計股數"
    buy_df = merged_df[merged_df["code"].isin(buy_intersection)].sort_values(sort_column, ascending=False).head(top_n).copy()
    sell_df = merged_df[merged_df["code"].isin(sell_intersection)].sort_values(sort_column, ascending=True).head(top_n).copy()

    display_columns = ["code", "name_zh"]
    for trade_date in ordered_dates:
        display_columns.extend([f"{trade_date}_金額", f"{trade_date}_股數"])
    display_columns.extend(["累計資金", "累計股數"])

    rename_map = {
        "code": "代碼",
        "name_zh": "名稱",
        "累計資金": f"{consecutive_days}日累計資金(百萬元)",
        "累計股數": f"{consecutive_days}日累計股數(張)",
    }
    for trade_date in ordered_dates:
        rename_map[f"{trade_date}_金額"] = f"{trade_date}資金(百萬元)"
        rename_map[f"{trade_date}_股數"] = f"{trade_date}股數(張)"

    def _safe_scale_and_round(frame, column_name, divisor, digits):
        numeric_series = pd.to_numeric(frame[column_name], errors="coerce")
        frame[column_name] = (numeric_series / divisor).round(digits)

    for frame in (buy_df, sell_df):
        for trade_date in ordered_dates:
            if has_amount_data:
                _safe_scale_and_round(frame, f"{trade_date}_金額", 1_000_000, 2)
            _safe_scale_and_round(frame, f"{trade_date}_股數", 1000, 1)
        if has_amount_data:
            _safe_scale_and_round(frame, "累計資金", 1_000_000, 2)
        _safe_scale_and_round(frame, "累計股數", 1000, 1)

    return {
        "investor_type": investor_type,
        "trade_dates": ordered_dates,
        "has_price_data": has_amount_data,
        "ranking_rule": (
            f"最近 {consecutive_days} 個交易日每天都在前 {top_n} 名，並以買賣超股數 × 當日收盤價估算資金力道"
            if has_amount_data else
            f"最近 {consecutive_days} 個交易日每天都在前 {top_n} 名；因當日收盤價來源暫時不可用，先以買賣超股數排序"
        ),
        "buy_rank_df": buy_df[display_columns].rename(columns=rename_map),
        "sell_rank_df": sell_df[display_columns].rename(columns=rename_map),
    }
