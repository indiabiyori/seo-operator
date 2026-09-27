#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pandas>=2.3,<4",
# ]
# ///
"""
low_ctr.py - 掲載順位のわりに CTR が低いクエリ（またはページ）を見つける

目的:
  Search Console の検索パフォーマンスのエクスポートから、同じくらいの掲載順位の行と比べて
  CTR が低いクエリまたはページを抽出する。title・meta description の改善候補を選ぶために使う。

入力:
  Search Console のエクスポート CSV。UI からダウンロードした zip の中のクエリの表・ページの表
  （クエリ.csv / Queries.csv、ページ.csv / Pages.csv という名前のことが多い）のほか、
  Search Console API・Data Studio（旧 Looker Studio）・スプレッドシート経由の CSV も読める。
  - 文字コード: BOM があればそれに従う。なければ UTF-8 → cp932 の順に試す。BOM なしの UTF-16 も NUL バイトの
    位置で見分ける。UTF-8 として壊れたバイトが少しだけある場合は置き換えて読み、標準エラー出力に警告を出す。
  - 区切り文字: カンマ・タブ・セミコロンのうち、ヘッダー行で既知の列名が最も多く見つかるものを使う。
    すべてのセルが空の行は読み飛ばす。ヘッダーより値の多い行があれば入力エラーにする（列のずれを防ぐため）。
  - 列名は英語・日本語のどちらの表記にも対応する（例: Top queries / 上位のクエリ、Clicks / クリック数、
    Impressions / 表示回数、CTR、Position / 掲載順位）。受け付ける列名の一覧はエラー時に表示する。
    同じ項目を表す列が 2 つ以上あると入力エラーにする（CTR だけは列を使わずクリック数 / 表示回数で計算する）。
  - 必須列: クエリ列またはページ列、クリック数、表示回数、掲載順位。
    CTR 列はなくてもよい（その場合はクリック数 / 表示回数で計算する）。
  - CTR は「3.5%」形式の文字列、比率（0.035）、百分率の数値（3.5）のどれでもよい。
    数値だけの列は、クリック数 / 表示回数と照合して比率か百分率かを自動で判定する（--ctr-unit で指定も可）。
  - 数値の桁区切り（"1,234"、"1 234"）、全角数字を処理する。小数点がカンマの表記（"3,5%"、"8,2"、"1.234"）は
    列の値から判定する（掲載順位・CTR の列の「数字,数字」は小数、表示回数・クリック数の列の「1.234」は桁区切り）。
  - 空・解析できない・負の値のクリック数・表示回数・掲載順位を含む行は除外し、件数を標準エラー出力に出す。
  - 掲載順位 0 は値なし（画面の「~」「-」がエクスポートで 0 になったもの。順位は最小 1）とみなし、その行を除外して件数を内訳に出す。
  - 任意で --benchmark に position,ctr の 2 列の CSV を渡せる（下記）。

期待 CTR:
  デフォルトでは、同じ CSV の自サイトの実績から作る。外部のベンチマーク値は使わない。
  1. 掲載順位を次の区間に分ける: [1,2) [2,3) [3,4) [4,6) [6,8) [8,11) [11,16) [16,21) [21,31) [31,∞)
  2. 表示回数が --baseline-min-impressions 以上の行について、区間ごとに
     「合計クリック数 / 合計表示回数」を求め、その区間の期待 CTR とする。
  3. 行数が --min-bucket-rows 未満の区間は期待 CTR を空欄にし、その区間の行は抽出しない（件数を標準エラー出力に出す）。
  --include-regex / --exclude-regex を適用したあとのデータで計算する。ブランド名クエリは CTR が高くなりやすく、
  除外しないと期待 CTR が高く出る。
  --benchmark を指定すると、自サイトの実績の代わりにその表の値を使う。各行の掲載順位を四捨五入した
  整数で表を引き、表の範囲外は端の値、表の途中で抜けている順位は前後の値の線形補間を使う。

抽出条件:
  掲載順位 <= --max-pos、かつ 表示回数 >= --min-impressions、かつ CTR < 期待 CTR × --ratio
  --max-pos のデフォルトは 10。references/10-gsc-growth.md の手順（平均順位 5 位以内のページ）で見るなら、
  ページの CSV に --max-pos 5 を指定する。
  --ratio は 0 より大きく 1 以下（1 より大きいと期待 CTR を上回る行まで拾うため入力エラーにする）。

出力:
  CSV。-o を指定すればそのファイルへ UTF-8（BOM 付き。Excel で開く想定）、なければ標準出力へ UTF-8（BOM なし）で書く。
  列: query または page、（クエリ × ページの CSV ではもう一方の列）、
      clicks, impressions, ctr, ctr_pct, position, bucket, expected_ctr, ctr_vs_expected, lost_clicks
  - ctr と expected_ctr は比率（小数第 4 位まで）、ctr_pct は百分率表記（例 3.52%）。
  - bucket は掲載順位の区間（--benchmark 指定時は「benchmark:引いた順位」）。
  - ctr_vs_expected = ctr / expected_ctr（0.4 なら期待 CTR の 4 割）。
  - lost_clicks = 表示回数 × (期待 CTR - CTR)。期待どおりの CTR だった場合との差の目安で、予測ではない。
  - 並び順は lost_clicks の降順。
  - CSV インジェクション対策として、-o で書くファイルでは、query / page 列で先頭が = + - @（またはタブ・CR）の
    セルの前に ' を付ける。標準出力には付けない（Claude や他のプログラムが読む経路のため）。Excel で開くなら -o を使う。
    「-20度 寝袋」のような - で始まる正当なクエリにも付くので、-o のファイルを pandas などで読むときは先頭の ' を除くか、
    --no-sanitize で出し直す。数値の列には付けない。
  - サマリー（入力行数、除外行数、区間ごとの期待 CTR、該当件数、使った閾値、CTR の単位判定）は標準エラー出力に出す。

使い方の例:
  python3 low_ctr.py Queries.csv -o low_ctr.csv
  python3 low_ctr.py クエリ.csv --exclude-regex "example|エグザンプル" --top 30 -o low_ctr.csv
  python3 low_ctr.py ページ.csv --max-pos 5 -o low_ctr_pages.csv   # 平均順位 5 位以内のページ（10-gsc-growth.md の手順）
  python3 low_ctr.py Queries.csv --ratio 0.6 --benchmark my_ctr_curve.csv

制約・注意点:
  - 期待 CTR は自サイトの平均的な実績であり、達成できる目標値ではない。
  - CTR が低い原因は title・meta description だけではない。検索結果に広告・動画・画像などの枠が多い、
    検索意図とページの内容がずれている、ナビゲーショナルなクエリ（他社名など）である、といった場合も
    CTR は下がる。実際の検索結果を見て判断すること。
  - 区間の行数が少ないと期待 CTR は不安定になる。--min-bucket-rows と --baseline-min-impressions で調整する。
  - --benchmark の値は利用者が用意する。出典を確認できる値か、自サイトの過去の実績を使うこと。
  - Search Console の UI からのエクスポートは最大 1,000 行である。
  - 依存パッケージは pandas だけ（Python 3.9 以上、pandas 2.x / 3.x）。
  - 終了コード: 0 = 正常終了（該当 0 件でも 0）、2 = 入力エラー（ファイルがない、必須列がない、引数が不正など）。
"""

import argparse
import bisect
import codecs
import csv
import io
import math
import os
import re
import shlex
import sys
import textwrap
import unicodedata
import zipfile

# パッケージがなくても --help を表示できるように、ここでは終了しない。確認は main() で parse_args の後に行う
try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None


# ---------------------------------------------------------------------------
# 共通部分（striking_distance.py / low_ctr.py / decay.py で同じコード。単体で動かすためにコピーしている）
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_INPUT_ERROR = 2

COLUMN_ALIASES = (
    ("query", ("Top queries", "Query", "Queries", "Search query",
               "上位のクエリ", "クエリ", "検索クエリ")),
    ("page", ("Top pages", "Page", "Pages", "Landing Page", "URL", "Address",
              "上位のページ", "ページ", "ランディング ページ", "ランディングページ")),
    ("clicks", ("Clicks", "Url Clicks", "URL Clicks", "クリック数", "クリック")),
    ("impressions", ("Impressions", "表示回数", "インプレッション", "インプレッション数")),
    ("ctr", ("CTR", "URL CTR", "Site CTR", "クリック率")),
    ("position", ("Position", "Average position", "Avg. position", "Average Position",
                  "掲載順位", "平均掲載順位")),
)
ALIAS_MAP = dict(COLUMN_ALIASES)
FIELD_LABELS = {
    "query": "クエリ",
    "page": "ページ",
    "clicks": "クリック数",
    "impressions": "表示回数",
    "ctr": "CTR",
    "position": "掲載順位",
}
REQUIRED_METRICS = ("clicks", "impressions", "position")
NUMERIC_FIELDS = ("clicks", "impressions", "ctr", "position")
METRIC_FIELDS = NUMERIC_FIELDS
DELIMITERS = ((",", "カンマ"), ("\t", "タブ"), (";", "セミコロン"))

# Search Console の画面で「~」「-」と表示される値は、ダウンロードしたファイルでは 0 になる。
# 掲載順位は最小 1 なので、掲載順位 0 は「値なし」とみなす（負の値とは別に数える）
ZERO_POSITION_LABEL = "掲載順位 0（エクスポートで値なしが 0 になったもの）"
ZERO_POSITION_MODES = ("exclude", "missing")

# CSV インジェクション対策: 表計算ソフトが数式として解釈しうる先頭の文字（OWASP の推奨に合わせた）
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
TEXT_OUTPUT_COLUMNS = ("query", "page")

# 列名の照合で無視する見えない文字（BOM、ゼロ幅スペースなど）
INVISIBLE_CHARS = dict.fromkeys((0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060), None)

# 比較表示のままのエクスポートで、指標名の前後に付く期間ラベルらしい語
PERIOD_LABEL_RE = re.compile(
    r"[0-9]|last|previous|prev|current|compare|comparison|\bvs\b|change|diff|"
    r"期間|前期|今期|当期|前年|昨年|過去|直近|前の|今の|日間|か月|ヶ月|カ月|週間|比較|差分|変化|増減")

# 数値の表記（小数点がカンマか点か）の判定に使うパターン
EU_NUMBER_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})+,\d+")      # 1.234,5
US_NUMBER_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+\.\d+")      # 1,234.5
DOT_GROUPED_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})+")        # 1.234（件数の列では桁区切り）
COMMA_GROUPED_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+")       # 1,234（件数の列では桁区切り）
DECIMAL_COMMA_RE = re.compile(r"-?\d*,\d+")                  # 3,5（掲載順位・CTR の列では小数）
DECIMAL_POINT_RE = re.compile(r"-?\d*\.\d+")                 # 3.5


class InputError(Exception):
    """入力エラー。main() で受け取り、終了コード 2 で終了する。"""


def log(message=""):
    """進捗・サマリーを標準エラー出力に書く。"""
    print(message, file=sys.stderr)


def setup_stderr():
    """表示できない文字があっても止まらないようにする。"""
    try:
        sys.stderr.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


def command_line(parts):
    """表示用のコマンド行を作る。コピーしてそのまま実行できるように引用する（Windows では空白を含む語だけを " で囲む）。"""
    if os.name == "nt":
        return " ".join(f'"{p}"' if (not p or " " in p) else p for p in parts)
    return shlex.join(parts)


def missing_packages(packages, argv=None):
    """必要なパッケージがないときに、用意の方法を表示して終了コード 2 を返す。

    import に失敗した時点で終了すると --help も表示できないため、main() が parse_args の後に呼ぶ。
    """
    script = os.path.abspath(__file__)
    requirements = os.path.join(os.path.dirname(os.path.dirname(script)), "requirements.txt")
    args = list(sys.argv[1:] if argv is None else argv)
    log(f"エラー: 必要なパッケージが見つかりません（{', '.join(packages)}）。")
    log("次のどちらかの方法で実行してください。")
    log("  uv を使う場合（必要なパッケージを自動で入れて実行します）:")
    log("    uv run " + command_line([script] + args))
    log("  pip を使う場合（仮想環境を作って有効にし、パッケージを入れてから、もう一度実行します）:")
    log("    pip install -r " + command_line([requirements]))
    return EXIT_INPUT_ERROR


def normalize_header(name):
    """列名を照合用に正規化する（BOM・ゼロ幅文字・前後の空白・全角空白を除き、英字を小文字にする）。"""
    text = unicodedata.normalize("NFKC", str(name)).translate(INVISIBLE_CHARS)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def zip_message(path):
    """zip（または .xlsx）が渡されたときのメッセージ。"""
    names = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
    except (zipfile.BadZipFile, OSError):
        pass
    lines = [f"zip ファイル（または Excel の .xlsx）のようです: {path}"]
    if names:
        lines.append("  zip の中の CSV: " + ", ".join(names[:10]) + (" ほか" if len(names) > 10 else ""))
    lines.append(
        "  対処: Search Console からダウンロードした zip は展開し、中のクエリの表かページの表の CSV"
        "（クエリ.csv / Queries.csv、ページ.csv / Pages.csv という名前のことが多い）を指定してください。"
        "Excel 形式で保存したファイルは CSV で保存し直してください。")
    return "\n".join(lines)


def guess_utf16_without_bom(data):
    """BOM のない UTF-16 を NUL バイトの位置から推定する。該当しなければ None。"""
    sample = data[:65536]
    half = len(sample) // 2
    if half < 2:
        return None
    even_nuls = sample[0::2].count(0)
    odd_nuls = sample[1::2].count(0)
    if odd_nuls >= max(2, half // 20) and odd_nuls > 4 * even_nuls:
        return "utf-16-le"
    if even_nuls >= max(2, half // 20) and even_nuls > 4 * odd_nuls:
        return "utf-16-be"
    return None


def read_text(path):
    """ファイルを読み、文字コードを判定して (テキスト, 文字コード名, 警告のリスト) を返す。

    BOM があればそれに従う（UTF-8 / UTF-16）。BOM がなければ NUL バイトの位置で BOM なしの UTF-16 を見分け、
    それ以外は UTF-8 → cp932 の順に試す。UTF-8 としてほぼ正しく、壊れたバイトが少しだけある場合は
    そのバイトを置き換えて読み、標準エラー出力に警告を出す（cp932 として読むと全体が文字化けするため）。
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        raise InputError(f"ファイルが見つかりません: {path}\n  対処: パスとファイル名を確認してください。")
    except IsADirectoryError:
        raise InputError(f"ファイルではなくフォルダが指定されています: {path}")
    except OSError as e:
        raise InputError(f"ファイルを読み込めません: {path}（{e}）")
    if data.startswith(b"PK\x03\x04"):
        raise InputError(zip_message(path))

    undecodable = InputError(
        f"文字コードを判定できません: {path}\n"
        "  対処: UTF-8、cp932（Shift_JIS）、UTF-16 のいずれかで保存し直してください。")
    text = None
    encoding = None
    warnings = []
    if data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            text = data.decode(encoding, errors="replace")
            warnings.append(f"警告: UTF-8 として不正なバイトが {text.count(chr(0xFFFD))} 個あり、"
                            "置き換えて読みました（該当する文字は記号に置き換わります）。")
    elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            raise undecodable
    else:
        utf16 = guess_utf16_without_bom(data)
        if utf16:
            encoding = utf16
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                raise undecodable
        else:
            try:
                text = data.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                replaced = data.decode("utf-8", errors="replace")
                n_bad = replaced.count("�")
                n_ok = sum(1 for ch in replaced if ord(ch) > 127) - n_bad
                if n_ok >= 10 * n_bad:
                    text, encoding = replaced, "utf-8"
                else:
                    try:
                        text = data.decode("cp932")
                        encoding = "cp932"
                    except UnicodeDecodeError:
                        if n_bad <= max(3, n_ok // 10):
                            text, encoding = replaced, "utf-8"
                        else:
                            raise undecodable
                if encoding == "utf-8":
                    warnings.append(f"警告: UTF-8 として不正なバイトが {n_bad} 個あり、置き換えて読みました"
                                    "（該当する文字は記号に置き換わります）。")
    if "\x00" in text:
        warnings.append(f"警告: NUL 文字が {text.count(chr(0))} 個あり、取り除いて読みました。")
        text = text.replace("\x00", "")
    return text, encoding, warnings


def first_record(text, delimiter):
    """空行を飛ばして最初の行（ヘッダー行）を返す。"""
    try:
        for record in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter):
            if any(cell.strip() for cell in record):
                return record
    except csv.Error:
        return []
    return []


def count_known_headers(header):
    known = {normalize_header(a) for _field, aliases in COLUMN_ALIASES for a in aliases}
    return sum(1 for name in header if normalize_header(name) in known)


def parse_csv_text(text, path):
    """CSV を読み、(ヘッダー, データ行のリスト, 区切り文字の名前, 読み飛ばした空行の数) を返す。

    区切り文字はカンマ・タブ・セミコロンのうち、ヘッダー行で既知の列名が最も多く見つかるものを使う
    （同数なら列の数が多いもの、それも同じならカンマ → タブ → セミコロンの順）。
    すべてのセルが空の行は読み飛ばす。ヘッダーより列が多い行は、余分なセルが空なら切り捨て、
    値があれば入力エラーにする（列がずれて別の列の値を読むのを防ぐため）。閉じていない引用符も入力エラーにする。
    """
    if not text.strip():
        raise InputError(
            f"ファイルが空です（ヘッダー行もありません）: {path}\n"
            "  対処: Search Console からエクスポートし直してください。"
        )
    try:
        csv.field_size_limit(2 ** 31 - 1)
    except OverflowError:  # pragma: no cover
        csv.field_size_limit(2 ** 24)
    best = None
    for delimiter, name in DELIMITERS:
        header = first_record(text, delimiter)
        score = (count_known_headers(header), len(header))
        if best is None or score > best[0]:
            best = (score, delimiter, name)
    _score, delimiter, delimiter_name = best

    # strict=True: 閉じていない引用符や、閉じた引用符の直後の文字を入力エラーにする（黙って列がずれるのを防ぐ）
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    header = None
    width = 0
    rows = []
    n_blank = 0
    try:
        for record in reader:
            if not any(cell.strip() for cell in record):
                if header is not None:
                    n_blank += 1
                continue
            if header is None:
                header = record
                width = len(header)
                continue
            if len(record) > width:
                if any(cell.strip() for cell in record[width:]):
                    raise InputError(
                        f"CSV の形式が不正です: {path}\n"
                        f"  詳細: {reader.line_num} 行目のセルの数が {len(record)} 個で、ヘッダーの {width} 個より多い\n"
                        "  対処: 行ごとに列の数がそろっているか確認してください。"
                        "桁区切りのカンマを含む数値（1,234）や小数点がカンマの数値（3,5）は引用符で囲む必要があります。"
                    )
                record = record[:width]
            elif len(record) < width:
                record = record + [""] * (width - len(record))
            rows.append(record)
    except csv.Error as e:
        raise InputError(
            f"CSV の形式が不正です: {path}\n"
            f"  詳細: {reader.line_num} 行目付近: {e}\n"
            '  対処: 引用符（"）が閉じているか確認してください。セルの中の " は "" のように 2 つ重ねる必要があります。'
        )
    if header is None:
        raise InputError(
            f"ファイルが空です（ヘッダー行もありません）: {path}\n"
            "  対処: Search Console からエクスポートし直してください。"
        )
    return header, rows, delimiter_name, n_blank


def find_columns(header):
    """列名を正規化して照合し、({項目名: 列番号}, {項目名: [重複した列番号]}) を返す。"""
    alias_norms = {field: {normalize_header(a) for a in aliases} for field, aliases in COLUMN_ALIASES}
    matches = {}
    for idx, name in enumerate(header):
        norm = normalize_header(name)
        for field, _aliases in COLUMN_ALIASES:
            if norm in alias_norms[field]:
                matches.setdefault(field, []).append(idx)
                break
    found = {field: idxs[0] for field, idxs in matches.items() if len(idxs) == 1}
    conflicts = {field: idxs for field, idxs in matches.items() if len(idxs) > 1}
    return found, conflicts


def period_labeled_columns(header):
    """指標名に期間ラベルが付いた列名（比較表示のままのエクスポートらしい列）を返す。"""
    hits = []
    for name in header:
        norm = normalize_header(name)
        for field in METRIC_FIELDS:
            matched = False
            for alias in ALIAS_MAP[field]:
                a = normalize_header(alias)
                if a != norm and a in norm and PERIOD_LABEL_RE.search(norm.replace(a, " ")):
                    matched = True
                    break
            if matched:
                hits.append(name)
                break
    return hits


def comparison_hint():
    return ("  ヒント: 列名に期間のラベルが付いているようです。Search Console の比較表示のまま"
            "エクスポートした CSV は使えません。期間ごとに 1 回ずつエクスポートしてください。")


def missing_columns_message(path, fields, header, either=False):
    """必須列がないときのメッセージ（見つかった列名と受け付ける列名）を作る。"""
    names = [f"{f}（{FIELD_LABELS[f]}）" for f in fields]
    joined = " または ".join(names) if either else "、".join(names)
    shown = ", ".join(f"'{c}'" for c in header) if len(header) else "（なし）"
    lines = [
        f"必須の列が見つかりません: {path}",
        f"  見つからない項目: {joined}",
        f"  CSV にあった列名: {shown}",
        "  受け付ける列名（英字の大文字・小文字、前後の空白、全角・半角は区別しない）:",
    ]
    for f in fields:
        lines.append(f"    {f}: " + ", ".join(ALIAS_MAP[f]))
    if period_labeled_columns(header):
        lines.append(comparison_hint())
    lines.append(
        "  対処: Search Console の「検索パフォーマンス」からエクスポートした CSV を使うか、"
        "列名を上のいずれかに変えてください。"
    )
    return "\n".join(lines)


def conflict_message(path, field, header, indices):
    cols = ", ".join(f"'{header[i]}'（{i + 1} 列目）" for i in indices)
    return (f"同じ項目を表す列が複数あります: {path}\n"
            f"  項目: {field}（{FIELD_LABELS[field]}）: {cols}\n"
            "  どの列を使うか決められないため中止しました。\n"
            "  対処: 使う列だけを残すか、使わない列の名前を変えてください。")


def resolve_key(found, key_option, path, header):
    """キー列（query / page）を決める。auto では query を優先する。"""
    if key_option == "auto":
        if "query" in found:
            key = "query"
        elif "page" in found:
            key = "page"
        else:
            raise InputError(missing_columns_message(path, ["query", "page"], header, either=True))
    else:
        if key_option not in found:
            raise InputError(missing_columns_message(path, [key_option], header))
        key = key_option
    other = "page" if key == "query" else "query"
    if other not in found:
        other = None
    return key, other


def number_text(value):
    """数値の文字列を全角 → 半角にし、空白（桁区切りの空白を含む）を除く。"""
    text = unicodedata.normalize("NFKC", str(value)).replace("−", "-")
    return re.sub(r"\s+", "", text)


def column_decimal_evidence(field, texts):
    """列の値から、小数点がカンマ（3,5）か点（3.5）かの手がかりを探す。戻り値は (カンマ, 点)。"""
    comma = point = False
    counts = field in ("clicks", "impressions")
    for raw in texts:
        t = raw.replace("%", "")
        if not t:
            continue
        if EU_NUMBER_RE.fullmatch(t):
            comma = True
        elif US_NUMBER_RE.fullmatch(t):
            point = True
        elif counts:
            # 件数は整数なので、3 桁ごとの点は桁区切り（小数点はカンマ）、3 桁ごとのカンマは桁区切り（小数点は点）
            if DOT_GROUPED_RE.fullmatch(t):
                comma = True
            elif COMMA_GROUPED_RE.fullmatch(t):
                point = True
        else:
            # 掲載順位と CTR は 1,000 を超えないので、数字の間のカンマは小数点とみなす
            if DECIMAL_COMMA_RE.fullmatch(t):
                comma = True
            elif DECIMAL_POINT_RE.fullmatch(t):
                point = True
        if comma and point:
            break
    return comma, point


def decide_decimal_marks(texts_by_field):
    """列ごとに小数点の表記を決める。戻り値は ({項目名: "comma" または "point"}, 説明)。"""
    evidence = {f: column_decimal_evidence(f, t) for f, t in texts_by_field.items()}
    any_comma = any(c and not p for c, p in evidence.values())
    any_point = any(p for _c, p in evidence.values())
    modes = {}
    for field, (comma, point) in evidence.items():
        if comma and not point:
            modes[field] = "comma"
        elif point:
            modes[field] = "point"
        else:
            modes[field] = "comma" if (any_comma and not any_point) else "point"
    note = ""
    comma_fields = [f for f in texts_by_field if modes[f] == "comma"]
    if comma_fields:
        note = ("小数点がカンマの表記（3,5 や 1.234,5）とみなした列: " + ", ".join(comma_fields)
                + "（点は桁区切りとして扱う）")
        if any_point:
            note += "。警告: 小数点がカンマの列と点の列が混在しています。値を確認してください"
    mixed = [f for f, (c, p) in evidence.items() if c and p]
    if mixed:
        note = (note + "。" if note else "") + (
            "警告: 次の列で小数点の表記（3,5 と 3.5）が混在しています。点を小数点とみなしました: " + ", ".join(mixed))
    return modes, note


def parse_numbers(texts, mode, index):
    """number_text() 済みの文字列のリストを float の Series にする。解析できない値・無限大は NaN。"""
    cleaned = []
    for t in texts:
        if mode == "comma":
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
        cleaned.append(t)
    values = pd.to_numeric(pd.Series(cleaned, index=index, dtype=object), errors="coerce").astype(float)
    return values.where(values.abs() != float("inf"))


def compute_ctr(clicks, impressions):
    """クリック数 / 表示回数。表示回数が 0 の行は 0。"""
    safe = impressions.where(impressions > 0)
    return (clicks / safe).fillna(0.0)


def detect_ctr_scale(values, clicks, impressions):
    """数値だけの CTR 列が比率か百分率かを判定する。戻り値は (scale, 理由)。"""
    mask = values.notna() & clicks.notna() & impressions.notna() & (impressions > 0)
    if mask.any():
        calc = clicks[mask] / impressions[mask]
        diff_ratio = float((values[mask] - calc).abs().median())
        diff_pct = float((values[mask] / 100.0 - calc).abs().median())
        detail = (f"クリック数 / 表示回数との差の中央値: 比率とみなすと {diff_ratio:.4g}、"
                  f"百分率とみなすと {diff_pct:.4g}")
        if diff_ratio < diff_pct:
            return "ratio", f"比率とみなす（{detail}）"
        if diff_pct < diff_ratio:
            return "percent", f"百分率とみなして 100 で割る（{detail}）"
    max_value = values.max()
    if pd.notna(max_value) and max_value > 1:
        return "percent", "最大値が 1 を超えるため百分率とみなして 100 で割る"
    return "ratio", "最大値が 1 以下のため比率とみなす"


def parse_ctr(texts, mode, clicks, impressions, unit, index):
    """CTR 列を比率（0〜1）に変換する。戻り値は (Series, 判定の説明)。"""
    is_pct = pd.Series(["%" in t for t in texts], index=index, dtype=bool)
    values = parse_numbers([t.replace("%", "") for t in texts], mode, index)
    values = values.where(~(values < 0))
    has_value = values.notna()
    pct_rows = is_pct & has_value
    plain_rows = (~is_pct) & has_value
    notes = []
    if pct_rows.any():
        notes.append(f"% 付きの値 {int(pct_rows.sum())} 行は百分率として 100 で割る")
    divide = pct_rows
    if plain_rows.any():
        n_plain = int(plain_rows.sum())
        if unit == "percent":
            scale, reason = "percent", "--ctr-unit percent の指定により百分率とみなして 100 で割る"
        elif unit == "ratio":
            scale, reason = "ratio", "--ctr-unit ratio の指定により比率とみなす"
        else:
            scale, reason = detect_ctr_scale(values[plain_rows], clicks[plain_rows], impressions[plain_rows])
        notes.append(f"数値だけの値 {n_plain} 行: {reason}")
        if scale == "percent":
            divide = pct_rows | plain_rows
    ctr = values.where(~divide, values / 100.0)
    missing = ctr.isna()
    if missing.any():
        ctr = ctr.where(~missing, compute_ctr(clicks, impressions))
        notes.append(f"CTR が空・解析できない・負の値の {int(missing.sum())} 行はクリック数 / 表示回数で補う")
    return ctr, "。".join(notes) if notes else "CTR 列に値がない"


def check_ctr_consistency(ctr, clicks, impressions):
    """変換後の CTR がクリック数 / 表示回数と大きく違えば警告の文を返す（なければ None）。"""
    mask = ctr.notna() & clicks.notna() & impressions.notna() & (impressions > 0)
    if not mask.any():
        return None
    calc = clicks[mask] / impressions[mask]
    diff = float((ctr[mask] - calc).abs().median())
    reference = float(calc.median())
    if diff > max(0.005, 0.5 * reference):
        return (f"警告: CTR 列の値がクリック数 / 表示回数と大きく違います（差の中央値 {diff:.4g}）。"
                "--ctr-unit の指定と、列がずれていないかを確認してください。")
    return None


def load_gsc_csv(path, key_option, ctr_unit, zero_position="exclude"):
    """GSC のエクスポート CSV を読み、列を正規化した DataFrame と読み込み情報を返す。

    掲載順位が 0（"0"、"0.0"、"0,0" などを解析した結果が 0）の値は「値なし」とみなす。
    zero_position="exclude" ではその行を除外し、"missing" では掲載順位を NaN にして行を残す。
    """
    if zero_position not in ZERO_POSITION_MODES:
        raise ValueError(f"zero_position: {zero_position!r}")
    text, encoding, warnings = read_text(path)
    header, rows, delimiter_name, n_blank = parse_csv_text(text, path)
    found, conflicts = find_columns(header)
    ctr_conflict = conflicts.pop("ctr", None)
    for field in ("query", "page", "clicks", "impressions", "position"):
        if field in conflicts:
            raise InputError(conflict_message(path, field, header, conflicts[field]))
    key, other = resolve_key(found, key_option, path, header)
    missing = [f for f in REQUIRED_METRICS if f not in found]
    if missing:
        raise InputError(missing_columns_message(path, missing, header))
    labeled = period_labeled_columns(header)
    if labeled:
        warnings.append("警告: 期間ラベル付きらしい列があります（" + ", ".join(f"'{c}'" for c in labeled[:4])
                        + "）。比較表示のままのエクスポートなら、期間ごとに出し直してください。"
                        "今回はラベルのない列を使います。")

    index = pd.RangeIndex(len(rows))

    def column(field):
        idx = found[field]
        return [row[idx] for row in rows]

    texts = {f: [number_text(v) for v in column(f)] for f in NUMERIC_FIELDS if f in found}
    modes, decimal_note = decide_decimal_marks(texts)
    clicks = parse_numbers(texts["clicks"], modes["clicks"], index)
    impressions = parse_numbers(texts["impressions"], modes["impressions"], index)
    position = parse_numbers(texts["position"], modes["position"], index)
    negative = (clicks < 0) | (impressions < 0) | (position < 0)
    unparsed = (clicks.isna() | impressions.isna() | position.isna()) & ~negative
    # 掲載順位 0 は値なし（負の値・解析できない行は、そちらの件数に数える）
    zero_position_rows = (position == 0) & ~negative & ~unparsed
    clicks = clicks.where(~negative)
    impressions = impressions.where(~negative)
    position = position.where(~negative & (position != 0))
    if ctr_conflict:
        cols = ", ".join(f"'{header[i]}'" for i in ctr_conflict)
        ctr = compute_ctr(clicks, impressions)
        ctr_note = f"CTR の列が複数ある（{cols}）ため使わず、クリック数 / 表示回数で計算"
    elif "ctr" in found:
        ctr, ctr_note = parse_ctr(texts["ctr"], modes["ctr"], clicks, impressions, ctr_unit, index)
        inconsistent = check_ctr_consistency(ctr, clicks, impressions)
        if inconsistent:
            warnings.append(inconsistent)
    else:
        ctr = compute_ctr(clicks, impressions)
        ctr_note = "CTR 列がないためクリック数 / 表示回数で計算"

    data = {key: pd.Series([v.strip() for v in column(key)], index=index, dtype=object)}
    if other:
        data[other] = pd.Series([v.strip() for v in column(other)], index=index, dtype=object)
    data["clicks"] = clicks
    data["impressions"] = impressions
    data["ctr"] = ctr
    data["position"] = position
    df = pd.DataFrame(data, index=index)

    bad = unparsed | negative
    if zero_position == "exclude":
        bad = bad | zero_position_rows
    empty_key = (df[key] == "") & ~bad
    keep = ~(bad | empty_key)
    n_zero_position = int((zero_position_rows & ~empty_key).sum())
    df = df[keep].reset_index(drop=True)
    info = {
        "path": path,
        "encoding": encoding,
        "sep_name": delimiter_name,
        "n_input": int(len(rows)),
        "n_blank": int(n_blank),
        "n_bad_metric": int(unparsed.sum()),
        "n_negative": int(negative.sum()),
        "n_zero_position": n_zero_position,
        "zero_position": zero_position,
        "n_empty_key": int(empty_key.sum()),
        "key": key,
        "other": other,
        "found": {field: header[idx] for field, idx in found.items()},
        "ctr_note": ctr_note,
        "decimal_note": decimal_note,
        "warnings": warnings,
        "has_ctr_column": "ctr" in found,
    }
    return df, info


def log_load_info(info, label=""):
    keys = info["key"] + (f" + {info['other']}" if info["other"] else "")
    log(f"{label}入力: {info['path']}（文字コード {info['encoding']}、{info['sep_name']}区切り、"
        f"{info['n_input']} 行、キー列 {keys}）")
    mapping = ", ".join(f"{field}='{col}'" for field, col in info["found"].items())
    log(f"  列の対応: {mapping}")
    log(f"  CTR の単位: {info['ctr_note']}")
    if info["decimal_note"]:
        log(f"  数値の表記: {info['decimal_note']}")
    for warning in info["warnings"]:
        log(f"  {warning}")
    if info["n_blank"]:
        log(f"  空行 {info['n_blank']} 行を読み飛ばしました")
    if info["n_bad_metric"]:
        log(f"  除外: クリック数・表示回数・掲載順位のいずれかが空か解析できない行 {info['n_bad_metric']} 行")
    if info["n_negative"]:
        log(f"  除外: クリック数・表示回数・掲載順位のいずれかが負の値の行 {info['n_negative']} 行")
    if info["n_zero_position"]:
        if info["zero_position"] == "exclude":
            log(f"  除外: {ZERO_POSITION_LABEL}の行 {info['n_zero_position']} 行（掲載順位は最小 1 のため値なしとみなす）")
        else:
            log(f"  {ZERO_POSITION_LABEL}の行 {info['n_zero_position']} 行: 掲載順位を空欄（値なし）として扱います")
    if info["n_empty_key"]:
        log(f"  除外: キー列が空の行 {info['n_empty_key']} 行")


def excluded_summary(info, n_regex):
    """除外行数の合計と内訳の文字列を返す（掲載順位 0 は、除外する場合だけ内訳に入れる）。"""
    total = info["n_bad_metric"] + info["n_negative"] + info["n_empty_key"] + n_regex
    detail = f"数値を解析できない {info['n_bad_metric']}、負の値 {info['n_negative']}、"
    if info["zero_position"] == "exclude":
        total += info["n_zero_position"]
        detail += f"{ZERO_POSITION_LABEL} {info['n_zero_position']}、"
    detail += f"キー列が空 {info['n_empty_key']}、正規表現 {n_regex}"
    return total, detail


def compile_regex(pattern, option_name):
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise InputError(f"{option_name} の正規表現が不正です: {pattern}（{e}）")


def apply_filters(df, key, include_re, exclude_re):
    """キー列に --include-regex / --exclude-regex を適用する。戻り値は (DataFrame, 除外行数)。"""
    if include_re is None and exclude_re is None:
        return df, 0

    def hit(regex, value):
        return bool(regex.search(value) or regex.search(unicodedata.normalize("NFKC", value)))

    keep = []
    for value in df[key]:
        ok = True
        if include_re is not None and not hit(include_re, value):
            ok = False
        if ok and exclude_re is not None and hit(exclude_re, value):
            ok = False
        keep.append(ok)
    mask = pd.Series(keep, index=df.index, dtype=bool)
    return df[mask].reset_index(drop=True), int((~mask).sum())


def as_int_if_integral(series):
    """すべて整数値なら int64 にする（CSV に 12.0 ではなく 12 と出すため）。"""
    s = series.astype(float)
    if len(s) and bool(s.notna().all()) and bool(((s % 1) == 0).all()):
        return s.astype("int64")
    return s


def format_pct(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.2f}%"


def is_formula_like(value):
    """表計算ソフトが数式として解釈しうる文字列（先頭が = + - @ タブ CR）なら True。"""
    return isinstance(value, str) and value.startswith(FORMULA_PREFIXES)


def count_formula_cells(df):
    """query / page 列で、先頭が = + - @ タブ CR のセルの数を返す（値は変えない）。"""
    return sum(1 for col in TEXT_OUTPUT_COLUMNS if col in df.columns for v in df[col] if is_formula_like(v))


def sanitize_text_cells(df):
    """query / page 列で、先頭が = + - @ タブ CR のセルの前に ' を付ける。戻り値は (DataFrame, 件数)。"""
    count = 0
    updates = {}
    for col in TEXT_OUTPUT_COLUMNS:
        if col not in df.columns:
            continue
        values = []
        for v in df[col]:
            if is_formula_like(v):
                values.append("'" + v)
                count += 1
            else:
                values.append(v)
        updates[col] = pd.Series(values, index=df.index, dtype=object)
    if updates:
        df = df.assign(**updates)
    return df, count


def check_output_path(output, inputs):
    """-o が入力ファイルと同じなら入力エラーにする（入力を上書きしないため）。"""
    if not output or not os.path.exists(output):
        return
    for path in inputs:
        try:
            same = bool(path) and os.path.exists(path) and os.path.samefile(output, path)
        except OSError:
            same = False
        if same:
            raise InputError(f"-o の出力先が入力ファイルと同じです: {output}\n"
                             "  対処: 別のファイル名を指定してください（入力ファイルを上書きしないため）。")


def write_csv(df, output, sanitize=True):
    """-o があればファイルへ UTF-8（BOM 付き）で、なければ標準出力へ UTF-8（BOM なし）で書く。

    CSV インジェクション対策（' を付ける）は -o のファイルだけに適用する（sanitize=False で無効）。
    標準出力は Claude や他のプログラムが読む経路なので、値を変えずに書く。
    """
    if output:
        n_sanitized = 0
        if sanitize:
            df, n_sanitized = sanitize_text_cells(df)
        try:
            df.to_csv(output, index=False, encoding="utf-8-sig")
        except OSError as e:
            raise InputError(f"出力ファイルに書き込めません: {output}（{e}）")
        log(f"出力ファイル: {output}（{len(df)} 行、UTF-8 BOM 付き）")
        if n_sanitized:
            log(f"CSV インジェクション対策: query / page 列で先頭が = + - @ タブ CR のセル {n_sanitized} 個の前に "
                "' を付けました（-o のファイルだけ。pandas などで読むときは先頭の ' を除くか、--no-sanitize で出し直す）")
        return
    n_formula = count_formula_cells(df)
    data = df.to_csv(index=False).encode("utf-8")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    except BrokenPipeError:
        # head などで途中まで読まれた場合は静かに終わる
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    if n_formula:
        log(f"注意: query / page 列に、先頭が = + - @ タブ CR のセルが {n_formula} 個あります。標準出力には ' を付けず"
            "そのまま書きました。Excel で開くなら -o でファイルに書き出してください（-o のファイルでは ' を付けて、"
            "数式として扱われるのを防ぐ）。")


def add_common_args(parser):
    parser.add_argument(
        "--key", choices=["auto", "query", "page"], default="auto",
        help="キー列。auto はクエリ列があればクエリ、なければページ（デフォルト: %(default)s）。"
             "クエリ × ページの CSV では、キーにしなかった列も出力に残す")
    parser.add_argument(
        "--ctr-unit", choices=["auto", "percent", "ratio"], default="auto",
        help="CTR 列の単位（デフォルト: %(default)s）。auto は数値だけの列をクリック数 / 表示回数と"
             "照合して判定する。「3.5%%」のように %% が付いた値は指定にかかわらず百分率として扱う")
    parser.add_argument(
        "--include-regex", metavar="正規表現",
        help="キー列がこの正規表現に一致する行だけを使う（大文字・小文字を区別しない。全角・半角をそろえた値にも照合する）")
    parser.add_argument(
        "--exclude-regex", metavar="正規表現",
        help="キー列がこの正規表現に一致する行を除く。ブランド名クエリの除外などに使う（照合の仕方は --include-regex と同じ）")
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="出力 CSV のパス。Excel 向けに UTF-8（BOM 付き）で書き、CSV インジェクション対策をする"
             "（--no-sanitize を参照）。省略すると標準出力に UTF-8（BOM なし）で、値を変えずに書く"
             "（' は付けない）。Excel で開くなら -o を使う。入力ファイルと同じパスは指定できない")
    parser.add_argument(
        "--top", type=int, default=0, metavar="N",
        help="上位 N 件だけを出力する（デフォルト: 0 = 全件）")
    parser.add_argument(
        "--no-sanitize", dest="sanitize", action="store_false",
        help="-o のファイルの CSV インジェクション対策を無効にする。既定では -o のファイルで、"
             "query / page 列の先頭が「=」「+」「-」「@」（またはタブ・CR）のセルの前に ' を付ける"
             "（標準出力には付けない）。「-」で始まる正当なクエリ（例:「-20度 寝袋」）にも付くので、"
             "-o のファイルを pandas などで読むときは先頭の ' を除くか、このオプションで出し直す。"
             "数値の列は変えない")


def validate_common_args(args):
    if args.top < 0:
        raise InputError("--top には 0 以上の整数を指定してください。")


# ---------------------------------------------------------------------------
# low_ctr.py 固有の処理
# ---------------------------------------------------------------------------

BUCKET_EDGES = (1, 2, 3, 4, 6, 8, 11, 16, 21, 31)
BUCKET_LABELS = ("[1,2)", "[2,3)", "[3,4)", "[4,6)", "[6,8)",
                 "[8,11)", "[11,16)", "[16,21)", "[21,31)", "[31,∞)")
FLOAT_TOLERANCE = 1e-12

DESCRIPTION = """\
Search Console のエクスポート CSV から、掲載順位のわりに CTR が低いクエリ（またはページ）を抽出する。
title・meta description の改善候補を選ぶために使う。

期待 CTR はデフォルトで同じ CSV の自サイトの実績から作る（外部のベンチマーク値は使わない）。
掲載順位を [1,2) [2,3) [3,4) [4,6) [6,8) [8,11) [11,16) [16,21) [21,31) [31,∞) の区間に分け、
表示回数が --baseline-min-impressions 以上の行の「合計クリック数 / 合計表示回数」を区間ごとの期待 CTR とする。
行数が --min-bucket-rows 未満の区間は期待 CTR を空欄にし、その区間の行は抽出しない。
--include-regex / --exclude-regex を適用したあとのデータで計算する。

抽出条件: 掲載順位 <= --max-pos、表示回数 >= --min-impressions、CTR < 期待 CTR × --ratio
references/10-gsc-growth.md の手順（平均順位 5 位以内のページ）で見るなら、ページの CSV に --max-pos 5 を指定する。
lost_clicks = 表示回数 × (期待 CTR - CTR) は目安であり、予測ではない。"""

EPILOG = """\
使用例:
  python3 low_ctr.py Queries.csv -o low_ctr.csv
  python3 low_ctr.py クエリ.csv --exclude-regex "example|エグザンプル" --top 30 -o low_ctr.csv
  python3 low_ctr.py ページ.csv --max-pos 5 -o low_ctr_pages.csv   # 平均順位 5 位以内のページ（10-gsc-growth.md の手順）
  python3 low_ctr.py Queries.csv --ratio 0.6 --benchmark my_ctr_curve.csv

--benchmark の CSV の形式（例。値は架空）:
  position,ctr
  1,0.25
  2,12%
  3,0.08
  position は 1 以上の整数。ctr は比率（0.08）か % 付き（8%）。% のない値が 1 を超えるとエラーにする。
  各行の掲載順位を四捨五入した整数で表を引く。範囲外は端の値、途中の抜けは前後の値の線形補間を使う。

入力の注意:
  - 列名は英語・日本語のどちらの表記にも対応（Top queries / 上位のクエリ、Top pages / 上位のページ、
    Clicks / クリック数、Impressions / 表示回数、CTR、Position / 掲載順位 など）。
  - 必須列: クエリ列またはページ列、クリック数、表示回数、掲載順位。CTR 列は任意。
  - 文字コードは UTF-8 / cp932 / UTF-16（BOM なしも可）、区切りはカンマ・タブ・セミコロン。
  - 小数点がカンマの表記（3,5% や 8,2）と桁区切り（1,234 / 1.234 / 1 234）は列ごとに判定する。
  - 空・解析できない・負の値の行は除外して件数を表示する。
  - 掲載順位 0 は値なし（画面の「~」「-」がエクスポートで 0 になったもの）とみなし、その行を除外する。
  - CTR が低い原因は title・meta description だけではない（検索結果の広告・動画などの枠、検索意図とのずれ、
    他社名などのナビゲーショナルなクエリ）。実際の検索結果を見て判断すること。

出力:
  -o のファイルは UTF-8（BOM 付き）、標準出力は UTF-8（BOM なし）。
  列: query または page、（もう一方の列）、clicks, impressions, ctr, ctr_pct, position,
  bucket, expected_ctr, ctr_vs_expected, lost_clicks（lost_clicks の降順）
  CSV インジェクション対策: -o のファイルでは query / page 列で先頭が = + - @（またはタブ・CR）のセルに ' を付ける
  （標準出力には付けない。- で始まる正当なクエリにも付く。--no-sanitize で無効）。Excel で開くなら -o を使う。

終了コード: 0 = 正常（該当 0 件でも 0）、2 = 入力エラー"""


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """--help の折り返しでハイフンの位置では改行しない（ファイル名や User-Agent が途中で切れないようにする）。"""

    def _split_lines(self, text, width):
        return textwrap.wrap(re.sub(r"\s+", " ", text).strip(), width, break_on_hyphens=False)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="low_ctr.py",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=HelpFormatter,
    )
    parser.add_argument("input", help="Search Console のエクスポート CSV（クエリの表かページの表。UI の zip の中の"
                                      "クエリ.csv / Queries.csv、ページ.csv / Pages.csv という名前のことが多い）")
    parser.add_argument("--max-pos", type=float, default=10.0, metavar="順位",
                        help="掲載順位の上限。この値以下の行を対象にする（デフォルト: %(default)s。"
                             "references/10-gsc-growth.md の手順の「平均順位 5 位以内」で見るなら 5）")
    parser.add_argument("--min-impressions", type=int, default=100, metavar="回数",
                        help="表示回数の下限。この値以上の行を対象にする（デフォルト: %(default)s）")
    parser.add_argument("--ratio", type=float, default=0.5, metavar="比",
                        help="CTR が「期待 CTR × この値」を下回る行を抽出する。0 より大きく 1 以下"
                             "（デフォルト: %(default)s）")
    parser.add_argument("--baseline-min-impressions", type=int, default=10, metavar="回数",
                        help="期待 CTR の計算に使う行の表示回数の下限（デフォルト: %(default)s）")
    parser.add_argument("--min-bucket-rows", type=int, default=5, metavar="行数",
                        help="期待 CTR を計算するのに必要な、区間ごとの最低行数。"
                             "これ未満の区間は期待 CTR を空欄にし、その区間の行は抽出しない（デフォルト: %(default)s）")
    parser.add_argument("--benchmark", metavar="FILE",
                        help="position,ctr の 2 列の CSV。指定すると自サイトの実績の代わりにこの値を期待 CTR に使う")
    add_common_args(parser)
    return parser


def bucket_label(position):
    """掲載順位を区間のラベルにする（1 未満は最初の区間に入れる）。"""
    index = bisect.bisect_right(BUCKET_EDGES, position) - 1
    return BUCKET_LABELS[max(index, 0)]


def load_benchmark(path):
    """--benchmark の CSV を読み、(順位のリスト, CTR のリスト) を返す。"""
    text, _encoding, warnings = read_text(path)
    for warning in warnings:
        log(f"  --benchmark {path}: {warning}")
    header, rows, _sep, _blank = parse_csv_text(text, path)
    found, conflicts = find_columns(header)
    for field in ("position", "ctr"):
        if field in conflicts:
            raise InputError(conflict_message(path, field, header, conflicts[field]))
    missing = [f for f in ("position", "ctr") if f not in found]
    if missing:
        shown = ", ".join(f"'{c}'" for c in header) if len(header) else "（なし）"
        raise InputError(
            f"--benchmark の CSV に必要な列がありません: {path}\n"
            f"  見つからない項目: {'、'.join(missing)}\n"
            f"  CSV にあった列名: {shown}\n"
            "  形式: position,ctr の 2 列（position は 1 以上の整数、ctr は 0.08 のような比率か 8% のような % 付き）"
        )
    if len(rows) == 0:
        raise InputError(f"--benchmark の CSV にデータ行がありません: {path}")
    index = pd.RangeIndex(len(rows))
    texts = {f: [number_text(row[found[f]]) for row in rows] for f in ("position", "ctr")}
    modes, _note = decide_decimal_marks(texts)
    positions = parse_numbers(texts["position"], modes["position"], index)
    values = parse_numbers([s.replace("%", "") for s in texts["ctr"]], modes["ctr"], index)
    table = {}
    for line_no, (pos, value, text_value) in enumerate(zip(positions, values, texts["ctr"]), start=2):
        if pd.isna(pos) or pd.isna(value):
            raise InputError(f"--benchmark の {line_no} 行目を解析できません: {path}")
        if pos < 1 or pos % 1 != 0:
            raise InputError(f"--benchmark の {line_no} 行目: position は 1 以上の整数にしてください（{pos:g}）。")
        if "%" in text_value:
            ctr = value / 100.0
        else:
            if value > 1:
                raise InputError(
                    f"--benchmark の {line_no} 行目: ctr が 1 を超えています（{value:g}）。"
                    "百分率なら 8% のように % を付けてください。")
            ctr = value
        if ctr < 0 or ctr > 1:
            raise InputError(f"--benchmark の {line_no} 行目: ctr は 0〜1（0%〜100%）の範囲にしてください。")
        if int(pos) in table:
            raise InputError(f"--benchmark の {line_no} 行目: position {int(pos)} が重複しています。")
        table[int(pos)] = ctr
    items = sorted(table.items())
    return [p for p, _ in items], [c for _, c in items]


def benchmark_lookup(positions, ctrs, position):
    """掲載順位を四捨五入して表を引く。戻り値は (期待 CTR, 引いた順位)。"""
    rounded = int(math.floor(position + 0.5))
    if rounded <= positions[0]:
        return ctrs[0], rounded
    if rounded >= positions[-1]:
        return ctrs[-1], rounded
    i = bisect.bisect_left(positions, rounded)
    if positions[i] == rounded:
        return ctrs[i], rounded
    p0, p1 = positions[i - 1], positions[i]
    c0, c1 = ctrs[i - 1], ctrs[i]
    return c0 + (c1 - c0) * (rounded - p0) / (p1 - p0), rounded


def run(args):
    validate_common_args(args)
    if args.max_pos <= 0:
        raise InputError("--max-pos には 0 より大きい値を指定してください。")
    if not (0 < args.ratio <= 1):
        raise InputError(f"--ratio には 0 より大きく 1 以下の値を指定してください（指定値 {args.ratio:g}）。"
                         "1 より大きいと期待 CTR を上回る行まで抽出され、lost_clicks が負になるため。")
    if args.min_impressions < 0 or args.baseline_min_impressions < 0:
        raise InputError("--min-impressions と --baseline-min-impressions には 0 以上の整数を指定してください。")
    if args.min_bucket_rows < 1:
        raise InputError("--min-bucket-rows には 1 以上の整数を指定してください。")
    include_re = compile_regex(args.include_regex, "--include-regex")
    exclude_re = compile_regex(args.exclude_regex, "--exclude-regex")
    check_output_path(args.output, [args.input, args.benchmark])

    df, info = load_gsc_csv(args.input, args.key, args.ctr_unit, zero_position="exclude")
    log_load_info(info)
    benchmark = load_benchmark(args.benchmark) if args.benchmark else None
    key, other = info["key"], info["other"]
    df, n_regex = apply_filters(df, key, include_re, exclude_re)
    if n_regex:
        log(f"  除外: --include-regex / --exclude-regex による {n_regex} 行")

    if benchmark is None:
        buckets = pd.Series([bucket_label(p) for p in df["position"]], index=df.index, dtype=object)
        base = df[df["impressions"] >= args.baseline_min_impressions]
        base_buckets = buckets[base.index]
        expected_by_bucket = {}
        log(f"期待 CTR（自サイトの実績。表示回数 {args.baseline_min_impressions} 以上の行で計算、"
            f"区間の最低行数 {args.min_bucket_rows}）:")
        for label in BUCKET_LABELS:
            sub = base[base_buckets == label]
            n_rows = len(sub)
            clicks = float(sub["clicks"].sum())
            impressions = float(sub["impressions"].sum())
            if n_rows >= args.min_bucket_rows and impressions > 0:
                expected_by_bucket[label] = clicks / impressions
                log(f"  {label}: {clicks / impressions * 100:.2f}%（{n_rows} 行、"
                    f"クリック数 {clicks:g} / 表示回数 {impressions:g}）")
            else:
                expected_by_bucket[label] = float("nan")
                reason = "表示回数が 0" if n_rows >= args.min_bucket_rows else f"{n_rows} 行で最低行数未満"
                log(f"  {label}: 空欄（{reason}）")
        expected = pd.Series([expected_by_bucket[b] for b in buckets], index=df.index, dtype=float)
        method_note = "自サイトの実績（区間ごと）"
    else:
        bench_positions, bench_ctrs = benchmark
        looked_up = [benchmark_lookup(bench_positions, bench_ctrs, p) for p in df["position"]]
        expected = pd.Series([v[0] for v in looked_up], index=df.index, dtype=float)
        buckets = pd.Series([f"benchmark:{v[1]}" for v in looked_up], index=df.index, dtype=object)
        log(f"期待 CTR: --benchmark {args.benchmark} の値を使う（順位 {bench_positions[0]}〜{bench_positions[-1]}、"
            f"{len(bench_positions)} 件）")
        method_note = f"--benchmark {args.benchmark}"

    df = df.assign(bucket=buckets, expected_ctr=expected)
    candidates = (df["position"] <= args.max_pos) & (df["impressions"] >= args.min_impressions)
    no_expected = candidates & df["expected_ctr"].isna()
    if no_expected.any():
        counts = df.loc[no_expected, "bucket"].value_counts()
        detail = "、".join(f"{label} {int(counts[label])} 行" for label in BUCKET_LABELS if label in counts.index)
        log(f"期待 CTR が空欄の区間にあるため判定しなかった行: {int(no_expected.sum())} 行（{detail}）")

    threshold = df["expected_ctr"] * args.ratio
    hit_mask = candidates & df["expected_ctr"].notna() & (df["ctr"] < threshold - FLOAT_TOLERANCE)
    hits = df[hit_mask]
    safe_expected = hits["expected_ctr"].where(hits["expected_ctr"] > 0)
    hits = hits.assign(
        ctr_vs_expected=hits["ctr"] / safe_expected,
        lost_clicks=hits["impressions"] * (hits["expected_ctr"] - hits["ctr"]),
        _order=range(len(hits)),
    )
    hits = hits.sort_values(["lost_clicks", "_order"], ascending=[False, True], na_position="last")
    if args.top > 0:
        hits = hits.head(args.top)

    columns = {key: hits[key]}
    if other:
        columns[other] = hits[other]
    columns["clicks"] = as_int_if_integral(hits["clicks"])
    columns["impressions"] = as_int_if_integral(hits["impressions"])
    columns["ctr"] = hits["ctr"].round(4)
    columns["ctr_pct"] = hits["ctr"].map(format_pct)
    columns["position"] = hits["position"].round(2)
    columns["bucket"] = hits["bucket"]
    columns["expected_ctr"] = hits["expected_ctr"].round(4)
    columns["ctr_vs_expected"] = hits["ctr_vs_expected"].round(2)
    columns["lost_clicks"] = hits["lost_clicks"].round(1)
    result = pd.DataFrame(columns, index=hits.index).reset_index(drop=True)
    write_csv(result, args.output, args.sanitize)

    n_excluded, excluded_detail = excluded_summary(info, n_regex)
    log("--- サマリー ---")
    log(f"入力行数: {info['n_input']}")
    log(f"除外行数: {n_excluded}（{excluded_detail}）")
    log(f"判定に使った行数: {len(df)}")
    log(f"閾値: 掲載順位 {args.max_pos:g} 以下、表示回数 {args.min_impressions} 以上、"
        f"CTR < 期待 CTR × {args.ratio:g}")
    log(f"期待 CTR: {method_note}")
    log(f"CTR の単位: {info['ctr_note']}")
    log(f"条件（順位・表示回数）を満たす行: {int(candidates.sum())}、"
        f"うち期待 CTR がなく判定しなかった行: {int(no_expected.sum())}")
    log(f"該当件数: {int(hit_mask.sum())}" + (f"（出力は上位 {len(result)} 件）" if args.top > 0 else ""))
    if len(result):
        log(f"lost_clicks の合計（出力分・目安）: {float(result['lost_clicks'].sum()):.1f}")
    return EXIT_OK


def main(argv=None):
    setup_stderr()
    args = build_parser().parse_args(argv)
    if pd is None:
        return missing_packages(["pandas"], argv)
    try:
        return run(args)
    except InputError as e:
        log(f"エラー: {e}")
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    sys.exit(main())
