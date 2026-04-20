"""
Yahoo!ショッピングAPIで自店の全商品を取得し、
商品名から3キーワードを抽出してGoogleスプレッドシートに書き込む。
新商品追加時も自動で差分更新される。
"""
import os
import pickle
import requests
from datetime import datetime

import gspread
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

APP_ID    = "dj00aiZpPWpqYk9CZmxDdDMxWCZzPWNvbnN1bWVyc2VjcmV0Jng9OTQ-"
SELLER_ID = "nakazi-shop"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")
TOKEN_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle")
SHEET_NAME       = "Yahoo!キーワードトラッカー"
PRODUCT_SHEET    = "商品キーワードリスト"


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


def fetch_all_products():
    """Yahoo!ショッピングAPIで全商品を取得"""
    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    products = []
    start = 1

    while True:
        params = {
            "appid": APP_ID,
            "seller_id": SELLER_ID,
            "results": 100,
            "start": start,
            "output": "json",
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        hits = data.get("hits", [])
        if not hits:
            break

        for item in hits:
            code = item.get("code", "")
            # "nakazi-shop_564" → "564"
            item_no = code.replace(f"{SELLER_ID}_", "") if code else ""
            products.append({
                "item_no": item_no,
                "name":    item.get("name", ""),
                "url":     item.get("url", ""),
            })

        total = data.get("totalResultsAvailable", 0)
        start += len(hits)
        if start > total:
            break

    return products


def extract_keywords(name, n=3):
    """商品名から累積キーワードを抽出（1語, 1+2語, 1+2+3語）"""
    words = name.split()
    return [" ".join(words[:i+1]) if i < len(words) else "" for i in range(n)]


def update_product_sheet(gc, products):
    """スプレッドシートの商品キーワードリストを差分更新"""
    try:
        sh = gc.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(SHEET_NAME)

    try:
        ws = sh.worksheet(PRODUCT_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=PRODUCT_SHEET, rows=1000, cols=10)
        ws.append_row(["商品番号", "商品名", "キーワード1", "キーワード2", "キーワード3", "追跡", "最終確認"])
        ws.freeze(rows=1)

    # 既存の商品番号一覧を取得（A列）
    existing = ws.col_values(1)[1:]  # ヘッダー除く

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_rows = []
    for product in products:
        item_no = product["item_no"]
        name    = product["name"]
        if item_no in existing:
            continue
        kw = extract_keywords(name)
        new_rows.append([item_no, name, kw[0], kw[1], kw[2], "Y", now])
        print(f"  追加: [{item_no}] {name[:35]} → [{kw[0]}][{kw[1]}][{kw[2]}]")

    if new_rows:
        ws.append_rows(new_rows)

    return sh.url, len(new_rows)


def main():
    print(f"=== 商品スキャン開始: {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    print("Google認証中...")
    gc = get_google_client()

    print("Yahoo!ショッピングAPIで商品取得中...")
    products = fetch_all_products()
    print(f"取得完了: {len(products)}商品")

    print("スプレッドシート更新中...")
    url, added = update_product_sheet(gc, products)

    print(f"\n新規追加: {added}件")
    print(f"URL: {url}")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
