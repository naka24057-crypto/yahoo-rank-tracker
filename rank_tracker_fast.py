"""
Chromeなし高速版 - Yahoo!ショッピング検索順位取得
__NEXT_DATA__ JSONから直接順位を解析（Selenium不要）
"""
import time
import os
import pickle
import re
import json
import requests
import urllib.parse
from datetime import datetime

import gspread
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

STORE_ID      = "nakazi-shop"
PRODUCT_SHEET = "商品キーワードリスト"
AREAS = {
    "東京": "13",
    "兵庫": "28",
}
MAX_PAGES = 10

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")
TOKEN_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle")
SHEET_NAME       = "Yahoo!キーワードトラッカー"
RANK_SHEET_TITLE = "検索順位"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


def get_google_client():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return gspread.authorize(creds)


def load_keywords(gc):
    sh = gc.open(SHEET_NAME)
    ws = sh.worksheet(PRODUCT_SHEET)
    rows = ws.get_all_values()[1:]
    seen = set()
    keywords = []
    for row in rows:
        if len(row) < 6:
            continue
        item_no, product_name, kw1, kw2, kw3, track = row[0], row[1], row[2], row[3], row[4], row[5]
        if track.strip().upper() != "Y":
            continue
        for kw in [kw1, kw2, kw3]:
            kw = kw.strip()
            if kw and kw not in seen:
                seen.add(kw)
                keywords.append((item_no, product_name, kw))
    return keywords


def get_or_create_rank_sheet(gc):
    try:
        sh = gc.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(SHEET_NAME)

    try:
        ws = sh.worksheet(RANK_SHEET_TITLE)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=RANK_SHEET_TITLE, rows=10000, cols=10)
        ws.append_row(["日付", "商品番号", "商品名", "エリア", "キーワード", "自然順位", "PR順位"])
        ws.freeze(rows=1)

    return sh, ws


def fetch_page(session, url):
    """Yahoo!検索結果をHTMLで取得し、__NEXT_DATA__からアイテムリストと次ページURLを返す"""
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return [], None
        nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not nd_match:
            return [], None
        nd = json.loads(nd_match.group(1))
        sr = nd.get("props", {}).get("initialState", {}).get("bff", {}).get("searchResults", {})
        items_map = sr.get("items", {})
        # ページキーは '1', '2', ... と変わるので最初のキーを使う
        entries = next(iter(items_map.values()), [])

        items = []
        next_url = None
        for entry in entries:
            if entry.get("type") == "RESULT":
                items = entry.get("content", {}).get("items", [])
            elif entry.get("type") == "PAGER":
                nxt = entry.get("content", {}).get("next")
                if nxt:
                    next_url = nxt.get("url")

        return items, next_url
    except Exception as e:
        print(f"  fetch error: {e}")
        return [], None


def search_rank(session, keyword, area_code):
    organic_rank = 1
    pr_rank = 1
    found_organic = None
    found_pr = None

    encoded = urllib.parse.quote(keyword)
    current_url = (
        f"https://shopping.yahoo.co.jp/search/{encoded}/0/"
        f"?first=1&tab_ex=commerce&prom=1&sort=score&area={area_code}"
    )

    for _ in range(MAX_PAGES):
        items, next_url = fetch_page(session, current_url)
        if not items:
            break

        for item in items:
            store = item.get("storeId", "")
            item_url = item.get("url", "")
            is_pr = "shopping-item-reach.yahoo.co.jp" in item_url
            is_mine = (store == STORE_ID)

            if is_pr:
                if is_mine and found_pr is None:
                    found_pr = pr_rank
                pr_rank += 1
            else:
                if is_mine and found_organic is None:
                    found_organic = organic_rank
                organic_rank += 1

            if found_organic is not None and found_pr is not None:
                return found_organic, found_pr

        if not next_url:
            break
        current_url = next_url
        time.sleep(2)

    return found_organic, found_pr


def main():
    print(f"=== 順位チェック開始（Chromeなし高速版）: {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    print("Google認証中...")
    gc = get_google_client()
    sh, ws = get_or_create_rank_sheet(gc)
    print(f"スプレッドシート: {sh.url}")

    print("キーワード読み込み中...")
    KEYWORDS = load_keywords(gc)
    print(f"追跡キーワード: {len(KEYWORDS)}件")

    session = requests.Session()
    session.headers.update(HEADERS)

    today = datetime.now().strftime("%Y-%m-%d")
    all_rows = ws.get_all_values()[1:]
    done = {(r[3], r[4]) for r in all_rows if len(r) >= 5 and r[0] == today}

    try:
        for area_name, area_code in AREAS.items():
            print(f"\n--- {area_name} ---")
            for item_no, product_name, kw in KEYWORDS:
                if (area_name, kw) in done:
                    print(f"  スキップ（取得済み）: {kw}")
                    continue
                print(f"  検索中: [{item_no}] {kw}")
                organic, pr = search_rank(session, kw, area_code)

                org_str = f"{organic}" if organic else "圏外"
                pr_str  = f"{pr}"      if pr      else "圏外"
                print(f"    自然: {org_str} / PR: {pr_str} → 書き込み中")

                ws.append_row([today, item_no, product_name, area_name, kw, org_str, pr_str])
                time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n停止されました（次回は続きから再開されます）")

    print(f"\n完了！URL: {sh.url}")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
