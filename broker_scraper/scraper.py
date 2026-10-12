"""下載證交所當前交易日的上市股票券商買賣 CSV。"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import ddddocr
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://bsr.twse.com.tw/bshtm/"
MENU_URL = urljoin(BASE_URL, "bsMenu.aspx")
REPORT_URL = urljoin(BASE_URL, "bsContent.aspx?v=t")
CSV_URL = urljoin(BASE_URL, "bsContent.aspx")
WELCOME_URL = urljoin(BASE_URL, "bsWelcome.aspx")
ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
RAW_DATA_DIR = Path(
    os.environ.get("TRADE_RAW_DATA_DIR", Path(__file__).resolve().parent.parent / "data" / "raw")
)
SAVE_DIR = RAW_DATA_DIR / "broker" / "twse"
MAX_ATTEMPTS = 5
REQUEST_DELAY = 3
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


class DateChangedError(RuntimeError):
    """網站的交易日期在這次批次執行期間改變。"""


def extract_trade_date(html: bytes, label: str) -> str:
    page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = re.search(rf"{re.escape(label)}\s*[:：]?\s*(\d{{4}}/\d{{1,2}}/\d{{1,2}})", page_text)
    if not match:
        raise ValueError(f"頁面找不到「{label}」")
    return datetime.strptime(match.group(1), "%Y/%m/%d").strftime("%Y-%m-%d")


def is_broker_csv(content: bytes, stock_code: str) -> bool:
    """只接受證交所回傳且股票代號相符的券商 CSV。"""
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            lines = content.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue
        if len(lines) < 3:
            return False
        return (
            lines[0].strip() == "券商買賣股票成交價量資訊"
            and re.fullmatch(rf'股票代碼,="{re.escape(stock_code)}"', lines[1].strip()) is not None
            and all(column in lines[2] for column in ("券商", "價格", "買進股數", "賣出股數"))
        )
    return False


def get_report_date(session: requests.Session) -> str:
    response = session.get(WELCOME_URL, timeout=20)
    response.raise_for_status()
    return extract_trade_date(response.content, "資料日期")


def get_listed_stocks(session: requests.Session) -> list[str]:
    response = session.get(ISIN_URL, timeout=30)
    response.raise_for_status()
    response.encoding = "big5"
    soup = BeautifulSoup(response.text, "html.parser")
    codes: list[str] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 6:
            continue
        match = re.match(r"^(\d{4})\s+", cells[0].get_text(" ", strip=True))
        if not match:
            continue
        # ESV 是股票；CEOG 是 ETF，EDSD 是存託憑證。
        if not cells[5].get_text(strip=True).startswith("ESV"):
            continue
        codes.append(match.group(1))
    codes = list(dict.fromkeys(codes))
    if not codes:
        raise ValueError("證交所股票清單為空，停止下載")
    return codes


def download_stock(stock_code: str, trade_date: str, ocr: ddddocr.DdddOcr) -> tuple[str, bytes | None]:
    """回傳 downloaded、no_data 或 failed，以及驗證過的 CSV。"""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with requests.Session() as session:
                session.headers.update(HEADERS)
                menu = session.get(MENU_URL, timeout=20)
                menu.raise_for_status()
                soup = BeautifulSoup(menu.content, "html.parser")
                payload = {
                    tag["name"]: tag.get("value", "")
                    for tag in soup.select('input[type="hidden"][name]')
                }
                if not payload.get("__VIEWSTATE") or not payload.get("__EVENTVALIDATION"):
                    raise ValueError("查詢頁缺少必要的表單欄位")
                image = soup.find("img", src=lambda src: src and "CaptchaImage" in src)
                if image is None:
                    raise ValueError("查詢頁沒有驗證碼圖片")
                image_response = session.get(urljoin(MENU_URL, image["src"]), timeout=20)
                image_response.raise_for_status()
                captcha = ocr.classification(image_response.content).strip()
                if len(captcha) != 5:
                    raise ValueError(f"驗證碼長度錯誤：{len(captcha)}")
                payload.update({
                    "RadioButton_Normal": "RadioButton_Normal",
                    "TextBox_Stkno": stock_code,
                    "CaptchaControl1": captcha,
                    "btnOK": "查詢",
                })
                result = session.post(MENU_URL, data=payload, timeout=20)
                result.raise_for_status()
                result_soup = BeautifulSoup(result.content, "html.parser")
                if result_soup.find(id="HyperLink_DownloadCSV") is None:
                    result_text = result_soup.get_text(" ", strip=True)
                    if "查無資料" in result_text or "無成交資料" in result_text:
                        return "no_data", None
                    raise ValueError("查詢未取得下載連結，可能是驗證碼錯誤或過期")
                report = session.get(REPORT_URL, headers={"Referer": MENU_URL}, timeout=30)
                report.raise_for_status()
                actual_date = extract_trade_date(report.content, "交易日期")
                if actual_date != trade_date:
                    raise DateChangedError(f"報表日期 {actual_date} 與批次日期 {trade_date} 不同")
                csv_response = session.get(CSV_URL, headers={"Referer": MENU_URL}, timeout=30)
                csv_response.raise_for_status()
                if not is_broker_csv(csv_response.content, stock_code):
                    raise ValueError("下載內容不是這檔股票的券商 CSV")
                return "downloaded", csv_response.content
        except DateChangedError:
            raise
        except (requests.RequestException, ValueError) as exc:
            print(f"  ⚠️ 第 {attempt}/{MAX_ATTEMPTS} 次失敗：{exc}", flush=True)
            if attempt < MAX_ATTEMPTS:
                time.sleep(2)
    return "failed", None


def save_csv(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", action="append", help="只下載指定的四碼股票，可重複使用；預設全部上市股票")
    parser.add_argument("--dry-run", action="store_true", help="只列出官方日期與待下載數量")
    args = parser.parse_args(argv)

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    with (SAVE_DIR / ".download.lock").open("a+") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("已有另一個下載程序在執行，本次略過。", flush=True)
            return 0

        with requests.Session() as session:
            session.headers.update(HEADERS)
            trade_date = get_report_date(session)
            all_stocks = get_listed_stocks(session)
        if args.stock:
            requested = list(dict.fromkeys(args.stock))
            unknown = [code for code in requested if code not in all_stocks]
            if unknown:
                parser.error(f"不是上市股票四碼代號：{', '.join(unknown)}")
            stocks = requested
        else:
            stocks = all_stocks

        day_dir = SAVE_DIR / trade_date
        pending = []
        for code in stocks:
            path = day_dir / f"{code}_bsr.csv"
            if not path.exists() or not is_broker_csv(path.read_bytes(), code):
                pending.append(code)
        print(f"官方資料日期：{trade_date}；上市股票 {len(stocks)} 檔；待下載 {len(pending)} 檔。", flush=True)
        if args.dry_run or not pending:
            return 0

        ocr = ddddocr.DdddOcr(show_ad=False)
        counts = {"downloaded": 0, "no_data": 0, "failed": 0}
        for index, code in enumerate(pending, 1):
            print(f"[{index}/{len(pending)}] {code}", flush=True)
            try:
                status, content = download_stock(code, trade_date, ocr)
            except DateChangedError as exc:
                print(f"❌ {exc}；停止本次批次。", flush=True)
                return 1
            if status == "downloaded" and content is not None:
                path = day_dir / f"{code}_bsr.csv"
                save_csv(path, content)
                print(f"  ✅ 已儲存 {path} ({len(content)} bytes)", flush=True)
            elif status == "no_data":
                print("  ℹ️ 當日查無成交資料", flush=True)
            else:
                print("  ❌ 本次下載失敗", flush=True)
            counts[status] += 1
            if index < len(pending):
                time.sleep(REQUEST_DELAY)
        print(f"完成：新增 {counts['downloaded']}；無資料 {counts['no_data']}；失敗 {counts['failed']}。", flush=True)
        return 1 if counts["failed"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (requests.RequestException, ValueError, OSError) as exc:
        print(f"❌ 批次下載中止：{exc}", file=sys.stderr, flush=True)
        sys.exit(1)
