#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pandas>=2.3,<4",
# ]
# ///
"""
striking_distance.py - 掲載順位 8〜20 位の「あと一歩」のクエリ（またはページ）を抽出する

目的:
  Search Console の検索パフォーマンスのエクスポートから、掲載順位が 1 ページ目の下位〜2 ページ目
  （デフォルト 8〜20 位）で、表示回数が一定以上（デフォルト 100 回以上）あるクエリまたはページを抽出する。
  リライト、内部リンクの追加、title の改善で上位を狙う候補を洗い出すために使う。
  表示回数の下限 100 は references/10-gsc-growth.md の手順と同じ基準。小規模サイトで候補が少なければ
  --min-impressions を下げる。

入力:
  Search Console のエクスポート。画面からダウンロードした zip はそのまま渡せる（展開しなくてよい）。
  zip の中から、--key に合わせてクエリの表（クエリ.csv / Queries.csv）かページの表（ページ.csv / Pages.csv）を
  選んで読む。展開した CSV や、Search Console API・Data Studio（旧 Looker Studio）・スプレッドシート経由の CSV も読める。
  - zip: 展開せずにメモリの上で読み、ディスクには書かない。zip かどうかは先頭のバイトで判定する（拡張子は見ない）。
    表の名前は英字の大文字・小文字を区別せず、zip の中のフォルダも探す。UTF-8 のフラグがない名前
    （macOS や Windows で圧縮し直した zip）も読む。--key auto はクエリの表を読み、クエリの表にデータ行がなく
    ページの表があれば、ページの表を読む。次の zip は入力エラーにする: 該当する表がないか 2 つ以上ある、
    パスワード付き、壊れている、無圧縮と Deflate 以外の圧縮方式、zip ファイルか表が（展開後に）100 MB を超える。
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

出力:
  CSV。-o を指定すればそのファイルへ UTF-8（BOM 付き。Excel で開く想定）、なければ標準出力へ UTF-8（BOM なし）で書く。
  列: query または page、（クエリ × ページの CSV ではもう一方の列）、
      clicks, impressions, ctr, ctr_pct, position, est_extra_clicks
  - ctr は比率（小数第 4 位まで）、ctr_pct は読みやすさのための百分率表記（例 3.52%）。
  - 並び順は est_extra_clicks の降順、同じ値なら impressions の降順。references/10-gsc-growth.md の手順
    （表示回数の多い順の上位 30 件）で見るときは、--top を付けずに出力し、impressions の降順に並べ替えてから
    上位 30 件を取る（--top は est_extra_clicks の順で切るため）。
  - CSV インジェクション対策として、-o で書くファイルでは、query / page 列で先頭が = + - @（またはタブ・CR）の
    セルの前に ' を付ける。標準出力には付けない（Claude や他のプログラムが読む経路のため）。Excel で開くなら -o を使う。
    「-20度 寝袋」のような - で始まる正当なクエリにも付くので、-o のファイルを pandas などで読むときは先頭の ' を除くか、
    --no-sanitize で出し直す。数値の列には付けない。
  - サマリー（入力行数、除外行数、該当件数、使った閾値、CTR の単位判定、目標 CTR）は標準エラー出力に出す。

est_extra_clicks（追加クリック数の目安）:
  同じ CSV の中で掲載順位が --target-max-pos（デフォルト 3）以下の行について
  「合計クリック数 / 合計表示回数」を求め、これを目標 CTR とする。各行の値は
      表示回数 × max(0, 目標 CTR - 現在の CTR)
  で計算する。外部のベンチマーク値は使わない。
  これは予測ではなく、自サイトの上位表示時の実績 CTR を当てはめた目安である。
  検索意図や SERP の構成（広告、AI による概要、動画枠など）が違うクエリでは実際の CTR は大きく変わる。
  該当する行がない、または合計表示回数が 100 未満のときは空欄にして、その旨を標準エラー出力に出す。
  --include-regex / --exclude-regex を適用したあとのデータで計算する（ブランド名クエリを除外しないと
  目標 CTR が高く出やすい）。

使い方の例:
  python3 striking_distance.py example.jp-Performance-on-Search-2026-09-27.zip -o striking.csv   # zip のまま（クエリの表）
  python3 striking_distance.py Queries.csv -o striking.csv
  python3 striking_distance.py クエリ.csv --exclude-regex "example|エグザンプル" --top 30 -o striking.csv
  python3 striking_distance.py ページ.csv --min-impressions 20 -o striking_pages.csv   # 小規模サイトの例
  python3 striking_distance.py api_export.csv --key query --min-pos 5 --max-pos 15

制約・注意点:
  - Search Console の UI からのエクスポートは最大 1,000 行である。それより多い行が必要なら
    Search Console API や Data Studio（旧 Looker Studio）経由で取得した CSV を使う。
  - 掲載順位は期間内の平均値である。ページ単位の CSV では、そのページに表示された複数のクエリの
    成績がまとめられているため、施策を決めるときはクエリ単位の CSV も確認する。
  - 期間が短いと表示回数が少なく、順位と CTR がぶれやすい。
  - 依存パッケージは pandas だけ（Python 3.9 以上、pandas 2.x / 3.x）。
  - 終了コード: 0 = 正常終了（該当 0 件でも 0）、2 = 入力エラー（ファイルがない、必須列がない、zip に使える表がない、引数が不正など）。
"""

import argparse
import codecs
import csv
import hashlib
import io
import os
import re
import shlex
import sys
import textwrap
import unicodedata
import zipfile
import zlib

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

# Search Console の zip（「エクスポート」で CSV を選んだもの）を展開せずに読むための設定
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06")  # 通常の zip、空の zip
ZIP_TABLES = (
    ("query", "クエリの表", ("クエリ.csv", "Queries.csv")),
    ("page", "ページの表", ("ページ.csv", "Pages.csv")),
)
ZIP_TABLE_LABELS = {key: label for key, label, _names in ZIP_TABLES}
# 展開後の大きさの上限（1 つの表）。画面からのエクスポートは 1 表 1,000 行で、数百 KB にもならない。
# 小さな zip が展開すると膨らむ場合（zip 爆弾）に、メモリを使い切らないための上限
ZIP_MEMBER_LIMIT = 100 * 1024 * 1024
# zip ファイル自体の大きさの上限。zipfile は開くときに中央ディレクトリ（中の名前の一覧）をすべて読むため、
# 選んだ表の上限とは別に設ける。画面からのエクスポートの zip は数 KB〜数百 KB
ZIP_FILE_LIMIT = 100 * 1024 * 1024
ZIP_METHODS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
# zip の読み込みで起きうる例外（壊れた zip、CRC の不一致、名前の文字コードの不整合など）
ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError, OverflowError, NotImplementedError,
              RuntimeError)


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
    """zip（または .xlsx）を受け付けない入力（low_ctr.py の --benchmark）に渡されたときのメッセージ。"""
    return (f"zip ファイル（または Excel の .xlsx）は、この入力には使えません: {path}\n"
            "  対処: CSV を指定してください。Excel で作った表は、CSV 形式で保存し直してください。")


def input_file_error(path, error):
    """入力ファイルを開けない・読めないときの入力エラー。"""
    if isinstance(error, FileNotFoundError):
        return InputError(f"ファイルが見つかりません: {path}\n  対処: パスとファイル名を確認してください。")
    if isinstance(error, IsADirectoryError):
        return InputError(f"ファイルではなくフォルダが指定されています: {path}")
    return InputError(f"ファイルを読み込めません: {path}（{error}）")


def read_bytes(path):
    """ファイル全体をバイト列で読む。"""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise input_file_error(path, e)


def looks_like_zip(data):
    return data[:4] in ZIP_MAGICS


def escape_controls(text):
    """改行などの制御文字を \\n や \\u202e の表記に置き換える（zip の中の名前で、表示の行を偽れないようにする）。"""
    return "".join(
        c.encode("unicode_escape").decode("ascii")
        if unicodedata.category(c)[0] == "C" or unicodedata.category(c) in ("Zl", "Zp") else c
        for c in text)


def zip_member_names(info):
    """zip の中のファイル名の候補を返す（先頭を表示に使う）。

    UTF-8 のフラグがない名前を zipfile は cp437 として読むため、cp437 でバイト列に戻し、UTF-8 → cp932 の順に読み直す
    （macOS で圧縮し直した zip は UTF-8 をフラグなしで、日本語版 Windows の古い圧縮機能は cp932 で書く）。
    読めた候補はすべて残す。filename ではなく orig_filename を使う（Windows では filename の \\ が / に置き換わり、
    cp932 の 2 バイト目の 0x5C が壊れるため）。
    """
    names = []
    if not info.flag_bits & 0x800:
        raw = info.orig_filename.encode("cp437")
        for encoding in ("utf-8", "cp932"):
            try:
                names.append(raw.decode(encoding))
            except UnicodeDecodeError:
                pass
        # Python 3.12 以降は、Unicode Path 拡張フィールド（0x7075）の名前が filename に入る
        if info.filename.replace("\\", "/") != info.orig_filename.replace("\\", "/"):
            names.insert(0, info.filename)
    names.append(info.filename)
    return list(dict.fromkeys(names))


def zip_member_key(name):
    """照合用に、フォルダを除いたファイル名を正規化する（NFKC で分解された濁点をまとめ、英字の大文字・小文字をそろえる）。"""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return unicodedata.normalize("NFKC", base).casefold()


def is_zip_junk(name):
    """フォルダ、macOS が付ける __MACOSX/ の中と ._ で始まるファイル、空の名前なら True。"""
    parts = name.replace("\\", "/").split("/")
    return name.endswith(("/", "\\")) or "__MACOSX" in parts or parts[-1].startswith("._") or not parts[-1]


def format_mb(size):
    """バイト数を MB（1,048,576 バイト）で小数第 1 位まで表す（上限と紛れないように切り上げる）。"""
    tenths = -(-size * 10 // 1048576)
    return f"{tenths // 10:,}.{tenths % 10} MB"


def zip_broken(path, error, member=None):
    """zip を読めないときの入力エラー（壊れている、途中で切れている、名前の文字コードが不正など）。"""
    detail = f"{type(error).__name__}: {error}"
    if member:
        detail = f"{member}: {detail}"
    return InputError(f"zip ファイルを読めません（壊れているか、ダウンロードが途中で止まった可能性があります）: {path}\n"
                      f"  詳細: {escape_controls(detail)}\n"
                      "  対処: Search Console からダウンロードし直してください。展開できる場合は、中の CSV を直接指定しても構いません。")


def find_zip_tables(archive, path):
    """zip の中のクエリの表とページの表を探す。

    戻り値は ({"query": [(ZipInfo, 表示名), ...], "page": [...]}, zip の中の CSV の表示名のリスト)。
    名前は、フォルダを除いた部分が ZIP_TABLES のどれかと一致するものを選ぶ（endswith は ._クエリ.csv も拾うので使わない）。
    """
    entries = []
    for info in archive.infolist():
        names = zip_member_names(info)
        first = unicodedata.normalize("NFC", names[0])
        entries.append((info, first, escape_controls(first), names))
    shown = [first for _info, first, _display, _names in entries]
    if "[Content_Types].xml" in shown and any(n.startswith("xl/") for n in shown):
        raise InputError(f"Excel の .xlsx ファイルのようです: {path}\n"
                         "  対処: Search Console の「エクスポート」では CSV を選んでください。"
                         "Excel で作った表は、CSV 形式で保存し直してください。")
    files = [entry for entry in entries if not is_zip_junk(entry[1])]
    found = {}
    for key, _label, wanted in ZIP_TABLES:
        wanted_keys = {zip_member_key(w) for w in wanted}
        found[key] = [(info, display) for info, _first, display, names in files
                      if any(zip_member_key(n) in wanted_keys for n in names)]
    csvs = [display for _info, first, display, _names in files if first.lower().endswith(".csv")]
    return found, csvs


def zip_not_found(path, key_option, found, csvs):
    """--key に合う表が zip にないときの入力エラー。"""
    order = ("query", "page") if key_option == "auto" else (key_option,)
    wanted = ", ".join(name for key, _label, names in ZIP_TABLES if key in order for name in names)
    listed = (", ".join(csvs[:10]) + (f" ほか {len(csvs) - 10} 件" if len(csvs) > 10 else "")) if csvs else "（なし）"
    if key_option == "auto":
        lines = [f"zip の中にクエリの表もページの表も見つかりません: {path}"]
    else:
        lines = [f"zip の中に{ZIP_TABLE_LABELS[key_option]}が見つかりません: {path}"]
    lines.append(f"  探した名前: {wanted}（英字の大文字・小文字は区別しない。zip の中のフォルダも探す）")
    lines.append(f"  zip の中の CSV: {listed}")
    other = "page" if key_option == "query" else "query"
    if key_option != "auto" and found[other]:
        label = ZIP_TABLE_LABELS[other]
        lines.append(f"  {label}（{found[other][0][1]}）はあります。{label}を使うなら --key {other} を指定してください。")
    lines.append("  対処: Search Console の「検索パフォーマンス」→「エクスポート」で CSV を選んで書き出した zip を"
                 "指定してください。画面の言語が日本語・英語以外の zip は、ファイル名も列名も訳されているため読めません。"
                 "表示言語を日本語か英語にしてから書き出し直してください。名前を変えた CSV を入れた zip は、"
                 "展開して中の CSV を直接指定してください。")
    return InputError("\n".join(lines))


def read_zip_table(archive, path, found, key, limit):
    """zip の中の表を 1 つ読み、(テキスト, 文字コード名, 警告のリスト, 表示名) を返す。

    同じ種類の表が 2 つ以上ある、パスワード付き、対応していない圧縮方式、展開後の大きさが上限を超えるものは
    入力エラーにする。展開後の大きさは中央ディレクトリの申告で先に調べ、読む量も上限 + 1 バイトまでにする。
    """
    if len(found[key]) > 1:
        raise InputError(f"zip の中に{ZIP_TABLE_LABELS[key]}が複数あります: {path}\n"
                         "  候補: " + ", ".join(display for _info, display in found[key]) + "\n"
                         "  対処: zip を展開して、使う CSV を直接指定してください。")
    info, member = found[key][0]
    source = f"{path} の中の {member}"
    if info.flag_bits & 0x1:
        raise InputError(f"パスワード付きの zip は読めません: {source}\n"
                         "  対処: zip を展開して、中の CSV を直接指定してください。")
    if info.compress_type not in ZIP_METHODS:
        raise InputError(f"この zip の圧縮方式（番号 {info.compress_type}）には対応していません: {source}\n"
                         "  対処: zip を展開して、中の CSV を直接指定してください"
                         "（Search Console からダウンロードしたままの zip は読めます）。")
    too_big = ("  対処: 画面からのエクスポートは 1 つの表が最大 1,000 行で、この大きさにはなりません。"
               "API や BigQuery で取った大きなデータは、期間とキー（クエリ・URL）ごとに集計してから渡してください。"
               "集計済みで大きいだけなら、zip を展開して CSV を直接指定してください。")
    if info.file_size > limit:
        raise InputError(f"zip の中の CSV が大きすぎます（展開後 {format_mb(info.file_size)}、"
                         f"上限 {limit // 1048576} MB）: {source}\n" + too_big)
    try:
        with archive.open(info) as f:
            data = f.read(limit + 1)
    except ZIP_ERRORS as e:
        raise zip_broken(path, e, member)
    # zipfile は申告の大きさを超えて返さない（超えると CRC の不一致になる）。zipfile の実装が変わったときのために残す
    if len(data) > limit:
        raise InputError(f"zip の中の CSV が大きすぎます（展開後 {limit // 1048576} MB を超えています）: {source}\n"
                         + too_big)
    text, encoding, warnings = decode_text(data, source)
    return text, encoding, warnings, source


def read_zip_export(fileobj, path, key_option, limit=ZIP_MEMBER_LIMIT):
    """Search Console の zip を展開せずに読み、--key に合う表を (テキスト, 文字コード名, 警告のリスト, 表示名) で返す。

    --key query はクエリの表（クエリ.csv / Queries.csv）、page はページの表（ページ.csv / Pages.csv）を読み、
    もう一方には切り替えない。auto はクエリの表を読む。ただし、クエリの表がヘッダー行だけ（列はそろっていて
    データ行がない）で、ページの表があれば、ページの表を読む（ページで絞り込んだエクスポートでは、クエリの表が
    ヘッダー行だけのことがある）。空のファイルや列の足りない表は切り替えず、そのまま入力エラーにする。
    ディスクには何も書かない。
    """
    try:
        archive = zipfile.ZipFile(fileobj)
    except ZIP_ERRORS as e:
        raise zip_broken(path, e)
    with archive:
        found, csvs = find_zip_tables(archive, path)
        order = ("query", "page") if key_option == "auto" else (key_option,)
        chosen = next((key for key in order if found[key]), None)
        if chosen is None:
            raise zip_not_found(path, key_option, found, csvs)
        text, encoding, warnings, source = read_zip_table(archive, path, found, chosen, limit)
        notes = []
        if key_option == "auto" and chosen == "query" and found["page"]:
            page_member = found["page"][0][1]
            if not is_header_only(text, "query"):
                notes.append(f"注意: zip にはページの表（{page_member}）もあります。--key auto ではクエリの表を使います。"
                             "ページ別に見るなら --key page を付けてください。")
            else:
                query_member = found["query"][0][1]
                text, encoding, warnings, source = read_zip_table(archive, path, found, "page", limit)
                notes.append(f"注意: zip のクエリの表（{query_member}）にデータ行がないため、ページの表（{page_member}）を"
                             "使います。ページで絞り込んだエクスポートでは、クエリの表が空のことがあります。")
    return text, encoding, notes + warnings, source


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


def decode_text(data, source):
    """バイト列の文字コードを判定して (テキスト, 文字コード名, 警告のリスト) を返す。source はメッセージに使う名前。

    BOM があればそれに従う（UTF-8 / UTF-16）。BOM がなければ NUL バイトの位置で BOM なしの UTF-16 を見分け、
    それ以外は UTF-8 → cp932 の順に試す。UTF-8 としてほぼ正しく、壊れたバイトが少しだけある場合は
    そのバイトを置き換えて読み、標準エラー出力に警告を出す（cp932 として読むと全体が文字化けするため）。
    """
    undecodable = InputError(
        f"文字コードを判定できません: {source}\n"
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


def has_data_rows(text):
    """ヘッダー行のほかに、空でない行が 1 行でもあれば True（区切り文字によらず、行の数だけを見る）。"""
    seen = 0
    try:
        for record in csv.reader(io.StringIO(text, newline="")):
            if any(cell.strip() for cell in record):
                seen += 1
                if seen > 1:
                    return True
    except csv.Error:
        return True  # 形式の問題は、この後の parse_csv_text で知らせる
    return False


def is_header_only(text, field):
    """ヘッダー行に field（query など）と必須の指標の列がそろい、データ行が 1 行もなければ True。"""
    if has_data_rows(text):
        return False
    for delimiter, _name in DELIMITERS:
        found, _conflicts = find_columns(first_record(text, delimiter))
        if field in found and all(m in found for m in REQUIRED_METRICS):
            return True
    return False


def zip_file_too_big(path, size=None):
    """zip ファイル自体が上限を超えるときの入力エラー。size が None なら、読んだ量が上限を超えたことだけを示す。"""
    shown = f"{format_mb(size)}、上限 {ZIP_FILE_LIMIT // 1048576} MB" if size is not None else (
        f"上限 {ZIP_FILE_LIMIT // 1048576} MB を超えています")
    return InputError(f"zip ファイルが大きすぎます（{shown}）: {path}\n"
                      "  対処: Search Console の画面からエクスポートした zip は数 KB〜数百 KB です。"
                      "ほかのファイルも入れて圧縮し直した zip なら、展開して使う CSV を直接指定してください。")


def read_text(path):
    """zip を受け付けない入力（low_ctr.py の --benchmark）のファイルを読み、(テキスト, 文字コード名, 警告のリスト) を返す。"""
    data = read_bytes(path)
    if looks_like_zip(data):
        raise InputError(zip_message(path))
    return decode_text(data, path)


def read_export_text(path, key_option):
    """Search Console のエクスポートを読み、(テキスト, 文字コード名, 警告のリスト, 表示名) を返す。

    先頭の 4 バイトで zip かどうかを判定する（拡張子は見ない）。zip なら展開せずに、--key に合う表を読む。
    zip はファイル全体をメモリに読まず、中央ディレクトリと選んだ表だけを読む（シークできない入力だけはメモリに読む）。
    zip ファイル自体が ZIP_FILE_LIMIT を超えるときは、開く前に入力エラーにする。
    表示名は、CSV ならパス、zip なら「x.zip の中の クエリ.csv」。
    """
    try:
        f = open(path, "rb")
    except OSError as e:
        raise input_file_error(path, e)
    with f:
        try:
            head = f.read(4)
            is_zip = head in ZIP_MAGICS
            size = data = None
            if is_zip and f.seekable():
                size = f.seek(0, os.SEEK_END)
                f.seek(0)
            elif is_zip:
                data = head + f.read(ZIP_FILE_LIMIT + 1 - len(head))
            else:
                data = head + f.read()
        except OSError as e:
            raise input_file_error(path, e)
        if is_zip:
            if (size if data is None else len(data)) > ZIP_FILE_LIMIT:
                raise zip_file_too_big(path, size)
            return read_zip_export(f if data is None else io.BytesIO(data), path, key_option)
    text, encoding, warnings = decode_text(data, path)
    return text, encoding, warnings, path


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
    found, _conflicts = find_columns(header)
    if "impressions" in found and "clicks" not in found and "position" not in found:
        lines.append(
            "  対処: 表示回数だけの表は、生成 AI パフォーマンス レポートなど、「検索結果」以外のレポートの"
            "エクスポートのようです。Search Console の「検索パフォーマンス」→「検索結果」からエクスポートし直してください。"
        )
    else:
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
    """GSC のエクスポート（CSV か Search Console の zip）を読み、列を正規化した DataFrame と読み込み情報を返す。

    掲載順位が 0（"0"、"0.0"、"0,0" などを解析した結果が 0）の値は「値なし」とみなす。
    zero_position="exclude" ではその行を除外し、"missing" では掲載順位を NaN にして行を残す。
    """
    if zero_position not in ZERO_POSITION_MODES:
        raise ValueError(f"zero_position: {zero_position!r}")
    text, encoding, warnings, source = read_export_text(path, key_option)
    header, rows, delimiter_name, n_blank = parse_csv_text(text, source)
    found, conflicts = find_columns(header)
    ctr_conflict = conflicts.pop("ctr", None)
    for field in ("query", "page", "clicks", "impressions", "position"):
        if field in conflicts:
            raise InputError(conflict_message(source, field, header, conflicts[field]))
    key, other = resolve_key(found, key_option, source, header)
    missing = [f for f in REQUIRED_METRICS if f not in found]
    if missing:
        raise InputError(missing_columns_message(source, missing, header))
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
        "path": source,
        # decay.py の「同じ内容」の判定に使う（zip は中の時刻が違っても、同じ表なら同じ値になる）
        "content_sha256": hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(),
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
             "クエリ × ページの CSV では、キーにしなかった列も出力に残す。Search Console の zip では、"
             "query はクエリの表、page はページの表を読む（auto はクエリの表。データ行がなければページの表）")
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
# striking_distance.py 固有の処理
# ---------------------------------------------------------------------------

MIN_TARGET_IMPRESSIONS = 100

DESCRIPTION = """\
Search Console のエクスポート CSV から、掲載順位 8〜20 位（1 ページ目の下位〜2 ページ目）で
表示回数が 100 回以上（references/10-gsc-growth.md の手順の基準。小規模サイトは
--min-impressions で下げる）のクエリ（またはページ）を抽出する。

est_extra_clicks は、同じ CSV の中で掲載順位が --target-max-pos 以下の行の
「合計クリック数 / 合計表示回数」を目標 CTR とし、
    表示回数 × max(0, 目標 CTR - 現在の CTR)
で計算した概算値である。外部のベンチマーク値は使わない。
予測ではなく、自サイトの実績 CTR を当てはめた目安として扱うこと。
上位の行の合計表示回数が 100 未満、または該当行がないときは空欄になる。"""

EPILOG = """\
使用例:
  python3 striking_distance.py example.jp-Performance-on-Search-2026-09-27.zip -o striking.csv   # zip のまま（クエリの表）
  python3 striking_distance.py Queries.csv -o striking.csv
  python3 striking_distance.py クエリ.csv --exclude-regex "example|エグザンプル" --top 30 -o striking.csv
  python3 striking_distance.py ページ.csv --min-impressions 20 -o striking_pages.csv   # 小規模サイトの例
  python3 striking_distance.py api_export.csv --key query --min-pos 5 --max-pos 15

入力の注意:
  - Search Console の zip はそのまま渡せる。--key に合わせて中のクエリ.csv / Queries.csv か
    ページ.csv / Pages.csv を読む（auto はクエリの表。データ行がなければページの表）。
  - 列名は英語・日本語のどちらの表記にも対応（Top queries / 上位のクエリ、Top pages / 上位のページ、
    Clicks / クリック数、Impressions / 表示回数、CTR、Position / 掲載順位 など）。
  - 必須列: クエリ列またはページ列、クリック数、表示回数、掲載順位。CTR 列は任意。
  - 文字コードは UTF-8 / cp932 / UTF-16（BOM なしも可）、区切りはカンマ・タブ・セミコロン。
  - 小数点がカンマの表記（3,5% や 8,2）と桁区切り（1,234 / 1.234 / 1 234）は列ごとに判定する。
  - 空・解析できない・負の値の行は除外して件数を表示する。
  - 掲載順位 0 は値なし（画面の「~」「-」がエクスポートで 0 になったもの）とみなし、その行を除外する。
  - Search Console の UI からのエクスポートは最大 1,000 行。それより多い行は Search Console API や
    Data Studio（旧 Looker Studio）経由で取得する。

出力:
  -o のファイルは UTF-8（BOM 付き）、標準出力は UTF-8（BOM なし）。
  列: query または page、（もう一方の列）、clicks, impressions, ctr, ctr_pct, position, est_extra_clicks
  est_extra_clicks の降順、同じ値なら impressions の降順に並べる。表示回数の多い順の上位 30 件で見るときは、
  --top を付けずに出力し、impressions で並べ替えてから上位 30 件を取る（--top は est_extra_clicks の順で切る）。
  CSV インジェクション対策: -o のファイルでは query / page 列で先頭が = + - @（またはタブ・CR）のセルに ' を付ける
  （標準出力には付けない。- で始まる正当なクエリにも付く。--no-sanitize で無効）。Excel で開くなら -o を使う。

終了コード: 0 = 正常（該当 0 件でも 0）、2 = 入力エラー"""


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """--help の折り返しでハイフンの位置では改行しない（ファイル名や User-Agent が途中で切れないようにする）。"""

    def _split_lines(self, text, width):
        return textwrap.wrap(re.sub(r"\s+", " ", text).strip(), width, break_on_hyphens=False)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="striking_distance.py",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=HelpFormatter,
    )
    parser.add_argument("input", help="Search Console のエクスポート。ダウンロードした zip はそのまま渡せる"
                                      "（--key に合わせて中のクエリ.csv / Queries.csv か、ページ.csv / Pages.csv を読む）。"
                                      "展開した CSV や、API などで取った CSV も読める")
    parser.add_argument("--min-pos", type=float, default=8.0, metavar="順位",
                        help="掲載順位の下限。この値以上の行を対象にする（デフォルト: %(default)s）")
    parser.add_argument("--max-pos", type=float, default=20.0, metavar="順位",
                        help="掲載順位の上限。この値以下の行を対象にする（デフォルト: %(default)s）")
    parser.add_argument("--min-impressions", type=int, default=100, metavar="回数",
                        help="表示回数の下限。この値以上の行を対象にする（デフォルト: %(default)s。"
                             "references/10-gsc-growth.md の手順の基準。小規模サイトで候補が少なければ下げる）")
    parser.add_argument("--target-max-pos", type=float, default=3.0, metavar="順位",
                        help="目標 CTR の計算に使う行の掲載順位の上限。この値以下の行の実績 CTR を目標にする"
                             "（デフォルト: %(default)s）")
    add_common_args(parser)
    return parser


def run(args):
    validate_common_args(args)
    if args.min_pos > args.max_pos:
        raise InputError(f"--min-pos（{args.min_pos:g}）が --max-pos（{args.max_pos:g}）より大きくなっています。")
    if args.min_impressions < 0:
        raise InputError("--min-impressions には 0 以上の整数を指定してください。")
    include_re = compile_regex(args.include_regex, "--include-regex")
    exclude_re = compile_regex(args.exclude_regex, "--exclude-regex")
    check_output_path(args.output, [args.input])

    df, info = load_gsc_csv(args.input, args.key, args.ctr_unit, zero_position="exclude")
    log_load_info(info)
    key, other = info["key"], info["other"]
    df, n_regex = apply_filters(df, key, include_re, exclude_re)
    if n_regex:
        log(f"  除外: --include-regex / --exclude-regex による {n_regex} 行")

    # 目標 CTR（同じ CSV の上位表示行の実績）
    top_rows = df[df["position"] <= args.target_max_pos]
    top_clicks = float(top_rows["clicks"].sum())
    top_impressions = float(top_rows["impressions"].sum())
    target_ctr = None
    if len(top_rows) == 0:
        log(f"目標 CTR: 掲載順位 {args.target_max_pos:g} 以下の行がないため計算できません。"
            "est_extra_clicks は空欄にします。")
    elif top_impressions < MIN_TARGET_IMPRESSIONS:
        log(f"目標 CTR: 掲載順位 {args.target_max_pos:g} 以下の行の合計表示回数が {top_impressions:g} で、"
            f"{MIN_TARGET_IMPRESSIONS} 未満のため計算しません。est_extra_clicks は空欄にします。")
    else:
        target_ctr = top_clicks / top_impressions
        log(f"目標 CTR: {target_ctr * 100:.2f}%（掲載順位 {args.target_max_pos:g} 以下の {len(top_rows)} 行、"
            f"クリック数 {top_clicks:g} / 表示回数 {top_impressions:g}。自サイトの実績で、予測値ではない）")

    in_range = (
        (df["position"] >= args.min_pos)
        & (df["position"] <= args.max_pos)
        & (df["impressions"] >= args.min_impressions)
    )
    hits = df[in_range]
    if target_ctr is not None:
        gap = (target_ctr - hits["ctr"]).clip(lower=0.0)
        est = hits["impressions"] * gap
    else:
        est = pd.Series(float("nan"), index=hits.index, dtype=float)
    hits = hits.assign(est_extra_clicks=est, _order=range(len(hits)))
    hits = hits.sort_values(
        ["est_extra_clicks", "impressions", "_order"],
        ascending=[False, False, True],
        na_position="last",
    )
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
    columns["est_extra_clicks"] = hits["est_extra_clicks"].round(1)
    result = pd.DataFrame(columns, index=hits.index).reset_index(drop=True)
    write_csv(result, args.output, args.sanitize)

    n_used = len(df)
    n_excluded, excluded_detail = excluded_summary(info, n_regex)
    log("--- サマリー ---")
    log(f"入力行数: {info['n_input']}")
    log(f"除外行数: {n_excluded}（{excluded_detail}）")
    log(f"判定に使った行数: {n_used}")
    log(f"閾値: 掲載順位 {args.min_pos:g}〜{args.max_pos:g}、表示回数 {args.min_impressions} 以上、"
        f"目標 CTR の基準は掲載順位 {args.target_max_pos:g} 以下")
    log(f"CTR の単位: {info['ctr_note']}")
    log(f"該当件数: {int(in_range.sum())}" + (f"（出力は上位 {len(result)} 件）" if args.top > 0 else ""))
    if target_ctr is not None and len(result):
        log(f"est_extra_clicks の合計（出力分・目安）: {float(result['est_extra_clicks'].sum()):.1f}")
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
