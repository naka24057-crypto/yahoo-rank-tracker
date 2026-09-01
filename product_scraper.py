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

from gs_retry import gs_retry

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
        sh = gs_retry(gc.open, SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(SHEET_NAME)

    try:
        ws = gs_retry(sh.worksheet, PRODUCT_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=PRODUCT_SHEET, rows=1000, cols=10)
        ws.append_row(["商品番号", "商品名", "キーワード1", "キーワード2", "キーワード3", "追跡", "最終確認"])
        ws.freeze(rows=1)

    # 既存データ取得（ヘッダー除く）
    all_rows = gs_retry(ws.get_all_values)[1:]
    # item_no → (row_index, 商品名, キーワード1, キーワード2, キーワード3, 追跡, 最終確認)
    existing = {}
    for i, row in enumerate(all_rows):
        if len(row) < 2 or not row[0]:
            continue
        row_padded = row + [""] * (7 - len(row))
        existing[row[0]] = (i + 2, row_padded[1], row_padded[2], row_padded[3], row_padded[4], row_padded[5], row_padded[6])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_rows = []
    update_batch = []  # バッチ更新用 [(range, values), ...]
    added = 0
    updated = 0

    for product in products:
        item_no = product["item_no"]
        name    = product["name"]
        kw      = extract_keywords(name)

        if item_no in existing:
            row_idx, old_name, old_kw1, old_kw2, old_kw3, track, _ = existing[item_no]
            # 商品名 or キーワードが変わっていたら更新
            if name != old_name or kw[0] != old_kw1 or kw[1] != old_kw2 or kw[2] != old_kw3:
                # 追跡列(F)は保持、最終確認(G)を今の時刻に更新
                update_batch.append({
                    'range': f'A{row_idx}:G{row_idx}',
                    'values': [[item_no, name, kw[0], kw[1], kw[2], track or "Y", now]]
                })
                updated += 1
                print(f"  更新: [{item_no}] {name[:35]}")
        else:
            new_rows.append([item_no, name, kw[0], kw[1], kw[2], "Y", now])
            added += 1
            print(f"  追加: [{item_no}] {name[:35]} → [{kw[0]}][{kw[1]}][{kw[2]}]")

    if new_rows:
        gs_retry(ws.append_rows, new_rows)
    if update_batch:
        gs_retry(ws.batch_update, update_batch)

    print(f"\n新規追加: {added}件 / 更新: {updated}件")
    return sh.url, added, updated


def main():
    print(f"=== 商品スキャン開始: {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    print("Google認証中...")
    gc = get_google_client()

    print("Yahoo!ショッピングAPIで商品取得中...")
    products = fetch_all_products()
    print(f"取得完了: {len(products)}商品")

    print("スプレッドシート更新中...")
    url, added, updated = update_product_sheet(gc, products)

    print(f"URL: {url}")
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
