"""MOPS major-announcement events, kept separate from price/rotation data.

The daily official feeds only expose recent announcements. A financial-report
board meeting is an estimated report date, never a confirmed publication date.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from modules.core.project_paths import PROJECT_ROOT, db_path

LOG = logging.getLogger(__name__)
DB_PATH = db_path("company_events.db")
SOURCES = {
    "TWSE": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
    "TPEx": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O",
}
IR_CALENDAR_URL = "https://irengage.taiwanindex.com.tw/conferenceList"
IR_CALENDAR_SOURCE = "Taiwan Index IR calendar"
DATE_PATTERN = re.compile(r"(?<!\d)(\d{2,4})[年/.-](\d{1,2})[月/.-](\d{1,2})(?:日)?")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript((PROJECT_ROOT / "migrations" / "20261009_company_events.sql").read_text())


def _official_date(value: str) -> str | None:
    match = DATE_PATTERN.search(value or "")
    if match:
        year, month, day = map(int, match.groups())
    else:
        digits = re.sub(r"\D", "", value or "")
        if len(digits) not in {7, 8}:
            return None
        year, month, day = int(digits[:-4]), int(digits[-4:-2]), int(digits[-2:])
    if year < 1911:
        year += 1911
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _field(description: str, label: str) -> str:
    match = re.search(rf"(?:^|\n)\s*\d*\.?\s*{re.escape(label)}\s*[：:]\s*([^\r\n]+)", description)
    return match.group(1).strip() if match else ""


def normalize_announcement(row: dict[str, Any], market: str, source_url: str, *, today: date | None = None) -> dict[str, Any] | None:
    today = today or date.today()
    stock_id = str(row.get("公司代號") or row.get("SecuritiesCompanyCode") or "").strip()
    name = str(row.get("公司名稱") or row.get("CompanyName") or "").strip()
    title = str(row.get("主旨 ") or row.get("主旨") or "").strip().replace("\r", " ").replace("\n", " ")
    description = str(row.get("說明") or "")
    if not (stock_id.isdigit() and name and title):
        return None
    if title.startswith("代子公司"):
        return None
    quarter_match = re.search(r"(\d{2,4})年(?:度)?(?:第)?([1-4一二三四])季", title + description)
    fiscal_year = fiscal_quarter = None
    if quarter_match:
        fiscal_year = int(quarter_match[1])
        fiscal_year += 1911 if fiscal_year < 1911 else 0
        fiscal_quarter = {"一": 1, "二": 2, "三": 3, "四": 4}.get(quarter_match[2]) or int(quarter_match[2])
    if "法說" in title or "法人說明會" in title:
        event_type = "investor_conference"
        raw_date = _field(description, "召開法人說明會之日期")
        event_date = _official_date(raw_date)
        if not event_date:
            return None
        raw_time = _field(description, "召開法人說明會之時間")
        time_match = re.search(r"(\d{1,2})\s*(?:時|:)\s*(\d{1,2})", raw_time)
        start_time = f"{int(time_match[1]):02d}:{int(time_match[2]):02d}" if time_match else None
        location = _field(description, "召開法人說明會之地點") or None
        organizer_match = re.search(r"(?:參加|受邀參加)([^，。\s]+?)(?:舉辦|主辦|舉行)", title)
        organizer = organizer_match.group(1) if organizer_match else None
        status = "confirmed"
    elif "財務報告" in title and "董事會預計召開日期" in title:
        event_type = "earnings"
        raw_date = _field(description, "董事會預計召開日期")
        event_date = _official_date(raw_date) or _official_date(title)
        if not event_date:
            return None
        start_time = location = organizer = None
        status = "estimated"
    elif "財務報告" in title and ("業經董事會決議通過" in title or "經董事會決議通過" in title):
        # The speech date is when the board-resolution announcement was made.
        # It does not prove the full report was filed at that time.
        event_type = "earnings"
        event_date = _official_date(str(row.get("發言日期") or ""))
        if not event_date or fiscal_year is None or fiscal_quarter is None:
            return None
        start_time = location = organizer = None
        status = "completed"
    else:
        return None
    if event_date < (today - timedelta(days=30)).isoformat() or event_date > (today + timedelta(days=180)).isoformat():
        return None
    online_match = re.search(r"https?://[^\s，。)]+", location or "")
    online_url = online_match.group(0) if online_match else None
    key = f"{market}|{stock_id}|{event_type}|{event_date}|{title}"
    return {
        "id": hashlib.sha256(key.encode()).hexdigest()[:24], "stock_id": stock_id,
        "company_name": name, "event_type": event_type, "title": title,
        "event_date": event_date, "start_time": start_time, "end_time": None,
        "fiscal_year": fiscal_year, "fiscal_quarter": fiscal_quarter,
        "status": status, "location": location, "online_url": online_url,
        "organizer": organizer, "language": None, "description": description,
        "source": f"{market} MOPS major announcements", "source_url": source_url,
        "external_url": online_url, "presentation_url": None, "replay_url": None, "ir_url": None,
    }


def parse_ir_calendar(html: str, source_url: str, *, today: date | None = None) -> list[dict[str, Any]]:
    """Read the public monthly listed/OTC conference table, without inventing dates for ranges."""
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    headers = {cell.get_text(" ", strip=True) for cell in soup.select("table th")}
    if not {"日期", "時間", "公司"}.issubset(headers):
        raise ValueError("IR calendar table is unavailable")
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in soup.select("tr"):
        columns = {cell.get("data-header"): cell.get_text(" ", strip=True) for cell in row.select("td[data-header]")}
        if not columns:
            continue
        raw_date = columns.get("日期", "")
        event_date = _official_date(raw_date)
        company = columns.get("公司", "")
        match = re.match(r"^(\d{4,6})\s+(.+)$", company)
        if not (event_date and match):
            continue
        if event_date < (today - timedelta(days=30)).isoformat() or event_date > (today + timedelta(days=180)).isoformat():
            continue
        raw_time = columns.get("時間", "")
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", raw_time)
        start_time = f"{int(time_match[1]):02d}:{time_match[2]}" if time_match else None
        stock_id, name = match.groups()
        key = f"IRCalendar|{stock_id}|{event_date}|{start_time or ''}"
        event_id = hashlib.sha256(key.encode()).hexdigest()[:24]
        if event_id in seen:
            continue
        seen.add(event_id)
        description = columns.get("訊息", "")
        location = columns.get("地點", "") or None
        url_match = re.search(r"https?://[^\s，。)]+", f"{description} {location or ''}")
        online_url = url_match.group(0) if url_match else None
        events.append({
            "id": event_id, "stock_id": stock_id, "company_name": name,
            "event_type": "investor_conference", "title": description[:160] or "法人說明會",
            "event_date": event_date, "start_time": start_time, "end_time": None,
            "fiscal_year": None, "fiscal_quarter": None, "status": "confirmed",
            "location": location, "online_url": online_url, "organizer": None,
            "language": None, "description": description or raw_date,
            "source": IR_CALENDAR_SOURCE, "source_url": source_url,
            "external_url": online_url, "presentation_url": None, "replay_url": None, "ir_url": None,
        })
    return events


def upsert_events(events: list[dict[str, Any]], *, path: Path = DB_PATH, now: str | None = None) -> int:
    migrate(path)
    now = now or datetime.now().isoformat(timespec="seconds")
    fields = ["id", "stock_id", "company_name", "event_type", "title", "event_date", "start_time", "end_time", "fiscal_year", "fiscal_quarter", "status", "location", "online_url", "organizer", "language", "description", "source", "source_url", "external_url", "presentation_url", "replay_url", "ir_url"]
    stored = 0
    with connect(path) as conn:
        for event in events:
            if event.get("event_type") == "investor_conference":
                matches = conn.execute(
                    "SELECT id,source FROM company_events WHERE stock_id=? AND event_type='investor_conference' AND event_date=? AND COALESCE(start_time,'')=? AND id<>?",
                    (event["stock_id"], event["event_date"], event.get("start_time") or "", event["id"]),
                ).fetchall()
                if event.get("source") == IR_CALENDAR_SOURCE and any(row["source"] != IR_CALENDAR_SOURCE for row in matches):
                    continue
                for row in matches:
                    if event.get("source") != IR_CALENDAR_SOURCE or row["source"] == IR_CALENDAR_SOURCE:
                        conn.execute("DELETE FROM company_events WHERE id=?", (row["id"],))
            if event.get("event_type") == "earnings" and event.get("fiscal_year") and event.get("fiscal_quarter"):
                period = (event["stock_id"], event["fiscal_year"], event["fiscal_quarter"])
                if event.get("status") == "estimated" and conn.execute(
                    "SELECT 1 FROM company_events WHERE stock_id=? AND fiscal_year=? AND fiscal_quarter=? AND status='completed' LIMIT 1",
                    period,
                ).fetchone():
                    continue
                # An updated board date supersedes its earlier estimate; once
                # a board resolution is announced, the estimate is no longer
                # presented as a separate upcoming publication date.
                conn.execute(
                    "DELETE FROM company_events WHERE stock_id=? AND event_type='earnings' AND fiscal_year=? AND fiscal_quarter=? AND status='estimated' AND id<>?",
                    (*period, event["id"]),
                )
            values = [event.get(field) for field in fields]
            conn.execute(f"INSERT INTO company_events ({','.join(fields)},created_at,updated_at,last_verified_at) VALUES ({','.join('?' for _ in fields)},?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,last_verified_at=excluded.last_verified_at,status=excluded.status,description=excluded.description,location=excluded.location,online_url=excluded.online_url", (*values, now, now, now))
            stored += 1
    return stored


def refresh_events(*, path: Path = DB_PATH, session: requests.Session | None = None, today: date | None = None) -> dict[str, Any]:
    migrate(path)
    client = session or requests
    now = datetime.now().isoformat(timespec="seconds")
    summary: dict[str, Any] = {"stored": 0, "sources": {}, "errors": []}
    for market, url in SOURCES.items():
        try:
            response = client.get(url, timeout=20)
            response.raise_for_status()
            raw = response.json()
            if not isinstance(raw, list):
                raise ValueError("official feed did not return a list")
            events = [event for row in raw if (event := normalize_announcement(row, market, url, today=today))]
            summary["stored"] += upsert_events(events, path=path, now=now)
            summary["sources"][market] = len(events)
            with connect(path) as conn:
                conn.execute("INSERT INTO event_source_state VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,last_error=NULL,rows_seen=excluded.rows_seen", (market, now, now, None, len(raw)))
        except Exception as exc:
            LOG.exception("Official event refresh failed for %s", market)
            summary["errors"].append(f"{market}: {exc}")
            with connect(path) as conn:
                conn.execute("INSERT INTO event_source_state VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_error=excluded.last_error", (market, now, None, str(exc), 0))
    anchor = today or date.today()
    calendar_count = 0
    try:
        for month_offset in range(4):
            month_number = (anchor.year * 12 + anchor.month - 1) + month_offset
            year, month = divmod(month_number, 12)
            month += 1
            url = f"{IR_CALENDAR_URL}?Year={year}&Month={month}"
            response = client.get(url, timeout=20)
            response.raise_for_status()
            selector = BeautifulSoup(response.text, "html.parser")
            selected_year = selector.select_one("#YearSelect option[selected]")
            selected_month = selector.select_one("#Month option[selected]")
            if selected_year is None or selected_year.get("value") != str(year) or selected_month is None or selected_month.get("value") != str(month):
                # The site has not opened that future year/month yet.
                break
            events = parse_ir_calendar(response.text, url, today=anchor)
            month_start = date(year, month, 1).isoformat()
            next_year, next_month = divmod(month_number + 1, 12)
            month_end = date(next_year, next_month + 1, 1).isoformat()
            current_ids = {event["id"] for event in events}
            # Remove only obsolete rows from this successfully fetched month.
            with connect(path) as conn:
                stale = conn.execute(
                    "SELECT id FROM company_events WHERE source=? AND event_date>=? AND event_date<?",
                    (IR_CALENDAR_SOURCE, month_start, month_end),
                ).fetchall()
                for row in stale:
                    if row["id"] not in current_ids:
                        conn.execute("DELETE FROM company_events WHERE id=?", (row["id"],))
            summary["stored"] += upsert_events(events, path=path, now=now)
            calendar_count += len(events)
        summary["sources"]["IRCalendar"] = calendar_count
        with connect(path) as conn:
            conn.execute("INSERT INTO event_source_state VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,last_error=NULL,rows_seen=excluded.rows_seen", ("IRCalendar", now, now, None, calendar_count))
    except Exception as exc:
        LOG.exception("Official IR calendar refresh failed")
        summary["errors"].append(f"IRCalendar: {exc}")
        with connect(path) as conn:
            conn.execute("INSERT INTO event_source_state VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_error=excluded.last_error", ("IRCalendar", now, None, str(exc), calendar_count))
    return summary


def list_events(*, start_date: str, end_date: str, event_type: str | None = None, stock_id: str | None = None, watchlist_only: bool = False, query: str | None = None, status: str | None = None, limit: int = 500, offset: int = 0, path: Path = DB_PATH) -> dict[str, Any]:
    date.fromisoformat(start_date)
    date.fromisoformat(end_date)
    if event_type and event_type not in {"earnings", "investor_conference"}:
        raise ValueError("unknown event_type")
    if status and status not in {"estimated", "confirmed", "completed", "cancelled"}:
        raise ValueError("unknown status")
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError("invalid pagination")
    migrate(path)
    with connect(path) as conn:
        where = ["event_date BETWEEN ? AND ?"]
        params: list[Any] = [start_date, end_date]
        if event_type:
            where.append("event_type=?")
            params.append(event_type)
        if stock_id:
            where.append("stock_id=?")
            params.append(stock_id)
        if query:
            escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(stock_id LIKE ? ESCAPE '\\' OR company_name LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%", f"%{escaped}%"])
        if status:
            where.append("status=?")
            params.append(status)
        if watchlist_only:
            from modules.watchlist_store import get_watchlists
            codes = [item["stock_code"] for item in get_watchlists()["items"]]
            if not codes:
                states = [dict(row) for row in conn.execute("SELECT * FROM event_source_state ORDER BY source")]
                return {"rows": [], "count": 0, "totals": {}, "source_state": states}
            where.append(f"stock_id IN ({','.join('?' for _ in codes)})")
            params.extend(codes)
        predicate = " AND ".join(where)
        count = conn.execute(f"SELECT COUNT(*) FROM company_events WHERE {predicate}", params).fetchone()[0]
        totals = {row[0]: row[1] for row in conn.execute(f"SELECT event_type,COUNT(*) FROM company_events WHERE {predicate} GROUP BY event_type", params)}
        rows = [dict(row) for row in conn.execute(f"SELECT * FROM company_events WHERE {predicate} ORDER BY event_date,start_time,stock_id LIMIT ? OFFSET ?", [*params, limit, offset])]
        states = [dict(row) for row in conn.execute("SELECT * FROM event_source_state ORDER BY source")]
    return {"rows": rows, "count": count, "totals": totals, "source_state": states}
