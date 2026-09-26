#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pandas>=2.3",
# ]
# ///
"""
decay.py - 前の期間よりクリック数が落ちたページ（またはクエリ）を見つけ、原因の当たりを付ける

目的:
  Search Console の検索パフォーマンスを 2 つの期間で 1 回ずつエクスポートした CSV を比べ、
  クリック数が落ちたページまたはクエリを抽出する。落ち方から原因の当たり（順位低下・需要減・CTR 低下など）を付け、
  リライトや調査の対象を選ぶために使う。

入力:
  --previous（前の期間）と --current（今の期間）の 2 つの CSV。同じ種類のエクスポート（クエリ同士、またはページ同士）を、
  同じ長さの 2 つの期間で 1 回ずつ取ったもの。季節性の影響を避けるため、前年同期との比較を推奨する
  （例: 直近 3 か月と前年の同じ 3 か月）。
  - Search Console の比較表示（期間を 2 つ選んだ状態）のまま出したエクスポートは受け付けない。
    列名に期間のラベルが付いて揺れるため。期間ごとに 1 回ずつエクスポートすること。
    期間ラベル付きらしい列名で必須列が見つからないときは、エラーメッセージでその旨を示す。
  - 文字コード: BOM があればそれに従う。なければ UTF-8 → cp932 の順に試す。BOM なしの UTF-16 も NUL バイトの
    位置で見分ける。区切り文字はカンマ・タブ・セミコロンから、ヘッダー行で既知の列名が最も多く見つかるものを使う。
  - 列名は英語・日本語のどちらの表記にも対応する（例: Top pages / 上位のページ、Top queries / 上位のクエリ、
    Clicks / クリック数、Impressions / 表示回数、CTR、Position / 掲載順位）。前期と今期で表記の言語が違ってもよい。
  - 必須列: クエリ列またはページ列、クリック数、表示回数、掲載順位。CTR 列はなくてもよい。
  - 数値の桁区切り（"1,234"、"1 234"）、全角数字、小数点がカンマの表記（"3,5%"、"8,2"）を処理する。
    空・解析できない・負の値の行は除外し、件数を標準エラー出力に出す。
  - 掲載順位 0 は値なし（画面の「~」「-」がエクスポートで 0 になったもの。順位は最小 1）とみなし、その期間の position を空欄にする（pos_diff も空欄になり「順位低下」の判定に使わない。件数は標準エラー出力に出す）。
  - 2 つのファイルのキー列の種類（query / page）が違うときは入力エラーにする。

処理:
  - 2 つのファイルをキー列で外部結合する。片方にしかない行は、その期間のクリック数・表示回数を 0 とする
    （CTR と掲載順位は空欄）。両方のファイルがクエリ列とページ列を持つ場合は、その組み合わせで結合する。
  - キーの照合: query は完全一致（大文字・小文字、全角・半角、空白の違いは別のクエリ）。
    page は、スキームとホスト名の大文字・小文字と、パーセントエンコードの表記（%E9%87%8E と「野」、%e9 と %E9）
    だけをそろえて照合する（どちらも同じ URL を表すため）。パスの大文字・小文字と末尾の / の違いは別の URL として扱う
    （実際に別の URL であるため）。前期だけ・今期だけにあるキーがこれらの違いだけで対応する場合は、
    URL の変更などの可能性があるので標準エラー出力に注意を出す。出力のキーは今期の表記（今期にないものは前期の表記）。
  - 同じキーの行が 1 つのファイルに複数あれば合算する（クリック数・表示回数は合計、掲載順位は表示回数で重み付けした平均。
    掲載順位が空欄の行は平均に入れない）。
  - 抽出条件: 前期のクリック数 >= --min-clicks、かつ 減少したクリック数 >= --min-drop-clicks、
    かつ クリック数の減少率 >= --min-drop-pct（%。デフォルト 30 は references/10-gsc-growth.md の手順と同じ基準）。
  - diagnosis（上から順に判定）:
      1. 今期のデータにない                                 → 消失（今期のデータなし）
      2. pos_diff（今期 - 前期。正の値が悪化）>= --pos-threshold → 順位低下
      3. 表示回数の減少率 >= --impr-drop-pct                   → 需要減（表示回数が減少・順位は維持）
      4. CTR の減少率 >= --ctr-drop-pct                        → CTR低下（順位・表示回数は維持）
      5. それ以外                                            → 複合要因
  - diagnosis は当たりを付けるための目安であり、原因の断定ではない。検索結果の実際の表示、
    ページの変更履歴、Google 検索セントラルで告知されたアップデートなどと突き合わせて確認する。

出力:
  CSV。-o を指定すればそのファイルへ UTF-8（BOM 付き。Excel で開く想定）、なければ標準出力へ UTF-8（BOM なし）で書く。
  列: query または page、（両方で結合した場合はもう一方の列）、
      clicks_prev, clicks_cur, clicks_diff, clicks_change_pct, impressions_prev, impressions_cur,
      impressions_change_pct, ctr_prev, ctr_cur, position_prev, position_cur, pos_diff, diagnosis
  - *_change_pct は % 単位の数値（小数第 1 位まで。-35.0 は 35% 減）。ctr_* は比率（小数第 4 位まで）。
  - 並び順は clicks_diff の昇順（落ち幅の大きい順）。
  - CSV インジェクション対策として、-o で書くファイルでは、query / page 列で先頭が = + - @（またはタブ・CR）の
    セルの前に ' を付ける。標準出力には付けない（Claude や他のプログラムが読む経路のため）。Excel で開くなら -o を使う。
    「-20度 寝袋」のような - で始まる正当なクエリにも付くので、-o のファイルを pandas などで読むときは先頭の ' を除くか、
    --no-sanitize で出し直す。数値の列（clicks_diff の負の値など）には付けない。
  - サマリー（入力行数、除外行数、結合結果、該当件数、診断ごとの件数、使った閾値、CTR の単位判定）は標準エラー出力に出す。

使い方の例:
  python3 decay.py --previous pages_2025.csv --current pages_2026.csv -o decay.csv
  python3 decay.py --previous 前期_ページ.csv --current 今期_ページ.csv --min-clicks 50 --top 30 -o decay.csv
  python3 decay.py --previous q_prev.csv --current q_cur.csv --exclude-regex "example|エグザンプル"

制約・注意点:
  - 「消失」は今期の CSV に行がないことを示すだけである。Search Console の UI からのエクスポートは最大 1,000 行なので、
    行数が上限に近い場合は、上位 1,000 行から外れただけのこともある。URL の変更（リダイレクト）でも旧 URL は消失になる。
  - クエリの CSV には、プライバシー保護のために匿名化されたクエリは行として出ない。そのためクエリ別の合計は
    グラフやページ別の合計より小さく、クエリの行がないことは「検索結果に表示されていない」ことを意味しない。
    サイト全体の傾向はページ別の CSV で見る。
  - 2 つの期間の長さが同じかどうかは CSV からは確かめられない。エクスポートするときに確認すること。
  - 掲載順位は期間内の平均値である。ページ単位では複数のクエリの成績がまとめられている。
  - AI による概要や AI モードに表示された分も、検索タイプ「ウェブ」の表示回数・クリック数に含まれる
    （Google 検索セントラルの AI 機能に関するドキュメントによる）。
  - 依存パッケージは pandas だけ（Python 3.9 以上、pandas 2.x / 3.x）。
  - 終了コード: 0 = 正常終了（該当 0 件でも 0）、2 = 入力エラー（ファイルがない、必須列がない、キー列の種類が違う、引数が不正など）。
"""

import argparse
import codecs
import csv
import filecmp
import io
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
# decay.py 固有の処理
# ---------------------------------------------------------------------------

FLOAT_TOLERANCE = 1e-9
UI_EXPORT_ROW_LIMIT = 1000

LABEL_DISAPPEARED = "消失（今期のデータなし）"
LABEL_RANK_DROP = "順位低下"
LABEL_DEMAND_DROP = "需要減（表示回数が減少・順位は維持）"
LABEL_CTR_DROP = "CTR低下（順位・表示回数は維持）"
LABEL_MIXED = "複合要因"
DIAGNOSIS_LABELS = (LABEL_DISAPPEARED, LABEL_RANK_DROP, LABEL_DEMAND_DROP, LABEL_CTR_DROP, LABEL_MIXED)

DESCRIPTION = """\
Search Console のエクスポート CSV を 2 つの期間で比べ、クリック数が落ちたページ（またはクエリ）を抽出して、
原因の当たり（diagnosis）を付ける。

--previous と --current には、同じ種類のエクスポート（ページ同士、またはクエリ同士）を、
同じ長さの 2 つの期間で 1 回ずつ取ったものを指定する。
季節性の影響を避けるため、前年同期との比較を推奨する（例: 直近 3 か月と前年の同じ 3 か月）。
Search Console の比較表示のまま出したエクスポートは、列名に期間のラベルが付いて揺れるため受け付けない。

抽出条件: 前期のクリック数 >= --min-clicks、減少したクリック数 >= --min-drop-clicks、
          クリック数の減少率 >= --min-drop-pct（%。デフォルト 30 は references/10-gsc-growth.md の手順の基準）
diagnosis（上から順に判定）:
  1. 今期のデータにない                                 → 消失（今期のデータなし）
  2. pos_diff（今期 - 前期。正の値が悪化）>= --pos-threshold → 順位低下
  3. 表示回数の減少率 >= --impr-drop-pct                   → 需要減（表示回数が減少・順位は維持）
  4. CTR の減少率 >= --ctr-drop-pct                        → CTR低下（順位・表示回数は維持）
  5. それ以外                                            → 複合要因
diagnosis は当たりを付けるための目安であり、原因の断定ではない。"""

EPILOG = """\
使用例:
  python3 decay.py --previous pages_2025.csv --current pages_2026.csv -o decay.csv
  python3 decay.py --previous 前期_ページ.csv --current 今期_ページ.csv --min-clicks 50 --top 30 -o decay.csv
  python3 decay.py --previous q_prev.csv --current q_cur.csv --exclude-regex "example|エグザンプル"

入力の注意:
  - 列名は英語・日本語のどちらの表記にも対応（Top pages / 上位のページ、Top queries / 上位のクエリ、
    Clicks / クリック数、Impressions / 表示回数、CTR、Position / 掲載順位 など）。
  - 必須列: クエリ列またはページ列、クリック数、表示回数、掲載順位。CTR 列は任意。
  - 2 つのファイルのキー列の種類（query / page）が違うと入力エラー（終了コード 2）。列名の言語は違ってもよい。
  - 文字コードは UTF-8 / cp932 / UTF-16（BOM なしも可）、区切りはカンマ・タブ・セミコロン。
    小数点がカンマの表記（3,5% や 8,2）と桁区切り（1,234 / 1.234 / 1 234）は列ごとに判定する。
  - 片方にしかない行は、その期間のクリック数・表示回数を 0 とする。同じキーの重複行は合算する。
  - 掲載順位 0 は値なし（画面の「~」「-」がエクスポートで 0 になったもの）とみなし、position と pos_diff を空欄にして「順位低下」の判定に使わない。
  - キーの照合: query は完全一致。page はスキーム・ホスト名の大文字・小文字とパーセントエンコードの
    表記（%E9%87%8E と「野」）だけをそろえる。パスの大文字・小文字と末尾の / の違いは別の URL として扱い、
    前期のみ・今期のみのキーがその違いだけで対応すれば標準エラー出力に注意を出す。
  - 「消失」は今期の CSV に行がないことを示すだけ。UI のエクスポートは最大 1,000 行なので、
    上位 1,000 行から外れただけのこともある。URL を変更した場合も旧 URL は消失になる。
    クエリの CSV では、匿名化されたクエリは行に出ないので、行がないことは表示されていないことを意味しない。

出力:
  -o のファイルは UTF-8（BOM 付き）、標準出力は UTF-8（BOM なし）。
  列: query または page、（両方で結合した場合はもう一方の列）、clicks_prev, clicks_cur, clicks_diff,
  clicks_change_pct, impressions_prev, impressions_cur, impressions_change_pct, ctr_prev, ctr_cur,
  position_prev, position_cur, pos_diff, diagnosis
  *_change_pct は % 単位（-35.0 は 35% 減）。clicks_diff の昇順（落ち幅の大きい順）に並べる。
  CSV インジェクション対策: -o のファイルでは query / page 列で先頭が = + - @（またはタブ・CR）のセルに ' を付ける
  （標準出力には付けない。- で始まる正当なクエリにも付く。--no-sanitize で無効）。Excel で開くなら -o を使う。

終了コード: 0 = 正常（該当 0 件でも 0）、2 = 入力エラー"""


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """--help の折り返しでハイフンの位置では改行しない（ファイル名や User-Agent が途中で切れないようにする）。"""

    def _split_lines(self, text, width):
        return textwrap.wrap(re.sub(r"\s+", " ", text).strip(), width, break_on_hyphens=False)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="decay.py",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=HelpFormatter,
    )
    parser.add_argument("--current", required=True, metavar="FILE",
                        help="今の期間のエクスポート CSV（必須）")
    parser.add_argument("--previous", required=True, metavar="FILE",
                        help="前の期間のエクスポート CSV（必須）。--current と同じ種類・同じ長さの期間にする")
    parser.add_argument("--min-clicks", type=int, default=20, metavar="回数",
                        help="前期のクリック数の下限（デフォルト: %(default)s）")
    parser.add_argument("--min-drop-pct", type=float, default=30.0, metavar="%",
                        help="クリック数の減少率の下限（%%。0〜100。デフォルト: %(default)s。references/10-gsc-growth.md の手順の基準）")
    parser.add_argument("--min-drop-clicks", type=int, default=10, metavar="回数",
                        help="減少したクリック数の下限（デフォルト: %(default)s）")
    parser.add_argument("--pos-threshold", type=float, default=2.0, metavar="順位",
                        help="掲載順位がこの値以上悪化したら「順位低下」とする（0 より大きい値。デフォルト: %(default)s）")
    parser.add_argument("--impr-drop-pct", type=float, default=20.0, metavar="%",
                        help="表示回数の減少率がこの値以上なら「需要減」とする（%%。0〜100。デフォルト: %(default)s）")
    parser.add_argument("--ctr-drop-pct", type=float, default=20.0, metavar="%",
                        help="CTR の減少率がこの値以上なら「CTR低下」とする（%%。0〜100。デフォルト: %(default)s）")
    add_common_args(parser)
    return parser


PCT_RUN_RE = re.compile(r"(?:%[0-9A-Fa-f]{2})+")
SCHEME_HOST_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*://)([^/?#]*)")
UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _decode_pct_run(match):
    """%XX の並びを、UTF-8 として読めれば非 ASCII 文字と非予約文字に戻し、それ以外は大文字の %XX にそろえる。"""
    run = match.group(0)
    try:
        decoded = bytes.fromhex(run.replace("%", "")).decode("utf-8")
    except UnicodeDecodeError:
        return run.upper()
    out = []
    for ch in decoded:
        if ord(ch) > 127 or ch in UNRESERVED:
            out.append(ch)
        else:
            out.append("%{:02X}".format(ord(ch)))
    return "".join(out)


def normalize_page_key(url):
    """page の照合用の値。スキーム・ホスト名を小文字にし、パーセントエンコードの表記をそろえる。

    パスの大文字・小文字、末尾の /、クエリ文字列は変えない（別の URL として扱う）。
    """
    text = PCT_RUN_RE.sub(_decode_pct_run, url)
    match = SCHEME_HOST_RE.match(text)
    if match:
        text = match.group(1).lower() + match.group(2).lower() + text[match.end():]
    return text


def loose_key(value, field):
    """大文字・小文字（全角・半角）と、page では末尾の / を無視した値。注意を出すためだけに使う。"""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    if field == "page":
        text = normalize_page_key(text).rstrip("/")
    return text


def add_join_keys(df, join_cols):
    """結合に使う列（_j_query / _j_page）を加える。"""
    updates = {}
    for col in join_cols:
        if col == "page":
            values = [normalize_page_key(v) for v in df[col]]
        else:
            values = list(df[col])
        updates[f"_j_{col}"] = pd.Series(values, index=df.index, dtype=object)
    return df.assign(**updates)


def aggregate_duplicates(df, join_cols, label):
    """結合に使う列が重複する行を合算する（掲載順位は表示回数で重み付けした平均）。"""
    jcols = [f"_j_{c}" for c in join_cols]
    duplicated = df.duplicated(subset=jcols, keep=False)
    if not duplicated.any():
        return df
    n_rows = int(duplicated.sum())
    n_groups = int(len(df.loc[duplicated, jcols].drop_duplicates()))
    # 掲載順位が空欄（掲載順位 0 = 値なし）の行は、重み付き平均の分子にも分母にも入れない
    has_position = df["position"].notna()
    weighted = df.assign(
        _pos_x_impr=(df["position"] * df["impressions"]).where(has_position, 0.0),
        _pos_impr=df["impressions"].where(has_position, 0.0),
    )
    named = {c: (c, "first") for c in join_cols}
    grouped = weighted.groupby(jcols, sort=False, as_index=False).agg(
        clicks=("clicks", "sum"),
        impressions=("impressions", "sum"),
        _pos_x_impr=("_pos_x_impr", "sum"),
        _pos_impr=("_pos_impr", "sum"),
        _pos_mean=("position", "mean"),
        **named,
    )
    safe_impressions = grouped["_pos_impr"].where(grouped["_pos_impr"] > 0)
    position = (grouped["_pos_x_impr"] / safe_impressions).fillna(grouped["_pos_mean"])
    result = grouped[jcols + join_cols].assign(
        clicks=grouped["clicks"],
        impressions=grouped["impressions"],
        ctr=compute_ctr(grouped["clicks"], grouped["impressions"]),
        position=position,
    )
    log(f"  {label}: {'・'.join(join_cols)} が重複する {n_rows} 行を {n_groups} 行に合算しました"
        "（クリック数・表示回数は合計、掲載順位は表示回数で重み付けした平均、CTR は再計算。"
        "page はパーセントエンコードの表記の違いも同じ URL とみなす）")
    n_blank = int((duplicated & ~has_position).sum())
    if n_blank:
        log(f"    そのうち掲載順位が空欄（値なし）の {n_blank} 行は、掲載順位の平均に入れていません")
    return result


def pct_change(new, old):
    """(new - old) / old × 100。old が 0 以下なら NaN。"""
    return (new - old) * 100.0 / old.where(old > 0)


def diagnose(absent_now, pos_diff, impr_drop_pct, ctr_drop_pct, args):
    if absent_now:
        return LABEL_DISAPPEARED
    if pd.notna(pos_diff) and pos_diff >= args.pos_threshold - FLOAT_TOLERANCE:
        return LABEL_RANK_DROP
    if pd.notna(impr_drop_pct) and impr_drop_pct >= args.impr_drop_pct - FLOAT_TOLERANCE:
        return LABEL_DEMAND_DROP
    if pd.notna(ctr_drop_pct) and ctr_drop_pct >= args.ctr_drop_pct - FLOAT_TOLERANCE:
        return LABEL_CTR_DROP
    return LABEL_MIXED


def report_near_duplicates(prev_only, cur_only, key):
    """前期だけ・今期だけのキーが、大文字・小文字や末尾の / だけの違いで対応していれば注意を出す。"""
    cur_by_loose = {}
    for value in cur_only:
        cur_by_loose.setdefault(loose_key(value, key), value)
    pairs = [(p, cur_by_loose[loose_key(p, key)]) for p in prev_only if loose_key(p, key) in cur_by_loose]
    if not pairs:
        return
    what = "大文字・小文字や末尾の「/」" if key == "page" else "大文字・小文字や全角・半角"
    log(f"  注意: 前期だけにあるキーのうち {len(pairs)} 件は、今期だけにあるキーと{what}だけが違います。"
        "別のキーとして扱っています（URL の変更・リダイレクトや表記の変化の可能性。両方の行を確認してください）:")
    for prev_value, cur_value in pairs[:5]:
        log(f"    前期 '{prev_value}' / 今期 '{cur_value}'")
    if len(pairs) > 5:
        log(f"    ほか {len(pairs) - 5} 件")


def run(args):
    validate_common_args(args)
    for name in ("min_clicks", "min_drop_clicks"):
        if getattr(args, name) < 0:
            raise InputError(f"--{name.replace('_', '-')} には 0 以上の整数を指定してください。")
    for name in ("min_drop_pct", "impr_drop_pct", "ctr_drop_pct"):
        if not (0 <= getattr(args, name) <= 100):
            raise InputError(f"--{name.replace('_', '-')} には 0〜100 の値を指定してください"
                             f"（指定値 {getattr(args, name):g}。減少率は 100% を超えないため）。")
    if args.pos_threshold <= 0:
        raise InputError("--pos-threshold には 0 より大きい値を指定してください。")
    include_re = compile_regex(args.include_regex, "--include-regex")
    exclude_re = compile_regex(args.exclude_regex, "--exclude-regex")
    check_output_path(args.output, [args.previous, args.current])

    # 掲載順位 0（値なし）は行を残して position を空欄にする（pos_diff も空欄になり、順位低下の判定に使わない）
    prev_df, prev_info = load_gsc_csv(args.previous, args.key, args.ctr_unit, zero_position="missing")
    log_load_info(prev_info, label="[前期] ")
    cur_df, cur_info = load_gsc_csv(args.current, args.key, args.ctr_unit, zero_position="missing")
    log_load_info(cur_info, label="[今期] ")

    if prev_info["key"] != cur_info["key"]:
        raise InputError(
            f"2 つのファイルのキー列の種類が違います: 前期 {prev_info['key']}（{args.previous}）、"
            f"今期 {cur_info['key']}（{args.current}）\n"
            "  対処: 同じ種類のエクスポート（ページ同士、またはクエリ同士）を指定してください。"
            "両方の列を持つ CSV なら --key query または --key page でそろえられます。"
        )
    key = cur_info["key"]
    try:
        if filecmp.cmp(args.previous, args.current, shallow=False):
            log("  警告: --previous と --current が同じ内容のファイルです。期間の指定を確認してください。")
    except OSError:
        pass
    for info, label in ((prev_info, "前期"), (cur_info, "今期")):
        if info["n_input"] == UI_EXPORT_ROW_LIMIT:
            log(f"  注意: {label}のファイルがちょうど {UI_EXPORT_ROW_LIMIT} 行です。UI のエクスポート上限で切れている"
                "可能性があり、「消失」には上位の行から外れただけの行が含まれることがあります。")

    other = None
    if prev_info["other"] and cur_info["other"]:
        other = cur_info["other"]
        join_cols = [key, other]
        log(f"結合: {key} と {other} の組み合わせで結合します（両方のファイルに両方の列があるため）。")
    else:
        join_cols = [key]
        for info, label in ((prev_info, "前期"), (cur_info, "今期")):
            if info["other"]:
                log(f"  注意: {label}のファイルにだけ {info['other']} 列があるため、{info['other']} 列は結合に使わず出力しません。")
        prev_df = prev_df.drop(columns=[c for c in ("query", "page") if c != key and c in prev_df.columns])
        cur_df = cur_df.drop(columns=[c for c in ("query", "page") if c != key and c in cur_df.columns])

    prev_df, prev_regex = apply_filters(prev_df, key, include_re, exclude_re)
    cur_df, cur_regex = apply_filters(cur_df, key, include_re, exclude_re)
    if prev_regex or cur_regex:
        log(f"  除外: --include-regex / --exclude-regex による 前期 {prev_regex} 行、今期 {cur_regex} 行")
    jcols = [f"_j_{c}" for c in join_cols]
    prev_df = aggregate_duplicates(add_join_keys(prev_df, join_cols), join_cols, "前期")
    cur_df = aggregate_duplicates(add_join_keys(cur_df, join_cols), join_cols, "今期")

    metrics = ("clicks", "impressions", "ctr", "position")
    prev_r = prev_df.rename(columns=dict([(m, f"{m}_prev") for m in metrics] + [(c, f"{c}__prev") for c in join_cols]))
    cur_r = cur_df.rename(columns=dict([(m, f"{m}_cur") for m in metrics] + [(c, f"{c}__cur") for c in join_cols]))
    merged = prev_r.merge(cur_r, on=jcols, how="outer", indicator=True)
    status = merged["_merge"].astype(str)
    in_prev = status.isin(["both", "left_only"])
    in_cur = status.isin(["both", "right_only"])
    # 出力するキーは今期の表記。今期にない行は前期の表記
    display = {}
    for col in join_cols:
        cur_values = merged[f"{col}__cur"]
        prev_values = merged[f"{col}__prev"]
        display[col] = pd.Series(
            [c if isinstance(c, str) else p for c, p in zip(cur_values, prev_values)],
            index=merged.index, dtype=object)
    if len(join_cols) == 1:
        report_near_duplicates(list(display[key][in_prev & ~in_cur]), list(display[key][in_cur & ~in_prev]), key)

    clicks_prev = merged["clicks_prev"].fillna(0.0)
    clicks_cur = merged["clicks_cur"].fillna(0.0)
    impressions_prev = merged["impressions_prev"].fillna(0.0)
    impressions_cur = merged["impressions_cur"].fillna(0.0)
    ctr_prev = merged["ctr_prev"]
    ctr_cur = merged["ctr_cur"]
    position_prev = merged["position_prev"]
    position_cur = merged["position_cur"]

    clicks_diff = clicks_cur - clicks_prev
    clicks_change_pct = pct_change(clicks_cur, clicks_prev)
    impressions_change_pct = pct_change(impressions_cur, impressions_prev)
    ctr_change_pct = pct_change(ctr_cur, ctr_prev)
    pos_diff = position_cur - position_prev

    drop_clicks = clicks_prev - clicks_cur
    drop_pct = -clicks_change_pct
    hit_mask = (
        (clicks_prev > 0)
        & (clicks_prev >= args.min_clicks)
        & (drop_clicks >= args.min_drop_clicks - FLOAT_TOLERANCE)
        & (drop_pct >= args.min_drop_pct - FLOAT_TOLERANCE)
    )

    diagnosis = pd.Series(
        [diagnose(not now, pdiff, -impr_pct, -ctr_pct, args)
         for now, pdiff, impr_pct, ctr_pct in zip(in_cur, pos_diff, impressions_change_pct, ctr_change_pct)],
        index=merged.index, dtype=object)

    table = pd.DataFrame({key: display[key]}, index=merged.index)
    if other:
        table[other] = display[other]
    table = table.assign(
        clicks_prev=clicks_prev,
        clicks_cur=clicks_cur,
        clicks_diff=clicks_diff,
        clicks_change_pct=clicks_change_pct,
        impressions_prev=impressions_prev,
        impressions_cur=impressions_cur,
        impressions_change_pct=impressions_change_pct,
        ctr_prev=ctr_prev,
        ctr_cur=ctr_cur,
        position_prev=position_prev,
        position_cur=position_cur,
        pos_diff=pos_diff,
        diagnosis=diagnosis,
    )
    hits = table[hit_mask]
    hits = hits.sort_values(["clicks_diff", "clicks_prev", key], ascending=[True, False, True])
    if args.top > 0:
        hits = hits.head(args.top)

    columns = {key: hits[key]}
    if other:
        columns[other] = hits[other]
    for name in ("clicks_prev", "clicks_cur", "clicks_diff"):
        columns[name] = as_int_if_integral(hits[name])
    columns["clicks_change_pct"] = hits["clicks_change_pct"].round(1)
    columns["impressions_prev"] = as_int_if_integral(hits["impressions_prev"])
    columns["impressions_cur"] = as_int_if_integral(hits["impressions_cur"])
    columns["impressions_change_pct"] = hits["impressions_change_pct"].round(1)
    columns["ctr_prev"] = hits["ctr_prev"].round(4)
    columns["ctr_cur"] = hits["ctr_cur"].round(4)
    columns["position_prev"] = hits["position_prev"].round(2)
    columns["position_cur"] = hits["position_cur"].round(2)
    columns["pos_diff"] = hits["pos_diff"].round(2)
    columns["diagnosis"] = hits["diagnosis"]
    result = pd.DataFrame(columns, index=hits.index).reset_index(drop=True)
    write_csv(result, args.output, args.sanitize)

    total_prev = float(clicks_prev.sum())
    total_cur = float(clicks_cur.sum())
    log("--- サマリー ---")
    for info, n_regex, label in ((prev_info, prev_regex, "前期"), (cur_info, cur_regex, "今期")):
        n_excluded, excluded_detail = excluded_summary(info, n_regex)
        log(f"{label}: 入力 {info['n_input']} 行、除外 {n_excluded} 行（{excluded_detail}）、"
            f"{ZERO_POSITION_LABEL}で position を空欄にした行 {info['n_zero_position']} 行")
    if prev_info["n_zero_position"] or cur_info["n_zero_position"]:
        log("  掲載順位が空欄の行は pos_diff も空欄で、「順位低下」の判定に使っていません"
            "（クリック数・表示回数・CTR で判定）。")
    log(f"結合後: {len(merged)} 行（両方にある {int((in_prev & in_cur).sum())}、前期のみ {int((in_prev & ~in_cur).sum())}、"
        f"今期のみ {int((in_cur & ~in_prev).sum())}）")
    change = f"（{(total_cur - total_prev) * 100.0 / total_prev:+.1f}%）" if total_prev > 0 else ""
    log(f"CSV 内のクリック数の合計: 前期 {total_prev:g} → 今期 {total_cur:g}{change}")
    log(f"閾値: 前期のクリック数 {args.min_clicks} 以上、減少 {args.min_drop_clicks} クリック以上、"
        f"減少率 {args.min_drop_pct:g}% 以上 / 診断: 順位悪化 {args.pos_threshold:g} 以上、"
        f"表示回数の減少率 {args.impr_drop_pct:g}% 以上、CTR の減少率 {args.ctr_drop_pct:g}% 以上")
    log(f"CTR の単位: 前期 {prev_info['ctr_note']} / 今期 {cur_info['ctr_note']}")
    log(f"該当件数: {int(hit_mask.sum())}" + (f"（出力は上位 {len(result)} 件）" if args.top > 0 else ""))
    if hit_mask.any():
        counts = diagnosis[hit_mask].value_counts()
        log("診断ごとの件数（目安。原因の断定ではない）: "
            + "、".join(f"{label} {int(counts.get(label, 0))}" for label in DIAGNOSIS_LABELS))
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
