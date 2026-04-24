"""
ダッシュボードシート作成
- 最新順位を商品×エリア横並びで表示
- 前日比の変化を矢印＋色で表示
"""
import pickle, gspread, sys, time, os, urllib.parse
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle")
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")

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
gc = gspread.authorize(creds)
sh = gc.open('Yahoo!キーワードトラッカー')

# --- データ読み込み ---
ws_rank = sh.worksheet('検索順位')
all_rows = ws_rank.get_all_values()[1:]  # ヘッダー除く
print(f"総データ数: {len(all_rows)}件")

# 日付一覧（新しい順）
dates = sorted(set(r[0] for r in all_rows if r[0]), reverse=True)
print(f"取得日: {dates}")
today   = dates[0] if len(dates) >= 1 else None
yesterday = dates[1] if len(dates) >= 2 else None
print(f"最新: {today}, 前日: {yesterday}")

# データを {(日付, エリア, キーワード): (商品番号, 商品名, 自然順位, PR順位)} に変換
data = {}
for r in all_rows:
    if len(r) < 7:
        continue
    date, item_no, product_name, area, kw, org, pr = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
    data[(date, area, kw)] = (item_no, product_name, org, pr)

# キーワード一覧（商品番号・商品名つき）- 最新日優先
kw_info = {}  # kw -> (item_no, product_name)
for r in all_rows:
    if len(r) < 7:
        continue
    _, item_no, product_name, area, kw, org, pr = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
    if kw not in kw_info:
        kw_info[kw] = (item_no, product_name)

# キーワードを商品番号でソート
kw_list = sorted(kw_info.keys(), key=lambda k: kw_info[k][0])

areas = ['東京', '兵庫']

def rank_val(s):
    """順位文字列を数値に変換（圏外=9999）"""
    try:
        return int(s)
    except:
        return 9999

def change_str(today_val, prev_val):
    """順位変化を文字列に"""
    if prev_val is None or today_val is None:
        return ""
    t = rank_val(today_val)
    p = rank_val(prev_val)
    if t == p:
        return "→"
    elif t < p:
        diff = p - t
        return f"↑{diff}"
    else:
        diff = t - p
        return f"↓{diff}"

# --- ダッシュボードシート作成 ---
try:
    ws_dash = sh.worksheet('ダッシュボード')
    ws_dash.clear()
    print("ダッシュボードシートをクリアしました")
except gspread.WorksheetNotFound:
    ws_dash = sh.add_worksheet(title='ダッシュボード', rows=1000, cols=20)
    print("ダッシュボードシートを作成しました")

def search_url(kw, area_code):
    encoded = urllib.parse.quote(kw)
    return f'=HYPERLINK("https://shopping.yahoo.co.jp/search/{encoded}/0/?first=1&tab_ex=commerce&prom=1&sort=score&area={area_code}","検索")'

# ヘッダー行
header = ['商品番号', '商品名', 'キーワード',
          '東京\n自然順位', '東京\n変化', '東京\nPR順位', '東京\nPR変化',
          '兵庫\n自然順位', '兵庫\n変化', '兵庫\nPR順位', '兵庫\nPR変化',
          '東京\n検索', '兵庫\n検索']

rows_out = [header]

# データ行
for kw in kw_list:
    item_no, product_name = kw_info[kw]
    row = [item_no, product_name, kw]

    for area in areas:
        today_rec   = data.get((today, area, kw))
        prev_rec    = data.get((yesterday, area, kw)) if yesterday else None

        today_org = today_rec[2] if today_rec else "未取得"
        today_pr  = today_rec[3] if today_rec else "未取得"
        prev_org  = prev_rec[2]  if prev_rec  else None
        prev_pr   = prev_rec[3]  if prev_rec  else None

        org_change = change_str(today_org, prev_org)
        pr_change  = change_str(today_pr, prev_pr)

        row += [today_org, org_change, today_pr, pr_change]

    # 東京・兵庫の検索URL
    row += [search_url(kw, "13"), search_url(kw, "28")]

    rows_out.append(row)

# メインデータ書き込み（A〜K列）
main_rows = [row[:11] for row in rows_out]
ws_dash.update(range_name='A1', values=main_rows)

# URL列（L・M列）を別途書き込み
url_header = [['東京\n検索', '兵庫\n検索']]
url_rows = [row[11:13] for row in rows_out[1:]]
ws_dash.update(range_name='L1', values=url_header + url_rows, value_input_option='USER_ENTERED')
print(f"データ書き込み完了: {len(rows_out)-1}行")
time.sleep(2)

# --- 書式設定 ---
ws_id = ws_dash.id

requests = []

# ヘッダー背景（濃紺・白文字・太字）
requests.append({'repeatCell': {
    'range': {'sheetId': ws_id, 'startRowIndex': 0, 'endRowIndex': 1},
    'cell': {'userEnteredFormat': {
        'backgroundColor': {'red': 0.13, 'green': 0.19, 'blue': 0.34},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'fontSize': 10},
        'horizontalAlignment': 'CENTER',
        'wrapStrategy': 'WRAP',
    }},
    'fields': 'userEnteredFormat'
}})

# 列幅
col_widths = [80, 200, 180, 75, 60, 75, 60, 75, 60, 75, 60, 55, 55]
for i, w in enumerate(col_widths):
    requests.append({'updateDimensionProperties': {
        'range': {'sheetId': ws_id, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i+1},
        'properties': {'pixelSize': w},
        'fields': 'pixelSize'
    }})

# 行の高さ（ヘッダー）
requests.append({'updateDimensionProperties': {
    'range': {'sheetId': ws_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1},
    'properties': {'pixelSize': 45},
    'fields': 'pixelSize'
}})

# 行の高さ（データ行）
if len(rows_out) > 1:
    requests.append({'updateDimensionProperties': {
        'range': {'sheetId': ws_id, 'dimension': 'ROWS', 'startIndex': 1, 'endIndex': len(rows_out)},
        'properties': {'pixelSize': 22},
        'fields': 'pixelSize'
    }})

# 先頭行を固定
requests.append({'updateSheetProperties': {
    'properties': {'sheetId': ws_id, 'gridProperties': {'frozenRowCount': 1}},
    'fields': 'gridProperties.frozenRowCount'
}})

# 自然順位列（D, H列 = index 3, 7）の色分け条件付き書式
rank_cols = [
    (3, 4),   # 東京 自然・変化
    (5, 6),   # 東京 PR・変化
    (7, 8),   # 兵庫 自然・変化
    (9, 10),  # 兵庫 PR・変化
]

col_letters = ['A','B','C','D','E','F','G','H','I','J','K']

# 順位セルの条件付き書式（D,F,H,J列）
for col_idx in [3, 5, 7, 9]:
    col_letter = col_letters[col_idx]
    n_data = len(rows_out) - 1
    # 1〜10位 → 緑
    requests.append({'addConditionalFormatRule': {'rule': {
        'ranges': [{'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': 1+n_data,
                    'startColumnIndex': col_idx, 'endColumnIndex': col_idx+1}],
        'booleanRule': {
            'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue':
                f'=AND(ISNUMBER(VALUE({col_letter}2)),VALUE({col_letter}2)<=10)'}]},
            'format': {'backgroundColor': {'red': 0.7, 'green': 0.93, 'blue': 0.7},
                       'textFormat': {'bold': True}}
        }
    }, 'index': 0}}),
    # 11〜30位 → 黄
    requests.append({'addConditionalFormatRule': {'rule': {
        'ranges': [{'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': 1+n_data,
                    'startColumnIndex': col_idx, 'endColumnIndex': col_idx+1}],
        'booleanRule': {
            'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue':
                f'=AND(ISNUMBER(VALUE({col_letter}2)),VALUE({col_letter}2)>=11,VALUE({col_letter}2)<=30)'}]},
            'format': {'backgroundColor': {'red': 1.0, 'green': 0.95, 'blue': 0.6}}
        }
    }, 'index': 1}}),
    # 31〜100位 → オレンジ
    requests.append({'addConditionalFormatRule': {'rule': {
        'ranges': [{'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': 1+n_data,
                    'startColumnIndex': col_idx, 'endColumnIndex': col_idx+1}],
        'booleanRule': {
            'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue':
                f'=AND(ISNUMBER(VALUE({col_letter}2)),VALUE({col_letter}2)>=31,VALUE({col_letter}2)<=100)'}]},
            'format': {'backgroundColor': {'red': 1.0, 'green': 0.8, 'blue': 0.5}}
        }
    }, 'index': 2}}),
    # 圏外 → グレー
    requests.append({'addConditionalFormatRule': {'rule': {
        'ranges': [{'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': 1+n_data,
                    'startColumnIndex': col_idx, 'endColumnIndex': col_idx+1}],
        'booleanRule': {
            'condition': {'type': 'TEXT_EQ', 'values': [{'userEnteredValue': '圏外'}]},
            'format': {'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                       'textFormat': {'foregroundColor': {'red': 0.6, 'green': 0.6, 'blue': 0.6}}}
        }
    }, 'index': 3}}),

# 変化列（E,G,I,K列）の色分け
for col_idx in [4, 6, 8, 10]:
    col_letter = col_letters[col_idx]
    n_data = len(rows_out) - 1
    # ↑ → 緑（順位アップ）
    requests.append({'addConditionalFormatRule': {'rule': {
        'ranges': [{'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': 1+n_data,
                    'startColumnIndex': col_idx, 'endColumnIndex': col_idx+1}],
        'booleanRule': {
            'condition': {'type': 'TEXT_CONTAINS', 'values': [{'userEnteredValue': '↑'}]},
            'format': {'textFormat': {'bold': True, 'foregroundColor': {'red': 0.1, 'green': 0.6, 'blue': 0.1}}}
        }
    }, 'index': 4}}),
    # ↓ → 赤（順位ダウン）
    requests.append({'addConditionalFormatRule': {'rule': {
        'ranges': [{'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': 1+n_data,
                    'startColumnIndex': col_idx, 'endColumnIndex': col_idx+1}],
        'booleanRule': {
            'condition': {'type': 'TEXT_CONTAINS', 'values': [{'userEnteredValue': '↓'}]},
            'format': {'textFormat': {'bold': True, 'foregroundColor': {'red': 0.8, 'green': 0.1, 'blue': 0.1}}}
        }
    }, 'index': 5}}),

# 既存のbandingを削除してから追加
spreadsheet_data = sh.fetch_sheet_metadata()
for s in spreadsheet_data.get('sheets', []):
    if s['properties']['sheetId'] == ws_id:
        for br in s.get('bandedRanges', []):
            requests.insert(0, {'deleteBanding': {'bandedRangeId': br['bandedRangeId']}})
        break

# 交互行の色分け（薄いグレー）
requests.append({'addBanding': {
    'bandedRange': {
        'range': {'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': len(rows_out),
                  'startColumnIndex': 0, 'endColumnIndex': 11},
        'rowProperties': {
            'firstBandColor': {'red': 1, 'green': 1, 'blue': 1},
            'secondBandColor': {'red': 0.95, 'green': 0.95, 'blue': 0.97},
        }
    }
}})

# 全セルの縦位置を中央に
requests.append({'repeatCell': {
    'range': {'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': len(rows_out)},
    'cell': {'userEnteredFormat': {'verticalAlignment': 'MIDDLE'}},
    'fields': 'userEnteredFormat.verticalAlignment'
}})

# URL列（L・M）を中央揃え
requests.append({'repeatCell': {
    'range': {'sheetId': ws_id, 'startRowIndex': 1, 'endRowIndex': len(rows_out),
              'startColumnIndex': 11, 'endColumnIndex': 13},
    'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER'}},
    'fields': 'userEnteredFormat.horizontalAlignment'
}})

sh.batch_update({'requests': requests})
print("書式設定完了")
print(f"\nダッシュボード: {sh.url}")
