"""
「消耗品で利益を取る入口商品モデル」が成立するかを数字で判定する。

使い方:
    python3 entry_product_model.py            # ベルトサンダーのケースを計算
    python3 entry_product_model.py --screen   # 逆算型リサーチの足切りチェックのみ

考え方:
  本体を薄利（または赤字）で売り、その本体が呼び込む消耗品のリピートで回収できるか。
  回収できる条件は 1台あたりの年間消耗品限界利益 >= 本体1台の赤字額。
  リピート周期が長い消耗品（大容量セット等）はこの式の分子が伸びないので成立しない。
"""
import argparse

# --- 自社のコスト構造（2026年8月時点・実利益ダッシュボードより） ---
YAHOO_VAR_RATE   = 0.243  # 16.7% + 9.0%x84.7% + max(0.1%,個別料率)x15.3%（個別0%のとき）
YAHOO_VAR_RATE_9 = 0.253  # 2026年9月の出店プラン変更で +1.0pt
RAKUTEN_VAR_RATE = 0.267  # 楽天のモール変動費
CLICKPOST     = 185       # クリックポスト（〜2026/09）
CLICKPOST_OCT = 240       # クリックポスト（2026/10〜）


def marginal_profit(price, cost, shipping, var_rate):
    """1個あたりの限界利益（税込売価 − 原価 − 送料 − モール変動費）"""
    return price - cost - shipping - price * var_rate


def blended(values_and_weights):
    """モール別の限界利益を販売構成比で加重平均する"""
    total_w = sum(w for _, w in values_and_weights)
    return sum(v * w for v, w in values_and_weights) / total_w


def consumable_per_body(attach_rate, repeats_per_year, retention, years=1):
    """本体1台が生む消耗品の販売セット数。

    attach_rate      本体購入時に消耗品も一緒に買う率
    repeats_per_year 使い切って買い直す回数（年）
    retention        買い直すとき自店で買う率
    """
    return attach_rate + repeats_per_year * retention * years


def ltv_per_body(body_mp, consumable_mp, sets_per_body):
    """本体1台あたりの限界利益合計（本体＋その台が生む消耗品）"""
    return body_mp + consumable_mp * sets_per_body


def breakeven_sets(body_mp, consumable_mp):
    """本体が赤字のとき、回収に必要な消耗品セット数。黒字なら0。"""
    if body_mp >= 0:
        return 0.0
    return -body_mp / consumable_mp


def monthly_impact(body_units, body_mp, consumable_mp, sets_per_body):
    """本体をN台/月売ったときの月次限界利益の増分"""
    return body_units * ltv_per_body(body_mp, consumable_mp, sets_per_body)


# --- 逆算型リサーチ（利益の取れる消耗品 → その本体を探す）の足切り ---
SCREEN_RULES = [
    ("リピート周期",   "1回の購入を4ヶ月以内に使い切る量で売っているか",
     "大容量セットは買い直しが年1回未満になり、入口の赤字を回収できない"),
    ("本体の需要",     "本体キーワードの検索需要が消耗品キーワードの3倍以上あるか",
     "本体が入口として機能するには、消耗品より母数が大きいことが前提"),
    ("本体の採算",     "本体単体の限界利益がプラスか",
     "赤字入口は消耗品では回収できない。薄利は可、赤字は不可"),
    ("消耗品の採算",   "消耗品の限界利益が1個400円以上あるか",
     "回収の分子。これを下回ると何台売っても効かない"),
    ("受け皿の順位",   "消耗品が主要語で3位以内を取れているか（or 取れる見込みか）",
     "本体で増やした需要を自店で受けられなければ他店に流れる"),
    ("物流",           "本体の送料が売価の15%以下に収まるか",
     "本体は厚み・重量が出るので送料が採算を壊しやすい"),
    ("故障リスク",     "非電動または単純機構か（初期不良・保証対応が軽いか）",
     "薄利の本体で返品対応が発生すると1件で数台分の利益が飛ぶ"),
]


def print_screen():
    print("=== 逆算型リサーチ 足切りチェック（消耗品 → 本体） ===")
    print("7項目すべてYESで初めて『入口商品モデル』の検討に進む。\n")
    for i, (name, question, why) in enumerate(SCREEN_RULES, 1):
        print(f"{i}. [{name}] {question}")
        print(f"   理由: {why}\n")


def run_belt_sander():
    print("=== ケース: ベルトサンダー本体（102-001） × 替えベルト10x330（104-0050） ===\n")

    # 消耗品：替えベルト 50本セット
    # 売価は実測（2026-08-04 取得: Yahoo 1,393円 / 楽天 1,980円）
    # 原価は管理表から取得できなかったため店舗平均原価率37.3%で置いた仮値
    belt_cost = 500
    belt_yahoo   = marginal_profit(1393, belt_cost, CLICKPOST, YAHOO_VAR_RATE)
    belt_rakuten = marginal_profit(1980, belt_cost, CLICKPOST, RAKUTEN_VAR_RATE)
    belt_yahoo_oct   = marginal_profit(1393, belt_cost, CLICKPOST_OCT, YAHOO_VAR_RATE_9)
    belt_rakuten_oct = marginal_profit(1980, belt_cost, CLICKPOST_OCT, RAKUTEN_VAR_RATE)

    belt_mp     = blended([(belt_yahoo, 7), (belt_rakuten, 3)])
    belt_mp_oct = blended([(belt_yahoo_oct, 7), (belt_rakuten_oct, 3)])

    print(f"替えベルト1セットの限界利益  Yahoo {belt_yahoo:,.0f}円 / 楽天 {belt_rakuten:,.0f}円")
    print(f"  加重平均(Y7:R3)             {belt_mp:,.0f}円")
    print(f"  2026年10月以降              {belt_mp_oct:,.0f}円 （送料+55円・変動費+1.0pt）")

    units = 59 / 3  # 3ヶ月販売数59個（2026年7月時点）
    print(f"\n現状の替えベルト事業  {units:.1f}個/月 x {belt_mp:,.0f}円 = 月 {units * belt_mp:,.0f}円")

    # 本体：仕入価格が確定していないので3ケース
    print("\n--- 本体の限界利益（売価4,980円・送料650円・Yahoo変動費24.3%） ---")
    for body_cost in (2000, 2500, 3000):
        mp = marginal_profit(4980, body_cost, 650, YAHOO_VAR_RATE)
        print(f"  原価 {body_cost:,}円 → 限界利益 {mp:,.0f}円 （{mp / 4980:.1%}）")

    # 回収シミュレーション
    print("\n--- 本体1台が生む消耗品（同梱率40%・年1回買い直し・自店継続率50%）---")
    sets = consumable_per_body(attach_rate=0.4, repeats_per_year=1.0, retention=0.5)
    print(f"  年間 {sets:.2f}セット/台 → 消耗品の限界利益 {sets * belt_mp:,.0f}円/台/年")

    print("\n--- 本体が赤字だった場合、回収に必要な消耗品セット数 ---")
    for loss in (-200, -500, -1000):
        need = breakeven_sets(loss, belt_mp)
        verdict = "達成可能" if need <= sets else "達成不可"
        print(f"  本体 {loss:,}円/台 → 必要 {need:.2f}セット/台 （実力 {sets:.2f}）… {verdict}")

    print("\n--- 月次インパクト（本体の限界利益 +920円/台の場合）---")
    for n in (3, 5, 10, 20):
        impact = monthly_impact(n, 920, belt_mp, sets)
        print(f"  本体 {n:2d}台/月 → 月 {impact:7,.0f}円 （店舗月利益72万円に対し {impact / 720000:.1%}）")

    print("\n※ 目標『利益率+3pt = 月+107,000円』に対して、この施策の寄与は上限でも1〜2割。")


def main():
    parser = argparse.ArgumentParser(description="入口商品モデルの成立判定")
    parser.add_argument("--screen", action="store_true", help="逆算型リサーチの足切りチェックのみ表示")
    args = parser.parse_args()

    if args.screen:
        print_screen()
        return

    run_belt_sander()
    print()
    print_screen()


if __name__ == "__main__":
    main()
