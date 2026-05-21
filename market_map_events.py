from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
import hashlib
import json
from urllib.parse import parse_qs
from urllib.parse import urlparse

import pandas as pd

from http_utils import request_text
from market_map_db import _get_connection
from market_map_db import ensure_market_map_db


TWSE_MAJOR_INFO_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
TPEX_MARKET_IMPORTANT_URL = "https://www.tpex.org.tw/www/zh-tw/home/information"
EVENT_CACHE_MINUTES = 30


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _roc_date_to_iso(value):
    raw = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    if len(raw) < 7:
        return None
    roc_year = int(raw[:-4])
    month = int(raw[-4:-2])
    day = int(raw[-2:])
    return f"{roc_year + 1911:04d}-{month:02d}-{day:02d}"


def _roc_slash_date_to_iso(value):
    parts = [part for part in str(value or "").strip().split("/") if part]
    if len(parts) != 3:
        return None
    roc_year, month, day = (int(part) for part in parts)
    return f"{roc_year + 1911:04d}-{month:02d}-{day:02d}"


def _raw_time_to_hms(value):
    raw = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    if not raw:
        return None
    raw = raw.zfill(6)
    return f"{raw[:2]}:{raw[2:4]}:{raw[4:6]}"


def _build_event_at(event_date, event_time):
    if not event_date:
        return None
    if event_time:
        return f"{event_date} {event_time}"
    return f"{event_date} 00:00:00"


def _extract_company_code_from_url(url):
    query = parse_qs(urlparse(str(url or "")).query)
    company_id = (query.get("COMPANY_ID") or [""])[0].strip()
    if company_id.isdigit():
        return company_id.zfill(4)
    return None


def _classify_event_type(title, detail=""):
    text = f"{title or ''} {detail or ''}"
    lowered = text.lower()
    if any(keyword in text for keyword in ["全額交割", "變更交易方法", "退票", "訴訟", "停工", "重訊說明", "重大損失"]):
        return "risk"
    if any(keyword in text for keyword in ["董事會", "股東會", "改選董事", "獨立董事", "審計委員會"]):
        return "board"
    if any(keyword in text for keyword in ["現金增資", "私募", "可轉換公司債", "公司債", "現增", "募資", "減資"]):
        return "capital"
    if any(keyword in text for keyword in ["法說", "法人說明會", "業績發表", "說明會"]):
        return "conference"
    if any(keyword in text for keyword in ["接單", "合作", "合約", "標案", "新藥", "臨床", "藥證", "出貨", "投資"]):
        return "operational"
    if any(keyword in lowered for keyword in ["clinical", "order", "partnership", "contract"]):
        return "operational"
    return "general"


def _severity_score(event_type, title):
    base_score_map = {
        "risk": 9.0,
        "capital": 7.0,
        "operational": 6.5,
        "conference": 5.0,
        "board": 4.5,
        "general": 3.5,
    }
    score = base_score_map.get(event_type, 3.5)
    text = str(title or "")
    if any(keyword in text for keyword in ["全額交割", "退票", "訴訟", "停工", "虧損"]):
        score += 1.5
    if any(keyword in text for keyword in ["接單", "合作", "新藥", "臨床", "藥證", "投資"]):
        score += 0.8
    return score


def _event_key(source, company_code, event_date, event_time, title):
    raw = "|".join(
        [
            str(source or ""),
            str(company_code or ""),
            str(event_date or ""),
            str(event_time or ""),
            str(title or ""),
        ]
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _fetch_twse_major_info_df():
    try:
        payload = json.loads(request_text(TWSE_MAJOR_INFO_URL, encoding="utf-8", errors="replace"))
    except Exception:
        return pd.DataFrame()
    rows = []
    for item in payload:
        company_code = str(item.get("公司代號") or "").strip().zfill(4)
        if not company_code.isdigit():
            continue
        event_date = _roc_date_to_iso(item.get("發言日期"))
        event_time = _raw_time_to_hms(item.get("發言時間"))
        title = str(item.get("主旨 ") or item.get("主旨") or "").strip()
        detail = str(item.get("說明") or "").strip()
        event_type = _classify_event_type(title, detail)
        rows.append(
            {
                "source": "TWSE_MAJOR_INFO",
                "source_type": "official_major_info",
                "company_code": company_code,
                "company_name": str(item.get("公司名稱") or "").strip(),
                "market": "TWSE",
                "event_date": event_date,
                "event_time": event_time,
                "event_at": _build_event_at(event_date, event_time),
                "title": title,
                "detail": detail,
                "event_type": event_type,
                "severity_score": _severity_score(event_type, title),
                "url": "",
                "matched_by": "company_assignment",
            }
        )
    return pd.DataFrame(rows)


def _fetch_tpex_major_info_df():
    try:
        payload = json.loads(request_text(TPEX_MARKET_IMPORTANT_URL, encoding="utf-8", errors="replace"))
    except Exception:
        return pd.DataFrame()
    tables = payload.get("tables") or []
    if not tables:
        return pd.DataFrame()

    rows = []
    for item in (tables[0].get("data") or []):
        if len(item) < 5:
            continue
        url = str(item[4] or "").strip()
        company_code = _extract_company_code_from_url(url)
        if not company_code:
            continue
        title = str(item[1] or "").strip()
        event_type = _classify_event_type(title)
        event_date = _roc_slash_date_to_iso(item[2])
        event_time = _raw_time_to_hms(item[3])
        rows.append(
            {
                "source": "TPEX_MAJOR_INFO",
                "source_type": "official_major_info",
                "company_code": company_code,
                "company_name": str(item[0] or "").strip(),
                "market": "TPEx",
                "event_date": event_date,
                "event_time": event_time,
                "event_at": _build_event_at(event_date, event_time),
                "title": title,
                "detail": "",
                "event_type": event_type,
                "severity_score": _severity_score(event_type, title),
                "url": url,
                "matched_by": "company_assignment",
            }
        )
    return pd.DataFrame(rows)


def _load_topic_assignment_df():
    ensure_market_map_db()
    with _get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT
                a.code AS company_code,
                a.topic_name,
                t.group_name,
                c.name_zh AS company_name,
                c.market
            FROM map_topic_company_assignments a
            JOIN map_topics t ON a.topic_name = t.topic_name
            JOIN map_companies c ON a.code = c.code
            ORDER BY a.code, a.topic_name
            """,
            conn,
        )


def _build_topic_event_frames(anchor_date=None):
    snapshot_date = _to_date(anchor_date or datetime.now().date()).strftime("%Y-%m-%d")
    assignment_df = _load_topic_assignment_df()
    if assignment_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    official_frames = [_fetch_twse_major_info_df(), _fetch_tpex_major_info_df()]
    official_df = pd.concat([df for df in official_frames if not df.empty], ignore_index=True) if any(not df.empty for df in official_frames) else pd.DataFrame()
    if official_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    merged_df = official_df.merge(
        assignment_df.drop(columns=["company_name"]),
        on=["company_code", "market"],
        how="left",
    )
    merged_df = merged_df[merged_df["topic_name"].notna()].copy()
    if merged_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    merged_df["snapshot_date"] = snapshot_date
    merged_df["updated_at"] = datetime.now().isoformat(timespec="seconds")
    merged_df["event_key"] = merged_df.apply(
        lambda row: _event_key(
            row.get("source"),
            row.get("company_code"),
            row.get("event_date"),
            row.get("event_time"),
            row.get("title"),
        ),
        axis=1,
    )
    merged_df = merged_df.sort_values(
        ["topic_name", "severity_score", "event_at", "company_code"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)

    summary_rows = []
    for topic_name, topic_df in merged_df.groupby("topic_name"):
        summary_rows.append(
            {
                "snapshot_date": snapshot_date,
                "topic_name": topic_name,
                "event_count": int(len(topic_df)),
                "company_count": int(topic_df["company_code"].nunique()),
                "risk_event_count": int((topic_df["event_type"] == "risk").sum()),
                "board_event_count": int((topic_df["event_type"] == "board").sum()),
                "capital_event_count": int((topic_df["event_type"] == "capital").sum()),
                "conference_event_count": int((topic_df["event_type"] == "conference").sum()),
                "operational_event_count": int((topic_df["event_type"] == "operational").sum()),
                "latest_event_at": topic_df["event_at"].dropna().max() if topic_df["event_at"].notna().any() else None,
                "top_event_titles": " / ".join(topic_df["title"].astype(str).head(3).tolist()),
                "updated_at": topic_df["updated_at"].iloc[0],
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["event_count", "operational_event_count", "risk_event_count", "latest_event_at"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    item_df = merged_df[
        [
            "snapshot_date",
            "topic_name",
            "event_key",
            "source",
            "source_type",
            "company_code",
            "company_name",
            "market",
            "event_date",
            "event_time",
            "event_at",
            "title",
            "detail",
            "event_type",
            "severity_score",
            "url",
            "matched_by",
            "updated_at",
        ]
    ].copy()
    return summary_df, item_df


def _persist_topic_event_frames(snapshot_date, summary_df, item_df):
    updated_at = datetime.now().isoformat(timespec="seconds")
    with _get_connection() as conn:
        conn.execute("DELETE FROM map_topic_event_snapshots WHERE snapshot_date = ?", (snapshot_date,))
        conn.execute("DELETE FROM map_topic_event_items WHERE snapshot_date = ?", (snapshot_date,))
        if not summary_df.empty:
            conn.executemany(
                """
                INSERT INTO map_topic_event_snapshots (
                    snapshot_date, topic_name, event_count, company_count, risk_event_count,
                    board_event_count, capital_event_count, conference_event_count,
                    operational_event_count, latest_event_at, top_event_titles, updated_at
                ) VALUES (
                    :snapshot_date, :topic_name, :event_count, :company_count, :risk_event_count,
                    :board_event_count, :capital_event_count, :conference_event_count,
                    :operational_event_count, :latest_event_at, :top_event_titles, :updated_at
                )
                """,
                summary_df.to_dict(orient="records"),
            )
        if not item_df.empty:
            conn.executemany(
                """
                INSERT INTO map_topic_event_items (
                    snapshot_date, topic_name, event_key, source, source_type, company_code,
                    company_name, market, event_date, event_time, event_at, title, detail,
                    event_type, severity_score, url, matched_by, updated_at
                ) VALUES (
                    :snapshot_date, :topic_name, :event_key, :source, :source_type, :company_code,
                    :company_name, :market, :event_date, :event_time, :event_at, :title, :detail,
                    :event_type, :severity_score, :url, :matched_by, :updated_at
                )
                """,
                item_df.to_dict(orient="records"),
            )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('latest_topic_event_snapshot_date', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (snapshot_date,),
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('latest_topic_event_updated_at', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (updated_at,),
        )
        conn.commit()


def _load_cached_topic_event_frames(snapshot_date):
    ensure_market_map_db()
    with _get_connection() as conn:
        summary_df = pd.read_sql_query(
            """
            SELECT *
            FROM map_topic_event_snapshots
            WHERE snapshot_date = ?
            ORDER BY event_count DESC, operational_event_count DESC, risk_event_count DESC, latest_event_at DESC
            """,
            conn,
            params=(snapshot_date,),
        )
        item_df = pd.read_sql_query(
            """
            SELECT *
            FROM map_topic_event_items
            WHERE snapshot_date = ?
            ORDER BY topic_name, severity_score DESC, event_at DESC
            """,
            conn,
            params=(snapshot_date,),
        )
    return summary_df, item_df


def ensure_market_map_topic_events(anchor_date=None, force_refresh=False, max_cache_age_minutes=EVENT_CACHE_MINUTES):
    snapshot_date = _to_date(anchor_date or datetime.now().date()).strftime("%Y-%m-%d")
    ensure_market_map_db()

    if not force_refresh:
        with _get_connection() as conn:
            meta_rows = conn.execute(
                """
                SELECT key, value
                FROM metadata
                WHERE key IN ('latest_topic_event_snapshot_date', 'latest_topic_event_updated_at')
                """
            ).fetchall()
        metadata = {row["key"]: row["value"] for row in meta_rows}
        latest_snapshot_date = metadata.get("latest_topic_event_snapshot_date")
        latest_updated_at = metadata.get("latest_topic_event_updated_at")
        if latest_snapshot_date == snapshot_date and latest_updated_at:
            try:
                updated_at = datetime.fromisoformat(latest_updated_at)
            except ValueError:
                updated_at = None
            if updated_at and updated_at >= datetime.now() - timedelta(minutes=max_cache_age_minutes):
                summary_df, item_df = _load_cached_topic_event_frames(snapshot_date)
                return {
                    "snapshot_date": snapshot_date,
                    "summary_df": summary_df,
                    "item_df": item_df,
                    "source": "cache",
                }

    try:
        summary_df, item_df = _build_topic_event_frames(anchor_date=snapshot_date)
        _persist_topic_event_frames(snapshot_date, summary_df, item_df)
        return {
            "snapshot_date": snapshot_date,
            "summary_df": summary_df,
            "item_df": item_df,
            "source": "fresh",
        }
    except Exception:
        summary_df, item_df = _load_cached_topic_event_frames(snapshot_date)
        return {
            "snapshot_date": snapshot_date,
            "summary_df": summary_df,
            "item_df": item_df,
            "source": "cache-fallback" if (not summary_df.empty or not item_df.empty) else "empty",
        }
