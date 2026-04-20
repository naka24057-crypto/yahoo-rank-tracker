"""
Yahoo!ショッピング キーワードサジェスト取得 → Googleスプレッドシート自動更新
サジェストはGoogleサジェストAPI（無料・認証不要）を使用
"""
import time
import os
import urllib.parse
import pickle
import requests
from datetime import datetime

import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

KEYWORDS = [
    "プラグレンチ",
    "プラグレンチ 16mm",
    "プラグレンチ 14mm",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")
TOKEN_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle")
SHEET_NAME       = "Yahoo!キーワードトラッカー"


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


def get_suggests(keyword):
    """GoogleサジェストAPIでキーワード候補を取得"""
    url = (
        "https://suggestqueries.google.com/complete/search"
        f"?client=firefox&q={urllib.parse.quote(keyword)}&hl=ja"
    )
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        suggests = data[1] if len(data) > 1 else []
        return [s for s in suggests if isinstance(s, str)][:20]
    except Exception as e:
        print(f"  サジェスト取得エラー: {e}")
        return []


def update_sheet(gc, all_suggests):
    try:
        sh = gc.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(SHEET_NAME)
        print(f"スプレッドシート作成: {sh.url}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for kw, suggests in all_suggests.items():
        sheet_title = kw[:30]
        try:
            ws = sh.worksheet(sheet_title)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_title, rows=1000, cols=30)
            ws.append_row(["取得日時"] + [f"サジェスト{i+1}" for i in range(20)])

        row = [now] + suggests[:20]
        ws.append_row(row)
        print(f"  {kw}: {len(suggests)}件 → 更新完了")

    return sh.url


def main():
    print(f"=== キーワードトラッカー開始: {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    print("Google認証中...")
    gc = get_google_client()

    all_suggests = {}
    for kw in KEYWORDS:
        print(f"取得中: {kw}")
        suggests = get_suggests(kw)
        all_suggests[kw] = suggests
        print(f"  → {suggests[:5]}")
        time.sleep(1)

    print("スプレッドシート更新中...")
    url = update_sheet(gc, all_suggests)
    print(f"完了！URL: {url}")
    print("=== 終了 ===")


if __name__ == "__main__":
    main()
