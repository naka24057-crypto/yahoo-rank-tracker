# -*- coding: utf-8 -*-
"""Google API の一時障害を受け流すための1本。3本のスクリプトから使う。

🚨2026-09-01にこれが無くて順位チェックが落ちた。
　 product_scraper.py の gc.open() が APIError[503] を返し、
   **3分24秒で2時間半の処理が全部飛んだ**。Yahoo!側は正常で「取得完了: 82商品」まで進んでいた。
🚨いちばん危ないのは rank_tracker_fast.py の測定ループ。1行ずつ append_row しているので、
   2時間半の途中で1回503が来ると、それまで測ったぶんが全部失われる。
⚠️404・権限エラー・シート不在は再試行しない。待っても直らないので、すぐ落として原因を見せる。
"""
import time

import gspread

RETRY_CODES = (429, 500, 502, 503, 504)
DELAYS = (5, 15, 45, 90)


def gs_retry(fn, *args, **kwargs):
    """Google API の 5xx と 429 だけ再試行する。それ以外はそのまま投げる。"""
    for i, d in enumerate(DELAYS + (None,)):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            code = None
            try:
                code = e.response.status_code
            except Exception:
                pass
            if code not in RETRY_CODES or d is None:
                raise
            print("  Google APIが %s を返した。%d秒待って再試行 (%d/%d)"
                  % (code, d, i + 1, len(DELAYS)), flush=True)
            time.sleep(d)
