#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GSC 系スクリプト（striking_distance.py / low_ctr.py / decay.py）の検証。

1. data/ にフィクスチャの CSV を生成する（ドメインは example.jp、値はすべて架空）。
2. 各ケースでスクリプトを実行し、終了コード・出力列・各行の値・標準エラーの文言を照合する。
   期待値は下の EXP_* に手計算した値を直接書いている（スクリプトと同じロジックで再計算しない）。

3. attack_tests(): 壊しにいくテスト（数値の表記、区切り文字、文字コード、列名の重複、値の異常、
   掲載順位 0（エクスポートで値なしが 0 になったもの）、
   CSV インジェクション対策、decay のキー照合、引数の範囲、Python 3.9 の文法、10 万行の処理時間、
   共通部分の同一性、__pycache__ の有無）。

使い方:
  python run_tests.py [--python 実行する Python] [--scripts スクリプトのディレクトリ] [--label 結果ファイル名の接尾辞]

関連ファイル:
  common_block.py  3 本のスクリプトの「共通部分」の正本。編集したら sync_common.py で 3 本に差し込む。
  sync_common.py   共通部分の差し込み（--check で一致の確認だけ）。
  orig/            改修前（2026-09-25 の攻撃的テスト前）のスクリプトと run_tests.py。新しいテストの検出力の確認用。
"""

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
# 既定の対象は、このリポジトリの skills/seo-operator（環境変数 SEO_OPERATOR_DIR で切り替える）
REPO_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "skills", "seo-operator")
DEFAULT_SCRIPTS = os.path.join(os.environ.get("SEO_OPERATOR_DIR", REPO_SKILL), "scripts")

FULLWIDTH = str.maketrans("0123456789", "０１２３４５６７８９")

# ---------------------------------------------------------------------------
# データセット（架空）
# ---------------------------------------------------------------------------

# striking_distance 用: (query, page, clicks, impressions, position)
S_ROWS = [
    ("example 株式会社", "https://example.jp/", 300, 1000, 1.2),
    ("有機野菜 宅配", "https://example.jp/organic/", 60, 400, 2.5),
    ("野菜 定期便", "https://example.jp/subscription/", 40, 400, 3.0),
    ("無農薬 にんじん", "https://example.jp/carrot/", 5, 50, 3.4),
    ("野菜ジュース 作り方", "https://example.jp/juice/", 3, 100, 7.9),
    ("野菜 宅配 おすすめ", "https://example.jp/%E3%81%8A%E3%81%99%E3%81%99%E3%82%81/", 20, 1000, 8.0),
    ("example 野菜 セット", "https://example.jp/set/", 60, 200, 9.0),
    ("野菜 保存方法", "https://example.jp/storage/", 1, 49, 10.0),
    ("野菜 宅配 人気", "https://example.jp/popular/", 150, 500, 11.0),
    ("有機野菜 通販", "https://example.jp/shop/", 12, 400, 12.4),
    ("旬の野菜 一覧", "https://example.jp/seasonal/", 3, 60, 15.0),
    ("野菜 レシピ 簡単", "https://example.jp/recipe/", 1, 50, 18.0),
    ("野菜 宅配 比較", "https://example.jp/compare/", 0, 300, 20.0),
    ("野菜 宅配 口コミ", "https://example.jp/review/", 2, 200, 20.1),
]
S_PAGE = {q: p for q, p, _c, _i, _pos in S_ROWS}
# API 形式（クエリ x ページ）で追加する行
S_API_EXTRA = [("野菜 宅配 おすすめ", "https://example.jp/p2/", 5, 250, 14.0)]

# low_ctr 用: (query, clicks, impressions, position)
L_ROWS = [
    # [1,2): 6 行。合計 1000 / 4000 = 0.25（example を除くと 400 / 3000 = 0.133333）
    ("example 公式", 600, 1000, 1.1),
    ("有機野菜 宅配", 200, 1000, 1.3),
    ("野菜 定期便", 100, 500, 1.5),
    ("野菜 宅配 安い", 30, 300, 1.8),
    ("野菜 詰め合わせ", 40, 200, 1.9),
    ("産直 野菜", 30, 1000, 1.6),
    # [2,3): 5 行。合計 200 / 2000 = 0.10
    ("野菜 通販", 100, 800, 2.2),
    ("有機野菜 セット", 50, 500, 2.5),
    ("野菜 宅配 冷凍", 20, 200, 2.9),
    ("野菜 宅配 一人暮らし", 9, 300, 2.0),
    ("野菜 まとめ買い", 21, 200, 2.7),
    # [3,4): 4 行（最低行数 5 未満で空欄）。合計 37 / 900
    ("野菜 宅配 ランキング", 10, 200, 3.2),
    ("野菜 宅配 お試し", 2, 200, 3.5),
    ("オーガニック 野菜", 20, 400, 3.9),
    ("野菜 宅配 高齢者", 5, 100, 3.0),
    # [4,6): 表示回数 10 以上が 5 行で 40 / 1000 = 0.04。仙台（表示回数 8）は基準から外れる
    ("野菜 宅配 子育て", 20, 400, 4.0),
    ("野菜 宅配 東京", 10, 200, 4.5),
    ("野菜 宅配 大阪", 3, 300, 5.2),
    ("野菜 宅配 福岡", 0, 50, 5.9),
    ("野菜 宅配 名古屋", 7, 50, 4.8),
    ("野菜 宅配 仙台", 8, 8, 5.0),
    # [6,8): 5 行。合計 30 / 1000 = 0.03
    ("野菜 宅配 評判", 6, 200, 6.0),
    ("野菜 宅配 解約", 3, 100, 6.5),
    ("野菜 宅配 メリット", 9, 300, 7.0),
    ("野菜 宅配 デメリット", 1, 200, 7.5),
    ("野菜 宅配 料金", 11, 200, 7.99),
    # [8,11): 5 行。合計 20 / 1000 = 0.02
    ("野菜 宅配 比較", 4, 200, 8.0),
    ("野菜 宅配 おすすめ", 10, 500, 9.0),
    ("野菜 宅配 口コミ", 0, 100, 10.0),
    ("野菜 宅配 ミールキット", 2, 100, 10.5),
    ("野菜 宅配 人気", 4, 100, 9.5),
    # [11,16): 2 行
    ("野菜 宅配 北海道", 1, 100, 12.0),
    ("野菜 宅配 沖縄", 0, 50, 15.5),
]
L_PAGE = {row[0]: f"https://example.jp/l/{i:02d}/" for i, row in enumerate(L_ROWS)}
L_FULL = [(q, L_PAGE[q], c, i, p) for q, c, i, p in L_ROWS]

# low_ctr --benchmark 用の小さなデータ
LB_ROWS = [
    ("a 野菜", "https://example.jp/lb/a/", 1, 100, 2.5),
    ("b 野菜", "https://example.jp/lb/b/", 0, 200, 4.4),
    ("c 野菜", "https://example.jp/lb/c/", 0, 100, 9.0),
    ("d 野菜", "https://example.jp/lb/d/", 10, 100, 1.2),
    ("e 野菜", "https://example.jp/lb/e/", 3, 100, 3.0),
]

# decay 用: (page, clicks, impressions, position)
D_PREV = [
    ("https://example.jp/vegetable/box/", 100, 2000, 3.0),
    ("https://example.jp/vegetable/organic/", 200, 4000, 4.0),
    ("https://example.jp/vegetable/seasonal/", 150, 3000, 5.0),
    ("https://example.jp/vegetable/recipe/", 120, 2000, 2.0),
    ("https://example.jp/vegetable/storage/", 100, 2000, 6.0),
    ("https://example.jp/vegetable/juice/", 50, 1000, 6.2),
    ("https://example.jp/vegetable/small-drop/", 100, 2000, 3.0),
    ("https://example.jp/vegetable/few-clicks/", 19, 500, 9.0),
    ("https://example.jp/vegetable/drop9/", 30, 600, 5.0),
    ("https://example.jp/vegetable/growth/", 50, 1000, 5.0),
    ("https://example.jp/%E9%87%8E%E8%8F%9C/", 20, 400, 4.0),
]
D_CUR = [
    ("https://example.jp/vegetable/organic/", 100, 3000, 7.0),
    ("https://example.jp/vegetable/seasonal/", 90, 1800, 5.5),
    ("https://example.jp/vegetable/recipe/", 60, 1900, 2.3),
    ("https://example.jp/vegetable/storage/", 70, 1700, 7.5),
    ("https://example.jp/vegetable/juice/", 40, 1000, 8.2),
    ("https://example.jp/vegetable/small-drop/", 81, 2000, 3.0),
    ("https://example.jp/vegetable/drop9/", 21, 600, 5.0),
    ("https://example.jp/vegetable/growth/", 80, 1200, 4.0),
    ("https://example.jp/vegetable/new/", 40, 800, 6.0),
    ("https://example.jp/%E9%87%8E%E8%8F%9C/", 10, 400, 4.2),
]

HEADERS = {
    "en_q": ["Top queries", "Clicks", "Impressions", "CTR", "Position"],
    "ja_q": ["上位のクエリ", "クリック数", "表示回数", "CTR", "掲載順位"],
    "en_p": ["Top pages", "Clicks", "Impressions", "CTR", "Position"],
    "ja_p": ["上位のページ", "クリック数", "表示回数", "CTR", "掲載順位"],
    "api": ["Query", "Page", "Clicks", "Impressions", "CTR", "Position"],
}


# ---------------------------------------------------------------------------
# フィクスチャの生成
# ---------------------------------------------------------------------------

def fmt_ctr(clicks, impressions, style):
    ratio = clicks / impressions if impressions else 0.0
    if style == "pct":
        return f"{ratio * 100:.2f}%"
    if style == "ratio":
        return f"{ratio:.6f}"
    if style == "pctnum":
        return f"{ratio * 100:.4f}"
    raise ValueError(style)


def fmt_num(n, thousands):
    return f"{n:,}" if thousands else str(n)


def write_file(name, header, rows, encoding="utf-8-sig", delimiter=",", newline="\r\n"):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator=newline)
    writer.writerow(header)
    writer.writerows(rows)
    path = os.path.join(DATA, name)
    with open(path, "wb") as f:
        f.write(buf.getvalue().encode(encoding))
    return path


def make_rows(dataset, key, ctr_style="pct", thousands=False, with_ctr=True, messy=False):
    """dataset の要素は (query, page, clicks, impressions, position)。key は query / page / both。"""
    out = []
    for idx, (q, p, c, i, pos) in enumerate(dataset):
        clicks = fmt_num(c, thousands)
        impressions = fmt_num(i, thousands)
        if messy and idx == 9:
            clicks = clicks.translate(FULLWIDTH)  # 全角数字
        if messy and idx == 1:
            impressions = f" {impressions} "  # 前後の空白
        row = []
        if key in ("query", "both"):
            row.append(q)
        if key in ("page", "both"):
            row.append(p)
        row += [clicks, impressions]
        if with_ctr:
            row.append(fmt_ctr(c, i, ctr_style))
        row.append(str(pos))
        out.append(row)
    if messy:
        # 解析できない行（除外されて件数が標準エラーに出る）
        bad = []
        if key in ("query", "both"):
            bad.append("解析できない行")
        if key in ("page", "both"):
            bad.append("https://example.jp/broken/")
        bad += ["-", "n/a"]
        if with_ctr:
            bad.append("")
        bad.append("12")
        out.append(bad)
    return out


def drop_ctr(header):
    return [h for h in header if h != "CTR"]


def gen_variants(prefix, dataset):
    write_file(f"{prefix}_en_pct.csv", HEADERS["en_q"], make_rows(dataset, "query", "pct"))
    write_file(f"{prefix}_ja_ratio.csv", HEADERS["ja_q"], make_rows(dataset, "query", "ratio"), newline="\n")
    write_file(f"{prefix}_ja_pctnum.csv", HEADERS["ja_q"], make_rows(dataset, "query", "pctnum"))
    write_file(f"{prefix}_en_noctr.csv", drop_ctr(HEADERS["en_q"]), make_rows(dataset, "query", with_ctr=False))
    write_file(f"{prefix}_ja_cp932.csv", HEADERS["ja_q"], make_rows(dataset, "query", "pct"), encoding="cp932")
    write_file(f"{prefix}_en_thousands.csv", HEADERS["en_q"],
               make_rows(dataset, "query", "pct", thousands=True, messy=True))
    write_file(f"{prefix}_en_utf16_tab.csv", HEADERS["en_q"], make_rows(dataset, "query", "pct"),
               encoding="utf-16", delimiter="\t")
    write_file(f"{prefix}_en_pages.csv", HEADERS["en_p"], make_rows(dataset, "page", "pct"))
    write_file(f"{prefix}_ja_pages.csv", HEADERS["ja_p"], make_rows(dataset, "page", "ratio"))
    missing_header = ["上位のクエリ", "クリック数", "表示回数", "CTR"]
    write_file(f"{prefix}_missing_pos.csv", missing_header,
               [r[:-1] for r in make_rows(dataset, "query", "pct")])
    write_file(f"{prefix}_empty.csv", HEADERS["en_q"], [])


def gen_all():
    os.makedirs(DATA, exist_ok=True)
    gen_variants("s", S_ROWS)
    write_file("s_api.csv", HEADERS["api"], make_rows(S_ROWS + S_API_EXTRA, "both", "ratio"))
    write_file("s_small_target.csv", HEADERS["en_q"], [
        ["小さい 上位", "9", "90", "10.00%", "2.0"],
        ["小さい 候補", "1", "100", "1.00%", "10.0"],
    ])
    write_file("missing_key.csv", ["Keyword", "Clicks", "Impressions", "CTR", "Position"],
               [["野菜", "1", "10", "10.00%", "3.0"]])
    write_file("comparison.csv",
               ["Top queries", "Last 28 days Clicks", "Previous 28 days Clicks",
                "Last 28 days Impressions", "Previous 28 days Impressions",
                "Last 28 days CTR", "Previous 28 days CTR",
                "Last 28 days Position", "Previous 28 days Position"],
               [["野菜", "1", "2", "10", "20", "10%", "10%", "3.0", "3.1"]])
    with open(os.path.join(DATA, "zero_bytes.csv"), "wb"):
        pass

    gen_variants("l", L_FULL)
    write_file("l_api.csv", HEADERS["api"], make_rows(L_FULL, "both", "ratio"))
    write_file("lb_rows.csv", HEADERS["en_q"], make_rows(LB_ROWS, "query", "pct"))
    write_file("lb_bench.csv", ["position", "ctr"], [["1", "30%"], ["2", "0.10"], ["3", "4%"], ["6", "0.01"]])
    write_file("lb_bench_bad.csv", ["position", "ctr"], [["1", "30"], ["2", "10"]])

    d_prev = [(None, p, c, i, pos) for p, c, i, pos in D_PREV]
    d_cur = [(None, p, c, i, pos) for p, c, i, pos in D_CUR]
    write_file("d_prev_ja.csv", HEADERS["ja_p"], make_rows(d_prev, "page", "pct"))
    write_file("d_cur_ja.csv", HEADERS["ja_p"], make_rows(d_cur, "page", "pct"))
    # 形式を混ぜる: 前期は英語の列名・比率・桁区切り、今期は日本語の列名・百分率の数値・cp932
    write_file("d_prev_en_ratio_thousands.csv", HEADERS["en_p"], make_rows(d_prev, "page", "ratio", thousands=True))
    write_file("d_cur_ja_pctnum_cp932.csv", HEADERS["ja_p"], make_rows(d_cur, "page", "pctnum"), encoding="cp932")
    write_file("d_empty_pages.csv", HEADERS["ja_p"], [])
    write_file("d_missing_impr.csv", ["上位のページ", "クリック数", "CTR", "掲載順位"],
               [["https://example.jp/a/", "10", "5.00%", "3.0"]])
    write_file("d_api_prev.csv", HEADERS["api"], [
        ["野菜 宅配", "https://example.jp/a/", "100", "1000", "0.100000", "3.0"],
        ["野菜 通販", "https://example.jp/c/", "50", "500", "0.100000", "4.0"],
    ])
    write_file("d_api_cur.csv", HEADERS["api"], [
        ["野菜 宅配", "https://example.jp/b/", "90", "1000", "0.090000", "3.0"],
        ["野菜 通販", "https://example.jp/c/", "20", "500", "0.040000", "4.1"],
    ])
    write_file("d_agg_prev.csv", HEADERS["api"], [
        ["野菜 宅配", "https://example.jp/a/", "60", "600", "0.100000", "2.0"],
        ["野菜 宅配", "https://example.jp/b/", "40", "400", "0.100000", "7.0"],
    ])
    write_file("d_agg_cur.csv", HEADERS["en_q"], [["野菜 宅配", "50", "1000", "5.00%", "4.5"]])


# ---------------------------------------------------------------------------
# 期待値（手計算）
# ---------------------------------------------------------------------------

S_COLS = ["clicks", "impressions", "ctr", "ctr_pct", "position", "est_extra_clicks"]
S_KINDS = ["int", "int", "f4", "str", "f2", "f1"]

# 目標 CTR = 掲載順位 3 以下の (300+60+40) / (1000+400+400) = 400/1800 = 0.222222
# est = 表示回数 x max(0, 0.222222 - CTR)
# --min-impressions 50 のときの期待値（旧デフォルト。下限 50 ちょうどの行を含むことも確かめる）
EXP_S_MIN50 = [
    ("野菜 宅配 おすすめ", 20, 1000, 0.02, "2.00%", 8.0, 202.2222),   # 1000 x 0.202222
    ("有機野菜 通販", 12, 400, 0.03, "3.00%", 12.4, 76.8889),          # 400 x 0.192222
    ("野菜 宅配 比較", 0, 300, 0.0, "0.00%", 20.0, 66.6667),           # 300 x 0.222222（20.0 は上限と同値で含む）
    ("旬の野菜 一覧", 3, 60, 0.05, "5.00%", 15.0, 10.3333),            # 60 x 0.172222
    ("野菜 レシピ 簡単", 1, 50, 0.02, "2.00%", 18.0, 10.1111),         # 50 x 0.202222（表示回数 50 は下限と同値で含む）
    ("野菜 宅配 人気", 150, 500, 0.30, "30.00%", 11.0, 0.0),           # CTR が目標を上回るので 0。同値は表示回数の降順
    ("example 野菜 セット", 60, 200, 0.30, "30.00%", 9.0, 0.0),
]
# デフォルト（--min-impressions 100）: 表示回数 60 と 50 の行が外れる
EXP_S_DEFAULT = [r for r in EXP_S_MIN50 if r[2] >= 100]
# --exclude-regex example: 目標 CTR = (60+40) / (400+400) = 0.125
EXP_S_EXCLUDE_MIN50 = [
    ("野菜 宅配 おすすめ", 20, 1000, 0.02, "2.00%", 8.0, 105.0),       # 1000 x 0.105
    ("有機野菜 通販", 12, 400, 0.03, "3.00%", 12.4, 38.0),             # 400 x 0.095
    ("野菜 宅配 比較", 0, 300, 0.0, "0.00%", 20.0, 37.5),              # 300 x 0.125
    ("野菜 レシピ 簡単", 1, 50, 0.02, "2.00%", 18.0, 5.25),            # 50 x 0.105
    ("旬の野菜 一覧", 3, 60, 0.05, "5.00%", 15.0, 4.5),                # 60 x 0.075
    ("野菜 宅配 人気", 150, 500, 0.30, "30.00%", 11.0, 0.0),
]
EXP_S_EXCLUDE = [r for r in EXP_S_EXCLUDE_MIN50 if r[2] >= 100]
# API 形式: おすすめ（p2）250 x 0.202222 = 50.5556 が加わる
EXP_S_API_MIN50 = [
    ("野菜 宅配 おすすめ", S_PAGE["野菜 宅配 おすすめ"], 20, 1000, 0.02, "2.00%", 8.0, 202.2222),
    ("有機野菜 通販", S_PAGE["有機野菜 通販"], 12, 400, 0.03, "3.00%", 12.4, 76.8889),
    ("野菜 宅配 比較", S_PAGE["野菜 宅配 比較"], 0, 300, 0.0, "0.00%", 20.0, 66.6667),
    ("野菜 宅配 おすすめ", "https://example.jp/p2/", 5, 250, 0.02, "2.00%", 14.0, 50.5556),
    ("旬の野菜 一覧", S_PAGE["旬の野菜 一覧"], 3, 60, 0.05, "5.00%", 15.0, 10.3333),
    ("野菜 レシピ 簡単", S_PAGE["野菜 レシピ 簡単"], 1, 50, 0.02, "2.00%", 18.0, 10.1111),
    ("野菜 宅配 人気", S_PAGE["野菜 宅配 人気"], 150, 500, 0.30, "30.00%", 11.0, 0.0),
    ("example 野菜 セット", S_PAGE["example 野菜 セット"], 60, 200, 0.30, "30.00%", 9.0, 0.0),
]
EXP_S_API = [r for r in EXP_S_API_MIN50 if r[3] >= 100]
# --target-max-pos 1: 該当行なし -> est は空欄、表示回数の降順
EXP_S_NO_TARGET_MIN50 = [
    ("野菜 宅配 おすすめ", 20, 1000, 0.02, "2.00%", 8.0, ""),
    ("野菜 宅配 人気", 150, 500, 0.30, "30.00%", 11.0, ""),
    ("有機野菜 通販", 12, 400, 0.03, "3.00%", 12.4, ""),
    ("野菜 宅配 比較", 0, 300, 0.0, "0.00%", 20.0, ""),
    ("example 野菜 セット", 60, 200, 0.30, "30.00%", 9.0, ""),
    ("旬の野菜 一覧", 3, 60, 0.05, "5.00%", 15.0, ""),
    ("野菜 レシピ 簡単", 1, 50, 0.02, "2.00%", 18.0, ""),
]
EXP_S_NO_TARGET = [r for r in EXP_S_NO_TARGET_MIN50 if r[2] >= 100]

L_COLS = ["clicks", "impressions", "ctr", "ctr_pct", "position", "bucket",
          "expected_ctr", "ctr_vs_expected", "lost_clicks"]
L_KINDS = ["int", "int", "f4", "str", "f2", "str", "f4", "f2", "f1"]

# 抽出条件: 掲載順位 <= 10、表示回数 >= 100、CTR < 期待 CTR x 0.5
EXP_L_DEFAULT = [
    ("産直 野菜", 30, 1000, 0.03, "3.00%", 1.6, "[1,2)", 0.25, 0.12, 220.0),          # 1000 x (0.25 - 0.03)
    ("野菜 宅配 安い", 30, 300, 0.10, "10.00%", 1.8, "[1,2)", 0.25, 0.40, 45.0),      # 300 x 0.15
    ("野菜 宅配 一人暮らし", 9, 300, 0.03, "3.00%", 2.0, "[2,3)", 0.10, 0.30, 21.0),  # 300 x 0.07
    ("野菜 宅配 大阪", 3, 300, 0.01, "1.00%", 5.2, "[4,6)", 0.04, 0.25, 9.0),         # 300 x 0.03
    ("野菜 宅配 デメリット", 1, 200, 0.005, "0.50%", 7.5, "[6,8)", 0.03, 0.1667, 5.0),  # 200 x 0.025
    ("野菜 宅配 口コミ", 0, 100, 0.0, "0.00%", 10.0, "[8,11)", 0.02, 0.0, 2.0),       # 100 x 0.02
]
# --exclude-regex example: [1,2) の期待 CTR = 400/3000 = 0.133333、しきい値 0.066667 -> 安い(0.10) は外れる
EXP_L_EXCLUDE = [
    ("産直 野菜", 30, 1000, 0.03, "3.00%", 1.6, "[1,2)", 0.133333, 0.225, 103.3333),
] + EXP_L_DEFAULT[2:]
# --min-bucket-rows 4: [3,4) の期待 CTR = 37/900 = 0.041111 -> お試し(0.01) が該当。200 x 0.031111 = 6.2222
EXP_L_BUCKET4 = EXP_L_DEFAULT[:4] + [
    ("野菜 宅配 お試し", 2, 200, 0.01, "1.00%", 3.5, "[3,4)", 0.041111, 0.2432, 6.2222),
] + EXP_L_DEFAULT[4:]
# --baseline-min-impressions 1: [4,6) に仙台(8/8) が入り 48/1008 = 0.047619。300 x 0.037619 = 11.2857
EXP_L_BASELINE1 = EXP_L_DEFAULT[:3] + [
    ("野菜 宅配 大阪", 3, 300, 0.01, "1.00%", 5.2, "[4,6)", 0.047619, 0.21, 11.2857),
] + EXP_L_DEFAULT[4:]
# --benchmark: 1=0.30, 2=0.10, 3=0.04, 6=0.01。四捨五入で引き、4 は 3 と 6 の線形補間 0.03、9 は範囲外で 0.01
EXP_L_BENCH = [
    ("d 野菜", 10, 100, 0.10, "10.00%", 1.2, "benchmark:1", 0.30, 0.3333, 20.0),  # 100 x 0.20
    ("b 野菜", 0, 200, 0.0, "0.00%", 4.4, "benchmark:4", 0.03, 0.0, 6.0),         # 200 x 0.03
    ("a 野菜", 1, 100, 0.01, "1.00%", 2.5, "benchmark:3", 0.04, 0.25, 3.0),       # 2.5 -> 3（四捨五入）
    ("c 野菜", 0, 100, 0.0, "0.00%", 9.0, "benchmark:9", 0.01, 0.0, 1.0),
]

D_COLS = ["clicks_prev", "clicks_cur", "clicks_diff", "clicks_change_pct", "impressions_prev",
          "impressions_cur", "impressions_change_pct", "ctr_prev", "ctr_cur", "position_prev",
          "position_cur", "pos_diff", "diagnosis"]
D_KINDS = ["int", "int", "int", "f1", "int", "int", "f1", "f4", "f4", "f2", "f2", "f2", "str"]
V = "https://example.jp/vegetable/"
JP = "https://example.jp/%E9%87%8E%E8%8F%9C/"
# --min-drop-pct 20 のときの期待値（旧デフォルト。減少率 20% ちょうどの境界を含むことも確かめる）
EXP_D_DROP20 = [
    # 200 -> 100（-50%）、順位 4.0 -> 7.0（+3.0）
    (V + "organic/", 200, 100, -100, -50.0, 4000, 3000, -25.0, 0.05, 0.0333, 4.0, 7.0, 3.0, "順位低下"),
    (V + "box/", 100, 0, -100, -100.0, 2000, 0, -100.0, 0.05, "", 3.0, "", "", "消失（今期のデータなし）"),
    # 順位 +0.5、表示回数 -40%
    (V + "seasonal/", 150, 90, -60, -40.0, 3000, 1800, -40.0, 0.05, 0.05, 5.0, 5.5, 0.5,
     "需要減（表示回数が減少・順位は維持）"),
    # 順位 +0.3、表示回数 -5%、CTR 6% -> 3.16%（-47%）
    (V + "recipe/", 120, 60, -60, -50.0, 2000, 1900, -5.0, 0.06, 0.0316, 2.0, 2.3, 0.3,
     "CTR低下（順位・表示回数は維持）"),
    # 順位 +1.5、表示回数 -15%、CTR 5% -> 4.12%（-17.6%）: どれも閾値未満
    (V + "storage/", 100, 70, -30, -30.0, 2000, 1700, -15.0, 0.05, 0.0412, 6.0, 7.5, 1.5, "複合要因"),
    # 境界: 減少 10 クリック・20% ちょうど、順位 6.2 -> 8.2（+2.0。浮動小数点では 1.9999999999999991）
    (V + "juice/", 50, 40, -10, -20.0, 1000, 1000, 0.0, 0.05, 0.04, 6.2, 8.2, 2.0, "順位低下"),
    # 境界: 前期 20 クリック、CTR 5% -> 2.5%（-50%）
    (JP, 20, 10, -10, -50.0, 400, 400, 0.0, 0.05, 0.025, 4.0, 4.2, 0.2, "CTR低下（順位・表示回数は維持）"),
]
# デフォルト（--min-drop-pct 30）: 減少率 20% の juice が外れる。storage の 30% ちょうどは残る
EXP_D_DEFAULT = [r for r in EXP_D_DROP20 if "juice" not in r[0]]
EXP_D_EXCLUDE = [r for r in EXP_D_DEFAULT if "juice" not in r[0]]
# 今期がヘッダーのみ: 前期 20 クリック以上はすべて消失（few-clicks の 19 は対象外）
_D_GONE = [
    (V + "organic/", 200, 4000, 4.0), (V + "seasonal/", 150, 3000, 5.0), (V + "recipe/", 120, 2000, 2.0),
    (V + "box/", 100, 2000, 3.0), (V + "small-drop/", 100, 2000, 3.0), (V + "storage/", 100, 2000, 6.0),
    (V + "growth/", 50, 1000, 5.0), (V + "juice/", 50, 1000, 6.2), (V + "drop9/", 30, 600, 5.0),
    (JP, 20, 400, 4.0),
]
EXP_D_EMPTY_CUR = [
    (p, c, 0, -c, -100.0, i, 0, -100.0, round(c / i, 4), "", pos, "", "", "消失（今期のデータなし）")
    for p, c, i, pos in _D_GONE
]
EXP_D_API = [
    ("野菜 宅配", "https://example.jp/a/", 100, 0, -100, -100.0, 1000, 0, -100.0, 0.1, "", 3.0, "", "",
     "消失（今期のデータなし）"),
    ("野菜 通販", "https://example.jp/c/", 50, 20, -30, -60.0, 500, 500, 0.0, 0.1, 0.04, 4.0, 4.1, 0.1,
     "CTR低下（順位・表示回数は維持）"),
]
# 前期の 2 行を合算: 100 / 1000、順位 (2.0x600 + 7.0x400) / 1000 = 4.0
EXP_D_AGG = [
    ("野菜 宅配", 100, 50, -50, -50.0, 1000, 1000, 0.0, 0.1, 0.05, 4.0, 4.5, 0.5, "CTR低下（順位・表示回数は維持）"),
]


# ---------------------------------------------------------------------------
# 実行と照合
# ---------------------------------------------------------------------------

TOL = {"f1": 0.051, "f2": 0.0051, "f4": 0.00006}


def check_value(actual, expected, kind):
    if expected == "":
        return actual == ""
    if kind == "str":
        return actual == expected
    if kind == "int":
        return actual == str(int(expected))
    try:
        return abs(float(actual) - float(expected)) <= TOL[kind]
    except ValueError:
        return False


def parse_csv_bytes(data):
    text = data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    return rows


class Runner:
    def __init__(self, python, scripts):
        self.python = python
        self.scripts = scripts
        self.results = []

    def run(self, script, args):
        cmd = [self.python, os.path.join(self.scripts, script)] + args
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(cmd, cwd=DATA, capture_output=True, env=env)
        return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", errors="replace")

    def record(self, name, ok, detail):
        self.results.append({"name": name, "result": "pass" if ok else "fail", "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    def case(self, name, script, args, exit_code=0, header=None, key_cols=None, value_cols=None,
             kinds=None, expected=None, stderr_has=(), output_file=None, stdout_empty=False,
             stderr_not_has=(), checks=()):
        if output_file:
            stale = os.path.join(DATA, output_file)
            if os.path.exists(stale):
                os.remove(stale)
        code, out, err = self.run(script, args)
        problems = []
        if code != exit_code:
            problems.append(f"終了コード {code}（期待 {exit_code}）")
        for s in stderr_has:
            if s not in err:
                problems.append(f"stderr に「{s}」がない")
        for s in stderr_not_has:
            if s in err:
                problems.append(f"stderr に「{s}」がある")
        if stdout_empty and out:
            problems.append("stdout が空でない")
        if out.startswith(b"\xef\xbb\xbf"):
            problems.append("標準出力に BOM がある")
        for label, fn in checks:
            try:
                ok = fn(code, out, err)
            except Exception as e:  # noqa: BLE001
                ok = False
                label = f"{label}（{type(e).__name__}: {e}）"
            if not ok:
                problems.append(f"確認に失敗: {label}")
        data = out
        if output_file:
            path = os.path.join(DATA, output_file)
            if not os.path.exists(path):
                problems.append("出力ファイルがない")
                data = b""
            else:
                with open(path, "rb") as f:
                    data = f.read()
                if not data.startswith(b"\xef\xbb\xbf"):
                    problems.append("出力ファイルに BOM がない")
        if header is not None:
            rows = parse_csv_bytes(data) if data else []
            if not rows:
                problems.append("出力 CSV が空（ヘッダーもない）")
            else:
                if rows[0] != header:
                    problems.append(f"ヘッダー不一致: {rows[0]}")
                body = rows[1:]
                if expected is not None:
                    if len(body) != len(expected):
                        problems.append(f"行数 {len(body)}（期待 {len(expected)}）")
                    cols = key_cols + value_cols
                    all_kinds = ["str"] * len(key_cols) + kinds
                    for r_i, (act, exp) in enumerate(zip(body, expected)):
                        row_map = dict(zip(rows[0], act))
                        for col, kind, ev in zip(cols, all_kinds, exp):
                            av = row_map.get(col)
                            if av is None or not check_value(av, ev, kind):
                                problems.append(f"{r_i + 1} 行目 {col}: {av!r}（期待 {ev!r}）")
        if problems and err:
            problems.append("stderr: " + err.strip().replace("\n", " / ")[:600])
        n_rows = ""
        if header is not None and not problems:
            n_rows = f"、{len(expected) if expected is not None else 0} 行一致"
        detail = "; ".join(problems) if problems else f"終了コード {code}{n_rows}"
        self.record(name, not problems, detail)
        return code, out, err


# ---------------------------------------------------------------------------
# 壊しにいくテスト（2026-09-25 追加）
# ---------------------------------------------------------------------------

SKILL_DIR = os.path.dirname(DEFAULT_SCRIPTS)  # main() で --scripts の親フォルダに置き換える


def write_raw(name, text, encoding="utf-8"):
    path = os.path.join(DATA, name)
    with open(path, "wb") as f:
        f.write(text.encode(encoding) if isinstance(text, str) else text)
    return path


def s_lines(fmt_int, fmt_ctr, fmt_pos, delimiter=",", header=None, extra=None):
    """S_ROWS を任意の数値表記で CSV の行にする。fmt_* はセルの文字列を返す（引用符は csv が付ける）。"""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header or HEADERS["en_q"])
    for q, _p, c, i, pos in S_ROWS:
        row = [q, fmt_int(c), fmt_int(i), fmt_ctr(c, i), fmt_pos(pos)]
        if extra:
            row += extra
        writer.writerow(row)
    return buf.getvalue()


def eu_int(n):
    return f"{n:,}".replace(",", ".")


def eu_dec(x, digits):
    return f"{x:.{digits}f}".replace(".", ",")


def gen_attack():
    # --- 数値の表記 ---
    # セミコロン区切り・小数点カンマ・点の桁区切り（ヨーロッパ式の Excel）
    write_raw("x_semicolon_eu.csv", s_lines(eu_int, lambda c, i: eu_dec(c / i * 100, 2) + " %",
                                           lambda p: eu_dec(p, 1), delimiter=";"), "utf-8-sig")
    # カンマ区切りで、小数点カンマのセルを引用符で囲んだもの（"3,5%" や "8,2"）
    write_raw("x_decimal_comma_quoted.csv", s_lines(str, lambda c, i: eu_dec(c / i * 100, 2) + "%",
                                                   lambda p: eu_dec(p, 1)))
    # 空白・ノーブレークスペース・狭いノーブレークスペースの桁区切り（"1 234"）
    spaces = [" ", " ", " "]
    counter = {"n": 0}

    def space_int(n):
        counter["n"] += 1
        return f"{n:,}".replace(",", spaces[counter["n"] % 3])
    write_raw("x_space_thousands.csv", s_lines(space_int, lambda c, i: f"{c / i * 100:.2f} %", str))
    # 全角数字・全角の小数点・全角の %
    fw = str.maketrans("0123456789.%", "０１２３４５６７８９．％")
    write_raw("x_fullwidth.csv", s_lines(lambda n: str(n).translate(fw),
                                        lambda c, i: f"{c / i * 100:.2f}%".translate(fw),
                                        lambda p: str(p).translate(fw)))
    # 列ごとに表記が違う: 表示回数は "1,000"（点が小数点の桁区切り）、掲載順位は "8,0"（小数点がカンマ）
    write_raw("x_mixed_marks.csv", s_lines(lambda n: f"{n:,}", lambda c, i: f"{c / i * 100:.2f}%",
                                          lambda p: eu_dec(p, 1)))

    # --- 改行・空行・区切り ---
    base = s_lines(str, lambda c, i: f"{c / i * 100:.2f}%", str)
    write_raw("x_cr_only.csv", base.replace("\n", "\r"))
    write_raw("x_blank_lines.csv", "\r\n\r\n" + base.replace("\n", "\r\n") + ",,,,\r\n\r\n , , ,\r\n\r\n")
    write_raw("x_semicolon_point.csv", base.replace(",", ";"))

    # --- 列名 ---
    header_messy = [" Top queries　", "​Clicks ", "Ｉｍｐｒｅｓｓｉｏｎｓ", "CTR ", "　Position", "Extra", "メモ"]
    write_raw("x_header_messy.csv", s_lines(str, lambda c, i: f"{c / i * 100:.2f}%", str,
                                           header=header_messy, extra=["x", "余分な列"]))
    write_raw("x_dup_clicks.csv", "Top queries,Clicks,Clicks,Impressions,CTR,Position\n野菜,1,2,100,1%,9\n")
    write_raw("x_dup_query.csv", "Top queries,Query,Clicks,Impressions,CTR,Position\n野菜,野菜,1,100,1%,9\n")
    # CTR 列が 2 つ（値はわざと間違えておく。使わずにクリック数 / 表示回数で計算されることを確かめる）
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Top queries", "Clicks", "Impressions", "CTR", "URL CTR", "Position"])
    for q, _p, c, i, pos in S_ROWS:
        w.writerow([q, c, i, "99%", "0.99", pos])
    write_raw("x_dup_ctr.csv", buf.getvalue())
    write_raw("x_ragged.csv", "Top queries,Clicks,Impressions,CTR,Position\n野菜 宅配,10,200,5%,9\n野菜 通販,1,1,234,5%,10\n")
    write_raw("x_unterminated_quote.csv",
              'Top queries,Clicks,Impressions,CTR,Position\n野菜,10,200,5%,9\n"未完の引用,1,300,1%,10\n野菜 通販,1,300,1%,10\n')
    write_raw("x_text_after_quote.csv", 'Top queries,Clicks,Impressions,CTR,Position\n"野菜"宅配,10,200,5%,9\n')
    write_raw("x_short_row.csv", "Top queries,Clicks,Impressions,CTR,Position\n野菜 宅配,20,1000,2%,8\n野菜 通販,1,234\n")

    # --- 値の異常 ---
    write_raw("x_bad_values.csv",
              "Top queries,Clicks,Impressions,CTR,Position\n"
              "有効 A,0,300,0%,10\n"
              "ダッシュ,1,300,0.33%,—\n"
              "空欄,1,300,0.33%,\n"
              "ゼロ表示,0,0,0%,10\n"
              "負のクリック,-1,300,0%,10\n"
              "負の順位,5,500,1%,-2\n"
              "無限,inf,300,0%,10\n"
              "上位,30,300,10%,2.0\n"
              ",,,,\n\n\n")
    write_raw("x_zero_impr_bucket.csv",
              "Top queries,Clicks,Impressions,CTR,Position\n"
              + "".join(f"q{i},0,0,0%,1.{i}\n" for i in range(6)))

    # --- 文字コード ---
    ja_q = s_lines(str, lambda c, i: f"{c / i * 100:.2f}%", str, delimiter="\t", header=HEADERS["ja_q"])
    write_raw("x_utf16le_nobom.csv", ja_q, "utf-16-le")
    write_raw("x_utf16be_nobom.csv", ja_q, "utf-16-be")
    good = base.encode("utf-8")
    broken = good.replace("野菜 保存方法".encode("utf-8"), "野菜 保存".encode("utf-8") + b"\xff" + "方法".encode("utf-8"))
    write_raw("x_utf8_one_bad_byte.csv", broken)
    write_raw("x_utf8_nul.csv", good.replace("旬の野菜".encode("utf-8"), "旬の\x00野菜".encode("utf-8")))
    import zipfile
    with zipfile.ZipFile(os.path.join(DATA, "x_export.zip"), "w") as z:
        z.writestr("Queries.csv", base)
        z.writestr("Pages.csv", base)
    os.makedirs(os.path.join(DATA, "x_dir.csv"), exist_ok=True)

    # --- セルの中のカンマ・改行、CSV インジェクション ---
    write_raw("x_comma_newline.csv",
              'Top queries,Clicks,Impressions,CTR,Position\n'
              '"野菜 宅配, おすすめ",20,1000,2%,8\n'
              '"野菜\n宅配 人気",150,500,30%,11\n'
              '"野菜 ""定期便""",40,400,10%,3\n')
    write_raw("x_inject.csv",
              "Query,Page,Clicks,Impressions,CTR,Position\n"
              "=1+1,https://example.jp/a/,2,200,1%,10\n"
              "-20度 寝袋,https://example.jp/b/,2,200,1%,10\n"
              "@SUM(A1),https://example.jp/c/,2,200,1%,10\n"
              "+81 電話,+cmd|' /C calc'!A0,2,200,1%,10\n"
              "\" =空白始まり\",https://example.jp/e/,2,200,1%,10\n"
              "通常 クエリ,https://example.jp/f/,2,200,1%,10\n"
              "通常 上位,https://example.jp/top/,50,500,10%,2\n")
    write_raw("x_inject_l.csv",
              "Top queries,Clicks,Impressions,CTR,Position\n=1+1,0,200,0%,5\n-20度 寝袋,0,200,0%,5\n通常,40,200,20%,5\n")
    write_raw("x_inject_prev.csv",
              "上位のクエリ,クリック数,表示回数,CTR,掲載順位\n"
              "-20度 寝袋,100,1000,10%,3\n=cmd,100,1000,10%,3\n通常,100,1000,10%,3\n")
    write_raw("x_inject_cur.csv",
              "Top queries,Clicks,Impressions,CTR,Position\n"
              "-20度 寝袋,50,1000,5%,2.5\n通常,100,1000,10%,3\n")

    # --- low_ctr ---
    write_raw("x_one_bucket.csv",
              "Top queries,Clicks,Impressions,CTR,Position\n"
              "q1,20,1000,2%,9.0\nq2,10,500,2%,9.5\nq3,1,500,0.2%,10.0\nq4,5,250,2%,8.2\n"
              "q5,4,200,2%,8.8\nq6,0,100,0%,9.9\nq7,3,300,1%,9.0\n")
    write_raw("x_lb_rows2.csv",
              "Top queries,Clicks,Impressions,CTR,Position\ng 野菜,0,100,0%,0.4\nf 野菜,0,100,0%,0.6\nh 野菜,0,100,0%,25\n")
    write_raw("x_bench_eu.csv", "position;ctr\n1;30 %\n2;0,10\n3;4%\n6;0,01\n")
    write_raw("x_bench_pos0.csv", "position,ctr\n0,30%\n1,20%\n")

    # --- decay ---
    write_raw("x_d_keys_prev.csv",
              " Top pages ,Clicks,Impressions,CTR,Position\n"
              "https://example.jp/A/,100,1000,10%,3\n"
              "https://Example.JP/b,100,1000,10%,3\n"
              "https://example.jp/%E9%87%8E%E8%8F%9C/,100,1000,10%,3\n"
              "https://example.jp/%e3%81%82/,100,1000,10%,3\n"
              "https://example.jp/dup/,60,600,10%,2\n"
              "https://example.jp/dup/,40,400,10%,7\n"
              "https://example.jp/slash,100,1000,10%,3\n")
    write_raw("x_d_keys_cur.csv",
              "上位のページ,クリック数,表示回数,CTR,掲載順位\n"
              "https://example.jp/a/,10,1000,1%,3\n"
              "https://example.jp/b,10,1000,1%,3\n"
              "https://example.jp/野菜/,10,1000,1%,3\n"
              "https://example.jp/%E3%81%82/,10,1000,1%,3\n"
              "https://example.jp/dup/,10,1000,1%,3\n"
              "https://example.jp/slash/,10,1000,1%,3\n")
    write_raw("x_d_qcase_prev.csv", "Top queries,Clicks,Impressions,CTR,Position\niPhone ケース,100,1000,10%,3\nｎｉｋｅ,50,500,10%,3\n")
    write_raw("x_d_qcase_cur.csv", "Top queries,Clicks,Impressions,CTR,Position\niphone ケース,90,1000,9%,3\nnike,45,500,9%,3\n")
    write_raw("x_d_lang_prev.csv", "Top queries,Clicks,Impressions,CTR,Position\n野菜 宅配,100,1000,10%,3.0\n")
    write_raw("x_d_lang_cur.csv", "上位のクエリ;クリック数;表示回数;CTR;掲載順位\n野菜 宅配;50;1.000;5,0 %;3,0\n", "cp932")
    write_raw("x_d_empty_q.csv", "Top queries,Clicks,Impressions,CTR,Position\n")
    write_raw("x_cmp_en.csv",
              "Top pages,Last 3 months Clicks,Previous 3 months Clicks,Last 3 months Impressions,"
              "Previous 3 months Impressions,Last 3 months CTR,Previous 3 months CTR,Last 3 months Position,"
              "Previous 3 months Position\nhttps://example.jp/,1,2,3,4,5%,5%,1,1\n")
    write_raw("x_cmp_ja.csv",
              "上位のページ,過去 3 か月間 クリック数,前の期間 クリック数,過去 3 か月間 表示回数,前の期間 表示回数,"
              "過去 3 か月間 CTR,前の期間 CTR,過去 3 か月間 掲載順位,前の期間 掲載順位\n"
              "https://example.jp/,1,2,3,4,5%,5%,1,1\n")
    write_raw("x_ctr_only.csv", "クエリ,クリック率,表示回数,掲載順位\n野菜,1%,100,3\n")
    write_raw("x_extra_change_col.csv",
              "Top queries,Clicks,Clicks change (%),Impressions,CTR,Position\n野菜 宅配,20,-10%,1000,2%,8\n")

    # --- 掲載順位 0（2026-09-26 追加）---
    # Search Console の画面で「~」「-」の値は、ダウンロードしたファイルでは 0 になる。掲載順位は最小 1 なので 0 は値なし。
    # striking: 0 を順位として扱うと目標 CTR の母集団（3 位以内）に入り、目標 CTR が 85/900 に下がる
    write_raw("x_pos0_s.csv",
              "Top queries,Clicks,Impressions,CTR,Position\n"
              "上位 A,30,300,10%,2.0\n"
              "値なし 整数,50,100,50%,0\n"
              "値なし 小数,5,500,1%,0.0\n"
              "値なし 全角,1,100,1%,０\n"
              "負の順位,5,500,1%,-2\n"
              "候補 B,2,200,1%,10.0\n")
    # low_ctr: セミコロン区切り・小数点カンマ（"0,0"）。0 を順位として扱うと [1,2) の区間に入り、期待 CTR が 142/400 になる
    write_raw("x_pos0_l.csv",
              "Top queries;Clicks;Impressions;CTR;Position\n"
              "上位 1;10;100;10,00 %;1,5\n"
              "上位 2;2;100;2,00 %;1,8\n"
              "値なし 高CTR;90;100;90,00 %;0,0\n"
              "値なし 整数;40;100;40,00 %;0\n"
              "負の順位;1;100;1,00 %;-1,0\n")
    # decay: 前期 0 -> 今期 6.0 を pos_diff +6 の「順位低下」にしない。重複行の合算でも 0 を平均に入れない
    write_raw("x_pos0_d_prev.csv",
              "Top pages,Clicks,Impressions,CTR,Position\n"
              "https://example.jp/p0-prev/,100,1000,10%,0\n"
              "https://example.jp/p0-cur/,100,1000,10%,3.0\n"
              "https://example.jp/normal/,100,1000,10%,3.0\n"
              "https://example.jp/dup/,60,600,10%,2.0\n"
              "https://example.jp/dup/,40,400,10%,0\n")
    write_raw("x_pos0_d_cur.csv",
              "Top pages,Clicks,Impressions,CTR,Position\n"
              "https://example.jp/p0-prev/,50,600,8.33%,6.0\n"
              "https://example.jp/p0-cur/,50,1000,5%,0.0\n"
              "https://example.jp/normal/,50,1000,5%,6.0\n"
              "https://example.jp/dup/,50,1000,5%,2.0\n")


def gen_big(rows=100000):
    """10 万行のクエリ x ページの CSV を 2 つ作る（値は乱数。再現できるよう seed を固定）。"""
    import random
    paths = []
    for n, seed in (("x_big_a.csv", 1), ("x_big_b.csv", 2)):
        rnd = random.Random(seed)
        buf = io.StringIO()
        buf.write("Query,Page,Clicks,Impressions,CTR,Position\n")
        for i in range(rows):
            imp = rnd.randint(0, 5000)
            clicks = rnd.randint(0, imp // 5) if imp else 0
            ctr = f"{clicks / imp * 100:.2f}%" if imp else "0%"
            buf.write(f'クエリ {i},https://example.jp/p{i % 3000}/,{clicks},"{imp:,}",{ctr},{rnd.uniform(1, 60):.1f}\n')
        paths.append(write_raw(n, buf.getvalue(), "utf-8-sig"))
    return paths


def attack_tests(r, args):
    import ast
    import time
    sd, lc, dc = "striking_distance.py", "low_ctr.py", "decay.py"
    s_header_q = ["query"] + S_COLS
    s_common = dict(header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS, expected=EXP_S_DEFAULT)
    gen_attack()

    # --- 構文（Python 3.9）・共通部分・--help ---
    for script in (sd, lc, dc):
        path = os.path.join(args.scripts, script)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src, filename=path, feature_version=(3, 9))
            ok, detail = True, "ast.parse(feature_version=(3, 9)) 成功"
        except SyntaxError as e:
            ok, detail = False, f"SyntaxError: {e}"
        r.record(f"X Python 3.9 の文法 {script}", ok, detail)
    proc = subprocess.run([sys.executable, os.path.join(HERE, "sync_common.py"), "--check"], capture_output=True)
    r.record("X 共通部分が 3 本で同一（common_block.py と一致）", proc.returncode == 0,
             proc.stdout.decode("utf-8", errors="replace").strip())
    sanitize_help = ("-o のファイルの CSV インジェクション対策を無効にする", "標準出力には付けない",
                     "先頭の ' を除くか", "値を変えずに書く", "Excel で開くなら -o を使う")
    zero_help = "掲載順位 0 は値なし（画面の「~」「-」がエクスポートで 0 になったもの）とみなし、"
    help_expect = {
        sd: ("usage: striking_distance.py", "--min-impressions 回数", "デフォルト: 100", "--no-sanitize",
             "BOM なし", "予測ではなく", "セミコロン", "終了コード", "Data Studio（旧 Looker Studio）",
             "--min-impressions 20", "--top を付けずに出力し、impressions で並べ替えてから上位 30 件",
             zero_help + "その行を除外する")
            + sanitize_help,
        lc: ("usage: low_ctr.py", "0 より大きく 1 以下", "--no-sanitize", "BOM なし", "[1,2)", "--benchmark",
             "--max-pos 5 を指定する", "「平均順位 5 位以内」で見るなら 5", zero_help + "その行を除外する")
            + sanitize_help,
        dc: ("usage: decay.py", "季節性の影響を避けるため、前年同期との比較を推奨", "デフォルト: 30.0",
             "--no-sanitize", "BOM なし", "末尾の / の違いは別の URL", "比較表示", "原因の断定ではない",
             "匿名化されたクエリは行に出ない", zero_help + "position と pos_diff を空欄にして「順位低下」の判定に使わない")
            + sanitize_help,
    }
    for script, needles in help_expect.items():
        code, out, err = r.run(script, ["--help"])
        text = out.decode("utf-8", errors="replace")
        flat = re.sub(r"\s*\n\s*", " ", text)  # argparse が空白で折り返すので、改行と字下げを空白 1 つに戻して照合する
        missing = [s for s in needles if s not in flat]
        stale = [s for s in ("ファイルにも標準出力にも", "標準出力にも同じ") if s in flat]
        stale += ["Looker Studio（旧名なし）"] if re.search(r"(?<!旧 )Looker Studio", flat) else []
        r.record(f"X --help {script}", code == 0 and not missing and not stale and not err,
                 f"終了コード {code}" + (f"、見つからない記載: {missing}" if missing else "、必要な記載あり")
                 + (f"、古い記載: {stale}" if stale else "") + (f"、stderr: {err[:200]}" if err else ""))
    for script in (sd, lc, dc):
        with open(os.path.join(args.scripts, script), encoding="utf-8") as f:
            src = f.read()
        head = src.split("\nimport argparse", 1)[0]
        need = ["BOM なし", "--no-sanitize", "-o で書くファイルでは", "標準出力には付けない",
                "先頭の ' を除くか"]
        need += ["季節性の影響を避けるため、前年同期との比較を推奨", "匿名化されたクエリ"] if script == dc else []
        need += ["100 回以上", "--top を付けずに出力し"] if script == sd else []
        need += ["--max-pos 5 を指定する"] if script == lc else []
        need += ["Data Studio（旧 Looker Studio）"] if script in (sd, lc) else []
        need += ["掲載順位 0 は値なし（画面の「~」「-」がエクスポートで 0 になったもの。順位は最小 1）とみなし、"]
        need += ["その行を除外して件数を内訳に出す"] if script in (sd, lc) else [
            "その期間の position を空欄にする（pos_diff も空欄になり「順位低下」の判定に使わない"]
        missing = [s for s in need if s not in head]
        stale = [s for s in ("標準出力にも同じように適用", "タブ・改行") if s in src]
        stale += ["Looker Studio（旧名なし）"] if re.search(r"(?<!旧 )Looker Studio", src) else []
        r.record(f"X ヘッダーコメント {script}", not missing and not stale,
                 "必要な記載あり" if not (missing or stale) else f"見つからない: {missing}、古い記載: {stale}")

    # --- 出力のエンコーディング ---
    code, out, err = r.case("X 標準出力は BOM なしの UTF-8", sd, ["s_en_pct.csv"], **s_common,
                            checks=(("先頭が「query,」", lambda c, o, e: o.startswith(b"query,")),))
    r.case("X -o のファイルは BOM 付き（utf-8-sig）", sd, ["s_en_pct.csv", "-o", "x_out_bom.csv"],
           output_file="x_out_bom.csv", stdout_empty=True, **s_common)

    # --- 数値の表記 ---
    r.case("X セミコロン区切り・小数点カンマ・点の桁区切り（1.000 / 2,00 % / 8,0）", sd, ["x_semicolon_eu.csv"],
           stderr_has=("セミコロン区切り", "小数点がカンマの表記"), **s_common)
    r.case("X 小数点カンマを引用符で囲んだカンマ区切り（\"2,00%\" / \"8,0\"）", sd, ["x_decimal_comma_quoted.csv"],
           stderr_has=("カンマ区切り", "小数点がカンマの表記"), **s_common)
    r.case("X 空白・NBSP の桁区切り（1 000）と「2.00 %」", sd, ["x_space_thousands.csv"], **s_common)
    r.case("X 全角数字・全角の小数点と %", sd, ["x_fullwidth.csv"], **s_common)
    r.case("X 列ごとに表記が違う（\"1,000\" と \"8,0\"）", sd, ["x_mixed_marks.csv"],
           stderr_has=("混在",), **s_common)
    r.case("X セミコロン区切り（小数点は点）", sd, ["x_semicolon_point.csv"], stderr_has=("セミコロン区切り",), **s_common)

    # --- 改行・空行 ---
    r.case("X CR だけの改行", sd, ["x_cr_only.csv"], **s_common)
    r.case("X 先頭・末尾の空行とカンマだけの行", sd, ["x_blank_lines.csv"],
           stderr_has=("入力行数: 14", "空行 4 行を読み飛ばしました", "数値を解析できない 0"), **s_common)

    # --- 列名 ---
    r.case("X 列名の前後の空白・全角空白・ゼロ幅スペース・全角英字、余分な列", sd, ["x_header_messy.csv"],
           stderr_has=("impressions='Ｉｍｐｒｅｓｓｉｏｎｓ'",), **s_common)
    r.case("X 同じ列名が 2 つ（Clicks）", sd, ["x_dup_clicks.csv"], exit_code=2,
           stderr_has=("同じ項目を表す列が複数あります", "'Clicks'（2 列目）, 'Clicks'（3 列目）"))
    r.case("X 同じ項目の別名が 2 つ（Top queries と Query）", sd, ["x_dup_query.csv"], exit_code=2,
           stderr_has=("query（クエリ）", "'Top queries'（1 列目）, 'Query'（2 列目）"))
    r.case("X CTR 列が 2 つ（使わずにクリック数 / 表示回数で計算）", sd, ["x_dup_ctr.csv"],
           stderr_has=("CTR の列が複数ある",), **s_common)
    r.case("X 列数が多い行（引用符なしの 1,234）", sd, ["x_ragged.csv"], exit_code=2,
           stderr_has=("3 行目のセルの数が 6 個", "引用符で囲む"))
    r.case("X 閉じていない引用符（残りを 1 つのセルとして黙って読まない）", sd, ["x_unterminated_quote.csv"], exit_code=2,
           stderr_has=("CSV の形式が不正です", "引用符（\"）が閉じているか"))
    r.case("X 閉じた引用符の直後に文字がある", sd, ["x_text_after_quote.csv"], exit_code=2,
           stderr_has=("2 行目付近",))
    r.case("X 列数が少ない行（掲載順位なし -> 除外）", sd, ["x_short_row.csv"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS,
           expected=[("野菜 宅配", 20, 1000, 0.02, "2.00%", 8.0, "")], stderr_has=("解析できない行 1 行",))

    # --- 値の異常（—、空欄、表示回数 0、負の値、inf）---
    r.case("X 掲載順位「—」・空欄、表示回数 0、負の値、inf、カンマだけの行", sd, ["x_bad_values.csv"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS,
           expected=[("有効 A", 0, 300, 0.0, "0.00%", 10.0, 30.0)],
           stderr_has=("空か解析できない行 3 行", "負の値の行 2 行", "空行 3 行", "目標 CTR: 10.00%（掲載順位 3 以下の 1 行",
                       "除外行数: 5（数値を解析できない 3、負の値 2"))
    r.case("L 表示回数 0 だけの区間（ゼロ除算しない）", lc,
           ["x_zero_impr_bucket.csv", "--min-impressions", "0", "--baseline-min-impressions", "0"],
           header=["query"] + L_COLS, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS, expected=[],
           stderr_has=("[1,2): 空欄（表示回数が 0）", "判定しなかった行: 6 行"))
    r.case("D 表示回数 0 の行（ゼロ除算しない）", dc, ["--previous", "x_zero_impr_bucket.csv", "--current", "x_zero_impr_bucket.csv"],
           header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS, kinds=D_KINDS, expected=[])

    # --- 掲載順位 0（エクスポートで値なしが 0 になったもの。2026-09-26 追加）---
    zero_label = "掲載順位 0（エクスポートで値なしが 0 になったもの）"
    # 目標 CTR = 上位 A だけの 30 / 300 = 0.10（0 の 3 行を入れると 85 / 900）。候補 B: 200 x (0.10 - 0.01) = 18.0
    r.case("S 掲載順位 0（\"0\"・\"0.0\"・全角「０」）は除外して内訳に出す。負の値とは別に数える", sd, ["x_pos0_s.csv"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS,
           expected=[("候補 B", 2, 200, 0.01, "1.00%", 10.0, 18.0)],
           stderr_has=(f"除外: {zero_label}の行 3 行",
                       f"除外行数: 4（数値を解析できない 0、負の値 1、{zero_label} 3、キー列が空 0、正規表現 0）",
                       "目標 CTR: 10.00%（掲載順位 3 以下の 1 行", "判定に使った行数: 2"))
    # [1,2) の期待 CTR = (10 + 2) / (100 + 100) = 0.06（0 の 2 行を入れると 142 / 400）。上位 2: 100 x (0.06 - 0.02) = 4.0
    r.case("L 掲載順位 0（\"0,0\"・\"0\"）は除外して内訳に出す。[1,2) の区間に入れない", lc,
           ["x_pos0_l.csv", "--min-bucket-rows", "1"],
           header=["query"] + L_COLS, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS,
           expected=[("上位 2", 2, 100, 0.02, "2.00%", 1.8, "[1,2)", 0.06, 0.3333, 4.0)],
           stderr_has=("セミコロン区切り", "[1,2): 6.00%（2 行", f"除外: {zero_label}の行 2 行",
                       f"除外行数: 3（数値を解析できない 0、負の値 1、{zero_label} 2、キー列が空 0、正規表現 0）",
                       "判定に使った行数: 2"))
    # 前期 dup は 2.0（x600）と 0（x400）の合算。0 を平均に入れると 1.2 になる
    r.case("D 掲載順位 0 は position と pos_diff を空欄にし、「順位低下」にしない（他の判定は続ける）", dc,
           ["--previous", "x_pos0_d_prev.csv", "--current", "x_pos0_d_cur.csv"],
           header=["page"] + D_COLS, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS,
           expected=[
               ("https://example.jp/dup/", 100, 50, -50, -50.0, 1000, 1000, 0.0, 0.1, 0.05, 2.0, 2.0, 0.0,
                "CTR低下（順位・表示回数は維持）"),
               ("https://example.jp/normal/", 100, 50, -50, -50.0, 1000, 1000, 0.0, 0.1, 0.05, 3.0, 6.0, 3.0, "順位低下"),
               ("https://example.jp/p0-cur/", 100, 50, -50, -50.0, 1000, 1000, 0.0, 0.1, 0.05, 3.0, "", "",
                "CTR低下（順位・表示回数は維持）"),
               ("https://example.jp/p0-prev/", 100, 50, -50, -50.0, 1000, 600, -40.0, 0.1, 0.0833, "", 6.0, "",
                "需要減（表示回数が減少・順位は維持）"),
           ],
           stderr_has=(f"{zero_label}の行 2 行: 掲載順位を空欄（値なし）として扱います",
                       f"{zero_label}の行 1 行: 掲載順位を空欄（値なし）として扱います",
                       "そのうち掲載順位が空欄（値なし）の 1 行は、掲載順位の平均に入れていません",
                       f"前期: 入力 5 行、除外 0 行（数値を解析できない 0、負の値 0、キー列が空 0、正規表現 0）、"
                       f"{zero_label}で position を空欄にした行 2 行",
                       f"今期: 入力 4 行、除外 0 行（数値を解析できない 0、負の値 0、キー列が空 0、正規表現 0）、"
                       f"{zero_label}で position を空欄にした行 1 行",
                       "「順位低下」の判定に使っていません", "該当件数: 4",
                       "順位低下 1", "需要減（表示回数が減少・順位は維持） 1", "CTR低下（順位・表示回数は維持） 2"),
           checks=(("「順位低下」は normal/ の 1 行だけ",
                    lambda c, o, e: [row[0] for row in parse_csv_bytes(o)[1:] if row[-1] == "順位低下"]
                    == ["https://example.jp/normal/"]),))

    # --- 文字コード ---
    exp_ja = EXP_S_DEFAULT
    r.case("X BOM なし UTF-16 LE（日本語の列名・タブ区切り）", sd, ["x_utf16le_nobom.csv"],
           stderr_has=("文字コード utf-16-le", "タブ区切り"), **s_common)
    r.case("X BOM なし UTF-16 BE", sd, ["x_utf16be_nobom.csv"], stderr_has=("文字コード utf-16-be",),
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS, expected=exp_ja)
    r.case("X UTF-8 に壊れたバイトが 1 個（置き換えて読む。UTF-16 と誤判定しない）", sd, ["x_utf8_one_bad_byte.csv"],
           stderr_has=("文字コード utf-8", "不正なバイトが 1 個"), stderr_not_has=("utf-16",), **s_common)
    r.case("X NUL 文字が混じった UTF-8", sd, ["x_utf8_nul.csv"], stderr_has=("NUL 文字が 1 個",), **s_common)
    r.case("X zip を渡した（GSC のダウンロードそのまま）", sd, ["x_export.zip"], exit_code=2,
           stderr_has=("zip ファイル", "Queries.csv", "展開し", "という名前のことが多い"))
    r.case("X フォルダを渡した", sd, ["x_dir.csv"], exit_code=2, stderr_has=("フォルダ",))

    # --- セルの中のカンマ・改行 ---
    r.case("X クエリにカンマ・改行・二重引用符", sd, ["x_comma_newline.csv", "--min-impressions", "0"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS,
           expected=[("野菜 宅配, おすすめ", 20, 1000, 0.02, "2.00%", 8.0, 80.0),
                     ("野菜\n宅配 人気", 150, 500, 0.30, "30.00%", 11.0, 0.0)],
           stderr_has=("目標 CTR: 10.00%",))

    # --- CSV インジェクション対策 ---
    inj_header = ["query", "page"] + S_COLS
    inj_rows = [("=1+1", "https://example.jp/a/"), ("-20度 寝袋", "https://example.jp/b/"),
                ("@SUM(A1)", "https://example.jp/c/"), ("+81 電話", "+cmd|' /C calc'!A0"),
                ("=空白始まり", "https://example.jp/e/"), ("通常 クエリ", "https://example.jp/f/")]

    def inj_expected(sanitize):
        out = []
        for q, p in inj_rows:
            if sanitize:
                q = "'" + q if q[0] in "=+-@" else q
                p = "'" + p if p[0] in "=+-@" else p
            out.append((q, p, 2, 200, 0.01, "1.00%", 10.0, 18.0))
        return out
    inj_common = dict(header=inj_header, key_cols=["query", "page"], value_cols=S_COLS, kinds=S_KINDS)
    r.case("X CSV インジェクション対策: -o のファイル（query / page に ' を付ける）", sd,
           ["x_inject.csv", "-o", "x_inject_out.csv"], output_file="x_inject_out.csv", stdout_empty=True,
           expected=inj_expected(True), stderr_has=("セル 6 個の前に ' を付けました",), **inj_common)
    # 2026-09-26 変更: 無害化は -o のファイルだけ。標準出力は値を変えずに書き、注意だけを出す
    r.case("X CSV インジェクション対策: 標準出力には適用しない（値はそのまま、注意を出す）", sd, ["x_inject.csv"],
           expected=inj_expected(False),
           stderr_has=("先頭が = + - @ タブ CR のセルが 6 個あります", "Excel で開くなら -o でファイルに書き出して"),
           stderr_not_has=("' を付けました",),
           checks=(("標準出力に「'=」「'-」「'@」「'+」がない",
                    lambda c, o, e: not any(x in o for x in (b"'=", b"'-", b"'@", b"'+"))),
                   ("標準出力の先頭が「query,page,」（BOM なし）", lambda c, o, e: o.startswith(b"query,page,"))),
           **inj_common)
    r.case("X --no-sanitize と標準出力（値はそのまま）", sd, ["x_inject.csv", "--no-sanitize"],
           expected=inj_expected(False), stderr_not_has=("' を付けました",), **inj_common)
    r.case("X -o のファイルと標準出力で、無害化の有無だけが違う", sd, ["x_inject.csv", "-o", "x_inject_cmp.csv"],
           output_file="x_inject_cmp.csv", stdout_empty=True, expected=inj_expected(True), **inj_common,
           checks=(("ファイルの ' を除くと標準出力と同じ",
                    lambda c, o, e: [[v[1:] if v.startswith("'") else v for v in row] for row in
                                     parse_csv_bytes(open(os.path.join(DATA, "x_inject_cmp.csv"), "rb").read())]
                    == parse_csv_bytes(r.run(sd, ["x_inject.csv"])[1])),))
    r.case("X --no-sanitize で無効", sd, ["x_inject.csv", "--no-sanitize", "-o", "x_inject_raw.csv"],
           output_file="x_inject_raw.csv", expected=inj_expected(False), stderr_not_has=("' を付けました",),
           **inj_common)
    r.case("X 正規表現は無害化の前の値に当てる（^-20度 で除外できる）", sd,
           ["x_inject.csv", "--exclude-regex", "^-20度", "-o", "x_inject_ex.csv"], output_file="x_inject_ex.csv",
           expected=[e for e in inj_expected(True) if "20度" not in e[0]], stderr_has=("正規表現 1",), **inj_common)
    r.case("X decay: キーに ' を付け、負の数値（clicks_diff・pos_diff）には付けない", dc,
           ["--previous", "x_inject_prev.csv", "--current", "x_inject_cur.csv", "-o", "x_inject_decay.csv"],
           output_file="x_inject_decay.csv", header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS,
           kinds=D_KINDS,
           expected=[("'=cmd", 100, 0, -100, -100.0, 1000, 0, -100.0, 0.1, "", 3.0, "", "", "消失（今期のデータなし）"),
                     ("'-20度 寝袋", 100, 50, -50, -50.0, 1000, 1000, 0.0, 0.1, 0.05, 3.0, 2.5, -0.5,
                      "CTR低下（順位・表示回数は維持）")],
           checks=(("負の数値のセルに ' がない",
                    lambda c, o, e: b",'-" not in open(os.path.join(DATA, "x_inject_decay.csv"), "rb").read()),))
    # [4,6) の期待 CTR = 40 / 600 = 0.066667。CTR 0 の 2 行が該当し、lost_clicks は 200 x 0.066667 = 13.3333
    r.case("X low_ctr: -o のファイルではキーに ' を付ける", lc,
           ["x_inject_l.csv", "--min-bucket-rows", "1", "-o", "x_inject_l_out.csv"], output_file="x_inject_l_out.csv",
           stdout_empty=True, header=["query"] + L_COLS, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS,
           expected=[("'=1+1", 0, 200, 0.0, "0.00%", 5.0, "[4,6)", 0.066667, 0.0, 13.3333),
                     ("'-20度 寝袋", 0, 200, 0.0, "0.00%", 5.0, "[4,6)", 0.066667, 0.0, 13.3333)],
           stderr_has=("セル 2 個の前に ' を付けました",))
    r.case("X low_ctr: 標準出力ではキーに ' を付けない", lc, ["x_inject_l.csv", "--min-bucket-rows", "1"],
           header=["query"] + L_COLS, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS,
           expected=[("=1+1", 0, 200, 0.0, "0.00%", 5.0, "[4,6)", 0.066667, 0.0, 13.3333),
                     ("-20度 寝袋", 0, 200, 0.0, "0.00%", 5.0, "[4,6)", 0.066667, 0.0, 13.3333)],
           stderr_has=("セルが 2 個あります",), stderr_not_has=("' を付けました",))
    r.case("X decay: 標準出力ではキーに ' を付けない", dc,
           ["--previous", "x_inject_prev.csv", "--current", "x_inject_cur.csv"],
           header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS, kinds=D_KINDS,
           expected=[("=cmd", 100, 0, -100, -100.0, 1000, 0, -100.0, 0.1, "", 3.0, "", "", "消失（今期のデータなし）"),
                     ("-20度 寝袋", 100, 50, -50, -50.0, 1000, 1000, 0.0, 0.1, 0.05, 3.0, 2.5, -0.5,
                      "CTR低下（順位・表示回数は維持）")],
           stderr_has=("セルが 2 個あります",), stderr_not_has=("' を付けました",))

    # --- 入力を上書きしない ---
    r.case("X -o が入力ファイルと同じ", sd, ["s_en_pct.csv", "-o", "s_en_pct.csv"], exit_code=2,
           stderr_has=("入力ファイルと同じ",))
    r.case("X decay: -o が --previous と同じ", dc, ["--previous", "d_prev_ja.csv", "--current", "d_cur_ja.csv",
                                                  "-o", "d_prev_ja.csv"], exit_code=2, stderr_has=("入力ファイルと同じ",))

    # --- striking_distance.py の引数 ---
    r.case("S --min-pos > --max-pos", sd, ["s_en_pct.csv", "--min-pos", "20", "--max-pos", "8"], exit_code=2,
           stderr_has=("--min-pos（20）が --max-pos（8）より大きく",))
    r.case("S 必須列の欠落（クリック数）の終了コードとメッセージ", sd, ["x_ctr_only.csv"], exit_code=2,
           stderr_has=("clicks（クリック数）", "Clicks, Url Clicks", "'クリック率'"), stderr_not_has=("比較表示",))

    # --- low_ctr.py ---
    one_bucket = [
        ("q3", 1, 500, 0.002, "0.20%", 10.0, "[8,11)", 0.0151, 0.13, 6.5),
        ("q6", 0, 100, 0.0, "0.00%", 9.9, "[8,11)", 0.0151, 0.0, 1.5),
    ]
    l_common = dict(header=["query"] + L_COLS, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS)
    r.case("L 全行が同じ区間", lc, ["x_one_bucket.csv"], expected=one_bucket,
           stderr_has=("[8,11): 1.51%（7 行", "[1,2): 空欄（0 行で最低行数未満）"), **l_common)
    r.case("L --ratio 1（期待 CTR 未満をすべて）", lc, ["x_one_bucket.csv", "--ratio", "1"],
           expected=[one_bucket[0], ("q7", 3, 300, 0.01, "1.00%", 9.0, "[8,11)", 0.0151, 0.66, 1.5), one_bucket[1]],
           **l_common)
    r.case("L --ratio 1.5 は入力エラー", lc, ["x_one_bucket.csv", "--ratio", "1.5"], exit_code=2,
           stderr_has=("0 より大きく 1 以下",))
    r.case("L --ratio 0 は入力エラー", lc, ["x_one_bucket.csv", "--ratio", "0"], exit_code=2,
           stderr_has=("0 より大きく 1 以下",))
    r.case("L --benchmark の境界（順位 1 未満・表の範囲外）", lc,
           ["x_lb_rows2.csv", "--benchmark", "lb_bench.csv", "--max-pos", "30"],
           expected=[("g 野菜", 0, 100, 0.0, "0.00%", 0.4, "benchmark:0", 0.30, 0.0, 30.0),
                     ("f 野菜", 0, 100, 0.0, "0.00%", 0.6, "benchmark:1", 0.30, 0.0, 30.0),
                     ("h 野菜", 0, 100, 0.0, "0.00%", 25.0, "benchmark:25", 0.01, 0.0, 1.0)], **l_common)
    r.case("L --benchmark がセミコロン区切り・小数点カンマ", lc, ["lb_rows.csv", "--benchmark", "x_bench_eu.csv"],
           expected=EXP_L_BENCH, **l_common)
    r.case("L --benchmark の position 0 は入力エラー", lc, ["lb_rows.csv", "--benchmark", "x_bench_pos0.csv"],
           exit_code=2, stderr_has=("position は 1 以上の整数",))
    r.case("L キー列の欠落の終了コードとメッセージ", lc, ["missing_key.csv"], exit_code=2,
           stderr_has=("query（クエリ） または page（ページ）", "'Keyword'"))

    # --- decay.py ---
    d_common = dict(header=["page"] + D_COLS, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS)
    gone = "消失（今期のデータなし）"
    ctr_drop = "CTR低下（順位・表示回数は維持）"
    r.case("D キーの照合（パスの大文字小文字・末尾 / は別キー、%XX とホストの大文字小文字はそろえる、重複は合算）", dc,
           ["--previous", "x_d_keys_prev.csv", "--current", "x_d_keys_cur.csv"],
           expected=[
               ("https://example.jp/A/", 100, 0, -100, -100.0, 1000, 0, -100.0, 0.1, "", 3.0, "", "", gone),
               ("https://example.jp/slash", 100, 0, -100, -100.0, 1000, 0, -100.0, 0.1, "", 3.0, "", "", gone),
               ("https://example.jp/%E3%81%82/", 100, 10, -90, -90.0, 1000, 1000, 0.0, 0.1, 0.01, 3.0, 3.0, 0.0, ctr_drop),
               ("https://example.jp/b", 100, 10, -90, -90.0, 1000, 1000, 0.0, 0.1, 0.01, 3.0, 3.0, 0.0, ctr_drop),
               ("https://example.jp/dup/", 100, 10, -90, -90.0, 1000, 1000, 0.0, 0.1, 0.01, 4.0, 3.0, -1.0, ctr_drop),
               ("https://example.jp/野菜/", 100, 10, -90, -90.0, 1000, 1000, 0.0, 0.1, 0.01, 3.0, 3.0, 0.0, ctr_drop),
           ],
           stderr_has=("重複する 2 行を 1 行に合算", "結合後: 8 行（両方にある 4、前期のみ 2、今期のみ 2）",
                       "前期だけにあるキーのうち 2 件", "末尾の「/」だけが違います",
                       "前期 'https://example.jp/A/' / 今期 'https://example.jp/a/'",
                       "前期 'https://example.jp/slash' / 今期 'https://example.jp/slash/'"), **d_common)
    r.case("D クエリの大文字小文字・全角半角の違い（別キー＋注意）", dc,
           ["--previous", "x_d_qcase_prev.csv", "--current", "x_d_qcase_cur.csv"],
           header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS, kinds=D_KINDS,
           expected=[("iPhone ケース", 100, 0, -100, -100.0, 1000, 0, -100.0, 0.1, "", 3.0, "", "", gone),
                     ("ｎｉｋｅ", 50, 0, -50, -100.0, 500, 0, -100.0, 0.1, "", 3.0, "", "", gone)],
           stderr_has=("前期だけにあるキーのうち 2 件", "全角・半角"))
    r.case("D 前期が英語 UI・今期が日本語 UI（cp932・セミコロン・小数点カンマ）", dc,
           ["--previous", "x_d_lang_prev.csv", "--current", "x_d_lang_cur.csv"],
           header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS, kinds=D_KINDS,
           expected=[("野菜 宅配", 100, 50, -50, -50.0, 1000, 1000, 0.0, 0.1, 0.05, 3.0, 3.0, 0.0, ctr_drop)],
           stderr_has=("文字コード cp932", "セミコロン区切り"))
    r.case("D 前期がヘッダーのみ（0 件）", dc, ["--previous", "x_d_empty_q.csv", "--current", "x_d_lang_prev.csv"],
           header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS, kinds=D_KINDS, expected=[],
           stderr_has=("今期のみ 1", "該当件数: 0"))
    r.case("D 前期が 0 バイト", dc, ["--previous", "zero_bytes.csv", "--current", "x_d_lang_prev.csv"], exit_code=2,
           stderr_has=("ファイルが空です",))
    r.case("D 比較表示のエクスポート（英語 UI の列名）", dc, ["--previous", "x_cmp_en.csv", "--current", "d_cur_ja.csv"],
           exit_code=2, stderr_has=("必須の列が見つかりません: x_cmp_en.csv", "比較表示のまま", "期間ごとに 1 回ずつ"))
    r.case("D 比較表示のエクスポート（日本語 UI の列名）", dc, ["--previous", "d_prev_ja.csv", "--current", "x_cmp_ja.csv"],
           exit_code=2, stderr_has=("x_cmp_ja.csv", "比較表示のまま"))
    r.case("D 期間ラベルらしい余分な列（必須列はある -> 警告して続行）", dc,
           ["--previous", "x_extra_change_col.csv", "--current", "x_extra_change_col.csv"],
           header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS, kinds=D_KINDS, expected=[],
           stderr_has=("期間ラベル付きらしい列があります", "'Clicks change (%)'"))
    r.case("D キー列の欠落の終了コードとメッセージ", dc, ["--previous", "missing_key.csv", "--current", "d_cur_ja.csv"],
           exit_code=2, stderr_has=("query（クエリ） または page（ページ）",))
    r.case("D --min-drop-pct 150 は入力エラー", dc,
           ["--previous", "d_prev_ja.csv", "--current", "d_cur_ja.csv", "--min-drop-pct", "150"], exit_code=2,
           stderr_has=("0〜100",))
    r.case("D --pos-threshold 0 は入力エラー", dc,
           ["--previous", "d_prev_ja.csv", "--current", "d_cur_ja.csv", "--pos-threshold", "0"], exit_code=2,
           stderr_has=("0 より大きい値",))

    # --- 10 万行の処理時間 ---
    big_a, big_b = gen_big()
    for script, argv in ((sd, [big_a]), (lc, [big_a]), (dc, ["--previous", big_a, "--current", big_b])):
        start = time.time()
        code, out, err = r.run(script, argv + ["-o", os.path.join(DATA, "x_big_out.csv")])
        elapsed = time.time() - start
        ok = code == 0 and elapsed < 30 and ("入力行数: 100000" in err or "入力 100000 行" in err)
        r.record(f"X 10 万行の処理時間 {script}", ok, f"終了コード {code}、{elapsed:.2f} 秒（上限 30 秒）")
    for name in ("x_big_a.csv", "x_big_b.csv", "x_big_out.csv"):
        path = os.path.join(DATA, name)
        if os.path.exists(path):
            os.remove(path)

    # --- スキルのフォルダに __pycache__ がない ---
    found = [os.path.join(root, d) for root, dirs, _files in os.walk(SKILL_DIR) for d in dirs if d == "__pycache__"]
    r.record("X スキルのフォルダに __pycache__ がない", not found, "なし" if not found else ", ".join(found))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--scripts", default=DEFAULT_SCRIPTS)
    ap.add_argument("--label", default="default")
    args = ap.parse_args()
    global SKILL_DIR
    args.scripts = os.path.abspath(os.path.expanduser(args.scripts))
    SKILL_DIR = os.path.dirname(args.scripts)
    os.environ["SEO_OPERATOR_DIR"] = SKILL_DIR  # sync_common.py --check も同じスクリプトを見る
    if os.sep in args.python:
        args.python = os.path.abspath(args.python)
    gen_all()
    r = Runner(args.python, args.scripts)

    # --- 構文と --help ---
    for script in ("striking_distance.py", "low_ctr.py", "decay.py"):
        # py_compile は __pycache__ をスキルのフォルダに作るので、compile() で構文だけ確認する
        code_check = ("import sys; p = sys.argv[1]; "
                      "compile(open(p, encoding='utf-8').read(), p, 'exec'); print(sys.version.split()[0])")
        proc = subprocess.run([args.python, "-c", code_check, os.path.join(args.scripts, script)],
                              capture_output=True)
        r.record(f"構文チェック {script}", proc.returncode == 0,
                 (proc.stderr.decode()[:200] or "Python " + proc.stdout.decode().strip() + " で compile() 成功"))
    r.case("help striking_distance", "striking_distance.py", ["--help"],
           stderr_has=(), exit_code=0)
    code, out, _ = r.run("striking_distance.py", ["--help"])
    text = out.decode()
    r.record("help striking_distance 内容", all(s in text for s in ("使用例", "予測ではなく", "--target-max-pos", "終了コード")),
             "使用例・予測ではない旨・引数・終了コードの記載を確認")
    code, out, _ = r.run("low_ctr.py", ["--help"])
    text = out.decode()
    r.record("help low_ctr 内容", code == 0 and all(s in text for s in ("使用例", "--benchmark", "[1,2)", "自サイトの実績")),
             "使用例・区間・--benchmark・自サイト実績の記載を確認")
    code, out, _ = r.run("decay.py", ["--help"])
    text = out.decode()
    r.record("help decay 内容", code == 0 and all(s in text for s in ("使用例", "比較表示", "前年同期", "原因の断定ではない")),
             "比較表示を受け付けない旨・前年同期推奨・断定ではない旨を確認")

    # --- striking_distance.py ---
    s_header_q = ["query"] + S_COLS
    s_header_p = ["page"] + S_COLS
    sd = "striking_distance.py"
    common = dict(header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS, expected=EXP_S_DEFAULT)
    r.case("S 英語列名・CTR「%」文字列", sd, ["s_en_pct.csv"],
           stderr_has=("% 付きの値 14 行は百分率", "目標 CTR: 22.22%", "該当件数: 5", "表示回数 100 以上"), **common)
    r.case("S --min-impressions 50（旧デフォルト。下限 50 ちょうどを含む）", sd, ["s_en_pct.csv", "--min-impressions", "50"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS, expected=EXP_S_MIN50,
           stderr_has=("該当件数: 7",))
    r.case("S 日本語列名・CTR 比率の数値", sd, ["s_ja_ratio.csv"],
           stderr_has=("比率とみなす", "query='上位のクエリ'", "position='掲載順位'"), **common)
    r.case("S 日本語列名・CTR 百分率の数値", sd, ["s_ja_pctnum.csv"],
           stderr_has=("百分率とみなして 100 で割る",), **common)
    r.case("S CTR 列なし", sd, ["s_en_noctr.csv"], stderr_has=("CTR 列がないため",), **common)
    r.case("S cp932", sd, ["s_ja_cp932.csv"], stderr_has=("文字コード cp932",), **common)
    r.case("S 桁区切り・全角数字・空白・解析不能行", sd, ["s_en_thousands.csv"],
           stderr_has=("入力行数: 15", "数値を解析できない 1"), **common)
    r.case("S UTF-16・タブ区切り", sd, ["s_en_utf16_tab.csv"], stderr_has=("文字コード utf-16", "タブ区切り"), **common)
    exp_pages = [(S_PAGE[e[0]],) + e[1:] for e in EXP_S_DEFAULT]
    r.case("S ページ版（Top pages）", sd, ["s_en_pages.csv"], header=s_header_p, key_cols=["page"],
           value_cols=S_COLS, kinds=S_KINDS, expected=exp_pages)
    r.case("S ページ版（上位のページ）", sd, ["s_ja_pages.csv"], header=s_header_p, key_cols=["page"],
           value_cols=S_COLS, kinds=S_KINDS, expected=exp_pages)
    r.case("S クエリ x ページ（両列を出力）", sd, ["s_api.csv"], header=["query", "page"] + S_COLS,
           key_cols=["query", "page"], value_cols=S_COLS, kinds=S_KINDS, expected=EXP_S_API)
    exp_api_page = [(e[1], e[0]) + e[2:] for e in EXP_S_API]
    r.case("S クエリ x ページ --key page", sd, ["s_api.csv", "--key", "page"], header=["page", "query"] + S_COLS,
           key_cols=["page", "query"], value_cols=S_COLS, kinds=S_KINDS, expected=exp_api_page)
    r.case("S --exclude-regex", sd, ["s_en_pct.csv", "--exclude-regex", "EXAMPLE"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS, expected=EXP_S_EXCLUDE,
           stderr_has=("正規表現 2", "目標 CTR: 12.50%"))
    for f in ("s_out_top3.csv",):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            os.remove(p)
    r.case("S --top 3 と -o（BOM 付きファイル）", sd, ["s_en_pct.csv", "--top", "3", "-o", "s_out_top3.csv"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS, expected=EXP_S_DEFAULT[:3],
           output_file="s_out_top3.csv", stdout_empty=True)
    r.case("S 目標 CTR の対象行なし（空欄・表示回数順）", sd, ["s_en_pct.csv", "--target-max-pos", "1"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS, expected=EXP_S_NO_TARGET,
           stderr_has=("行がないため計算できません",))
    r.case("S 目標 CTR の表示回数不足（空欄）", sd, ["s_small_target.csv"],
           header=s_header_q, key_cols=["query"], value_cols=S_COLS, kinds=S_KINDS,
           expected=[("小さい 候補", 1, 100, 0.01, "1.00%", 10.0, "")], stderr_has=("100 未満",))
    r.case("S 必須列の欠落（掲載順位）", sd, ["s_missing_pos.csv"], exit_code=2,
           stderr_has=("position（掲載順位）", "Position, Average position", "'上位のクエリ'", "受け付ける列名"))
    r.case("S キー列の欠落", sd, ["missing_key.csv"], exit_code=2,
           stderr_has=("query（クエリ） または page（ページ）", "Top queries", "上位のページ", "'Keyword'"))
    r.case("S 比較表示のエクスポート", sd, ["comparison.csv"], exit_code=2, stderr_has=("比較表示",))
    r.case("S ヘッダーのみの空 CSV", sd, ["s_empty.csv"], header=s_header_q, key_cols=["query"],
           value_cols=S_COLS, kinds=S_KINDS, expected=[], stderr_has=("該当件数: 0",))
    r.case("S 0 バイトのファイル", sd, ["zero_bytes.csv"], exit_code=2, stderr_has=("ファイルが空です",))
    r.case("S ファイルなし", sd, ["no_such_file.csv"], exit_code=2, stderr_has=("ファイルが見つかりません",))
    r.case("S 不正な正規表現", sd, ["s_en_pct.csv", "--exclude-regex", "("], exit_code=2,
           stderr_has=("正規表現が不正です",))

    # --- low_ctr.py ---
    lc = "low_ctr.py"
    l_header_q = ["query"] + L_COLS
    lcommon = dict(header=l_header_q, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS, expected=EXP_L_DEFAULT)
    l_stderr = ("判定しなかった行: 4 行", "[3,4): 空欄（4 行で最低行数未満）", "[1,2): 25.00%", "該当件数: 6")
    r.case("L 英語列名・CTR「%」文字列", lc, ["l_en_pct.csv"], stderr_has=l_stderr, **lcommon)
    r.case("L 日本語列名・CTR 比率の数値", lc, ["l_ja_ratio.csv"], stderr_has=l_stderr + ("比率とみなす",), **lcommon)
    r.case("L 日本語列名・CTR 百分率の数値", lc, ["l_ja_pctnum.csv"],
           stderr_has=l_stderr + ("百分率とみなして 100 で割る",), **lcommon)
    r.case("L CTR 列なし", lc, ["l_en_noctr.csv"], stderr_has=l_stderr, **lcommon)
    r.case("L cp932", lc, ["l_ja_cp932.csv"], stderr_has=l_stderr, **lcommon)
    r.case("L 桁区切り・全角数字・空白・解析不能行", lc, ["l_en_thousands.csv"],
           stderr_has=l_stderr + ("数値を解析できない 1",), **lcommon)
    r.case("L UTF-16・タブ区切り", lc, ["l_en_utf16_tab.csv"], stderr_has=l_stderr, **lcommon)
    exp_l_pages = [(L_PAGE[e[0]],) + e[1:] for e in EXP_L_DEFAULT]
    r.case("L ページ版（Top pages）", lc, ["l_en_pages.csv"], header=["page"] + L_COLS, key_cols=["page"],
           value_cols=L_COLS, kinds=L_KINDS, expected=exp_l_pages)
    r.case("L ページ版（上位のページ）", lc, ["l_ja_pages.csv"], header=["page"] + L_COLS, key_cols=["page"],
           value_cols=L_COLS, kinds=L_KINDS, expected=exp_l_pages)
    exp_l_api = [(e[0], L_PAGE[e[0]]) + e[1:] for e in EXP_L_DEFAULT]
    r.case("L クエリ x ページ（両列を出力）", lc, ["l_api.csv"], header=["query", "page"] + L_COLS,
           key_cols=["query", "page"], value_cols=L_COLS, kinds=L_KINDS, expected=exp_l_api)
    r.case("L --exclude-regex（除外後のデータで期待 CTR）", lc, ["l_en_pct.csv", "--exclude-regex", "example"],
           header=l_header_q, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS, expected=EXP_L_EXCLUDE,
           stderr_has=("[1,2): 13.33%（5 行", "正規表現 1"))
    r.case("L --min-bucket-rows 4", lc, ["l_en_pct.csv", "--min-bucket-rows", "4"],
           header=l_header_q, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS, expected=EXP_L_BUCKET4)
    r.case("L --baseline-min-impressions 1", lc, ["l_en_pct.csv", "--baseline-min-impressions", "1"],
           header=l_header_q, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS, expected=EXP_L_BASELINE1)
    r.case("L --benchmark（四捨五入・補間・範囲外）", lc, ["lb_rows.csv", "--benchmark", "lb_bench.csv"],
           header=l_header_q, key_cols=["query"], value_cols=L_COLS, kinds=L_KINDS, expected=EXP_L_BENCH)
    r.case("L --benchmark の不正値", lc, ["lb_rows.csv", "--benchmark", "lb_bench_bad.csv"], exit_code=2,
           stderr_has=("% を付けて",))
    r.case("L 必須列の欠落", lc, ["l_missing_pos.csv"], exit_code=2, stderr_has=("position（掲載順位）",))
    r.case("L ヘッダーのみの空 CSV", lc, ["l_empty.csv"], header=l_header_q, key_cols=["query"],
           value_cols=L_COLS, kinds=L_KINDS, expected=[], stderr_has=("該当件数: 0",))

    # --- decay.py ---
    dc = "decay.py"
    d_header = ["page"] + D_COLS
    dcommon = dict(header=d_header, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS, expected=EXP_D_DEFAULT)
    code, out, err = r.case("D 5 種類の diagnosis（日本語列名・「%」文字列）", dc,
                            ["--previous", "d_prev_ja.csv", "--current", "d_cur_ja.csv"],
                            stderr_has=("該当件数: 6", "消失（今期のデータなし） 1", "順位低下 1", "複合要因 1",
                                        "減少率 30% 以上"),
                            **dcommon)
    labels = {row[-1] for row in parse_csv_bytes(out)[1:]} if out else set()
    want = {"消失（今期のデータなし）", "順位低下", "需要減（表示回数が減少・順位は維持）",
            "CTR低下（順位・表示回数は維持）", "複合要因"}
    r.record("D diagnosis が 5 種類すべて出る", labels == want, f"出現したラベル: {sorted(labels)}")
    r.case("D --min-drop-pct 20（旧デフォルト。減少率 20% ちょうど・順位 +2.0 の境界）", dc,
           ["--previous", "d_prev_ja.csv", "--current", "d_cur_ja.csv", "--min-drop-pct", "20"],
           header=d_header, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS, expected=EXP_D_DROP20,
           stderr_has=("該当件数: 7", "順位低下 2"))
    r.case("D 形式混在（英語・比率・桁区切り / 日本語・百分率の数値・cp932）", dc,
           ["--previous", "d_prev_en_ratio_thousands.csv", "--current", "d_cur_ja_pctnum_cp932.csv"],
           stderr_has=("文字コード cp932", "比率とみなす", "百分率とみなして 100 で割る"), **dcommon)
    r.case("D --exclude-regex", dc, ["--previous", "d_prev_ja.csv", "--current", "d_cur_ja.csv",
                                     "--exclude-regex", "juice"],
           header=d_header, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS, expected=EXP_D_EXCLUDE)
    r.case("D キー列の種類が違う（page と query）", dc, ["--previous", "d_prev_ja.csv", "--current", "s_en_pct.csv"],
           exit_code=2, stderr_has=("キー列の種類が違います",))
    r.case("D 今期がヘッダーのみ（すべて消失）", dc, ["--previous", "d_prev_ja.csv", "--current", "d_empty_pages.csv"],
           header=d_header, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS, expected=EXP_D_EMPTY_CUR)
    r.case("D 両方ヘッダーのみ（0 件）", dc, ["--previous", "d_empty_pages.csv", "--current", "d_empty_pages.csv"],
           header=d_header, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS, expected=[],
           stderr_has=("該当件数: 0", "同じ内容のファイル"))
    r.case("D クエリ x ページ（組み合わせで結合）", dc, ["--previous", "d_api_prev.csv", "--current", "d_api_cur.csv"],
           header=["query", "page"] + D_COLS, key_cols=["query", "page"], value_cols=D_COLS, kinds=D_KINDS,
           expected=EXP_D_API)
    r.case("D 重複キーの合算（クエリ x ページ と クエリのみ）", dc,
           ["--previous", "d_agg_prev.csv", "--current", "d_agg_cur.csv"],
           header=["query"] + D_COLS, key_cols=["query"], value_cols=D_COLS, kinds=D_KINDS, expected=EXP_D_AGG,
           stderr_has=("重複する 2 行を 1 行に合算しました", "page 列は結合に使わず"))
    r.case("D 必須列の欠落", dc, ["--previous", "d_missing_impr.csv", "--current", "d_cur_ja.csv"], exit_code=2,
           stderr_has=("impressions（表示回数）", "Impressions, 表示回数"))
    r.case("D --top 2", dc, ["--previous", "d_prev_ja.csv", "--current", "d_cur_ja.csv", "--top", "2"],
           header=d_header, key_cols=["page"], value_cols=D_COLS, kinds=D_KINDS, expected=EXP_D_DEFAULT[:2])

    attack_tests(r, args)

    n_fail = sum(1 for x in r.results if x["result"] == "fail")
    print(f"\n合計 {len(r.results)} 件、失敗 {n_fail} 件（python: {args.python}）")
    with open(os.path.join(HERE, f"results_{args.label}.json"), "w", encoding="utf-8") as f:
        json.dump(r.results, f, ensure_ascii=False, indent=2)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
