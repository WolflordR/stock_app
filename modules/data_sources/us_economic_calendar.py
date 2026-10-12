"""Live U.S. economic release schedule from the New York Fed calendar."""
from __future__ import annotations

import json
import re
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from modules.core.project_paths import cache_path


NEW_YORK_FED_CALENDAR = "https://www.newyorkfed.org/research/calendars"
FED_FOMC_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CACHE_FILE = cache_path("us_economic_calendar.json")
EASTERN = ZoneInfo("America/New_York")
TAIPEI = ZoneInfo("Asia/Taipei")
CACHE_TTL = timedelta(hours=6)
_cache_lock = Lock()

_HIGH = (
    "consumer price index", "employment situation", "producer price index",
    "gross domestic product", "personal income and the pce deflator",
    "personal income and outlays", "advance retail sales", "retail sales",
    "ism manufacturing", "ism non-manufacturing", "job openings and labor turnover",
)
_MEDIUM = (
    "initial claims", "durable goods", "industrial production", "consumer survey",
    "consumer sentiment", "new residential", "existing home sales",
    "trade balance", "employment cost index", "business inventories",
)


def _category_and_importance(name: str) -> tuple[str, str, str]:
    lower = name.lower()
    importance = "high" if any(word in lower for word in _HIGH) else (
        "medium" if any(word in lower for word in _MEDIUM) else "low"
    )
    if any(word in lower for word in ("consumer price", "producer price", "pce deflator", "inflation")):
        return "通膨", importance, "影響通膨與利率預期"
    if any(word in lower for word in ("employment", "claims", "job openings", "earnings")):
        return "就業", importance, "觀察美國勞動市場"
    if any(word in lower for word in ("gross domestic product", "retail sales", "income", "ism ")):
        return "景氣與消費", importance, "觀察美國經濟活動"
    if any(word in lower for word in ("housing", "home sales", "construction", "residential")):
        return "房市", importance, "觀察美國房地產活動"
    return "其他指標", importance, "查看公布機構的原始資料"


def _display_name(name: str) -> str:
    translations = (
        ("consumer price index", "消費者物價指數 CPI"),
        ("producer price index", "生產者物價指數 PPI"),
        ("employment situation", "非農就業報告"),
        ("gross domestic product", "國內生產毛額 GDP"),
        ("personal income and the pce deflator", "個人所得與 PCE 物價指數"),
        ("personal income and outlays", "個人所得與支出／PCE"),
        ("initial claims", "初領失業救濟金"),
        ("advance retail sales", "零售銷售"),
        ("job openings and labor turnover", "JOLTS 職缺與勞動流動"),
    )
    lower = name.lower()
    return next((label for phrase, label in translations if phrase in lower), name)


def parse_new_york_fed_month(html: str, year: int, month: int, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="research-table-1col")
    if table is None:
        raise ValueError("New York Fed calendar table not found")
    rows = []
    for tr in table.find_all("tr"):
        for cell in tr.find_all("td")[1:6]:
            day_match = re.match(r"^(\d{1,2})\b", cell.get_text(" ", strip=True))
            if not day_match:
                continue
            try:
                us_date = date(year, month, int(day_match.group(1)))
            except ValueError:
                continue
            for link in cell.select("span.ts-accordion-content a"):
                name = link.get_text(" ", strip=True)
                if not name:
                    continue
                following = []
                for sibling in link.next_siblings:
                    if getattr(sibling, "name", None) == "a":
                        break
                    following.append(str(sibling))
                time_match = re.search(r"\((\d{1,2}):(\d{2})\)", " ".join(following))
                if not time_match:
                    continue
                hour, minute = map(int, time_match.groups())
                local = datetime.combine(us_date, time(hour, minute), EASTERN).astimezone(TAIPEI)
                category, importance, impact = _category_and_importance(name)
                rows.append({
                    "date": local.date().isoformat(), "time": local.strftime("%H:%M"),
                    "country": "US", "event": _display_name(name), "original_event": name,
                    "category": category, "importance": importance,
                    "previous": None, "forecast": None, "actual": None, "unit": None,
                    "market_impact": impact, "source_name": "紐約聯準銀行",
                    "source_url": urljoin(page_url, link.get("href") or page_url),
                    "calendar_url": page_url,
                })
    if not rows:
        raise ValueError("New York Fed calendar contained no scheduled releases")
    return rows


def parse_fomc_calendar(html: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    heading = next((h for h in soup.find_all("h4")
                    if f"{year} FOMC Meetings" in h.get_text(" ", strip=True)), None)
    if heading is None:
        raise ValueError(f"FOMC {year} schedule not found")
    panel = heading.find_parent("div", class_="panel")
    rows = []
    for meeting in panel.select(".fomc-meeting") if panel else []:
        month_node = meeting.select_one(".fomc-meeting__month")
        date_node = meeting.select_one(".fomc-meeting__date")
        if month_node is None or date_node is None:
            continue
        try:
            month = datetime.strptime(month_node.get_text(" ", strip=True), "%B").month
            day = int(re.findall(r"\d{1,2}", date_node.get_text(" ", strip=True))[-1])
            local = datetime.combine(date(year, month, day), time(14, 0), EASTERN).astimezone(TAIPEI)
        except (ValueError, IndexError):
            continue
        rows.append({
            "date": local.date().isoformat(), "time": local.strftime("%H:%M"),
            "country": "US", "event": "FOMC 利率決議", "original_event": "FOMC policy statement",
            "category": "聯準會", "importance": "high",
            "previous": None, "forecast": None, "actual": None, "unit": None,
            "market_impact": "聯準會利率決策與政策聲明",
            "source_name": "美國聯邦準備理事會", "source_url": FED_FOMC_CALENDAR,
            "calendar_url": FED_FOMC_CALENDAR,
        })
    if not rows:
        raise ValueError(f"FOMC {year} schedule contained no meetings")
    return rows


def _month_keys(start: date, end: date) -> list[tuple[int, int]]:
    keys = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def _read_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
        json.dump(data, handle, ensure_ascii=False)
        temp = Path(handle.name)
    temp.replace(path)


def load_official_us_calendar(start: date, end: date, *, path: Path = CACHE_FILE) -> dict:
    """Load monthly schedules, retaining the last successful copy on source errors."""
    now = datetime.now(timezone.utc)
    rows = []
    errors = []
    used_stale = False
    latest_sync = None
    # A 14:00 ET release may appear on the next calendar day in Taiwan.
    for year, month in _month_keys(start - timedelta(days=1), end):
        key = f"{year:04d}-{month:02d}"
        page_url = f"{NEW_YORK_FED_CALENDAR}/i-{date(year, month, 1).strftime('%b').lower()}{year % 100:02d}.html"
        with _cache_lock:
            cache = _read_cache(path)
            cached = cache.get(key, {})
            fetched_at = cached.get("fetched_at")
            is_fresh = False
            if fetched_at:
                try:
                    is_fresh = now - datetime.fromisoformat(fetched_at) < CACHE_TTL
                except ValueError:
                    pass
            if not is_fresh:
                try:
                    response = requests.get(page_url, headers={"User-Agent": "TradeLab/1.0 (economic calendar)"}, timeout=12)
                    response.raise_for_status()
                    parsed = parse_new_york_fed_month(response.text, year, month, page_url)
                    cached = {"fetched_at": now.isoformat(), "rows": parsed}
                    cache[key] = cached
                    _write_cache(path, cache)
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{key}: {exc}")
                    used_stale = used_stale or bool(cached.get("rows"))
        rows.extend(cached.get("rows", []))
        if cached.get("fetched_at"):
            latest_sync = max(latest_sync or cached["fetched_at"], cached["fetched_at"])
    for year in range((start - timedelta(days=1)).year, end.year + 1):
        key = f"fomc-{year}"
        with _cache_lock:
            cache = _read_cache(path)
            cached = cache.get(key, {})
            fetched_at = cached.get("fetched_at")
            is_fresh = False
            if fetched_at:
                try:
                    is_fresh = now - datetime.fromisoformat(fetched_at) < CACHE_TTL
                except ValueError:
                    pass
            if not is_fresh:
                try:
                    response = requests.get(FED_FOMC_CALENDAR, headers={"User-Agent": "TradeLab/1.0 (economic calendar)"}, timeout=12)
                    response.raise_for_status()
                    parsed = parse_fomc_calendar(response.text, year)
                    cached = {"fetched_at": now.isoformat(), "rows": parsed}
                    cache[key] = cached
                    _write_cache(path, cache)
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{key}: {exc}")
                    used_stale = used_stale or bool(cached.get("rows"))
        rows.extend(cached.get("rows", []))
        if cached.get("fetched_at"):
            latest_sync = max(latest_sync or cached["fetched_at"], cached["fetched_at"])
    unique = {(row["date"], row["time"], row["original_event"]): row for row in rows}
    return {"rows": sorted(unique.values(), key=lambda row: (row["date"], row["time"], row["event"])),
            "source": "official_cache" if used_stale else "official" if rows else "unavailable",
            "last_updated_at": latest_sync, "errors": errors,
            "source_label": "紐約聯準銀行與聯準會官方行事曆（台灣時間）"}
