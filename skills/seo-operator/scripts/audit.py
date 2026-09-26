#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests>=2.32",
#     "beautifulsoup4>=4.15",
# ]
# ///
"""
audit.py - サイトマップの URL を1件ずつ取得し、ページごとの基本的な SEO 項目を CSV に書き出す。

目的
  サイトマップ（サイトマップインデックスを含む）に載っている URL について、HTTP ステータス、
  リダイレクト先、title、meta description、h1 の数、canonical、noindex、本文の分量を一覧にする。
  技術監査（references/02-technical-audit.md）と title・meta description の見直し
  （references/07-on-page.md）の入力データを作るために使う。

入力
  sitemap : サイトマップ（またはサイトマップインデックス）の URL、またはローカルファイルのパス。
            - サイトマップインデックスは再帰的にたどる（--max-depth まで）。インデックスが別のインデックスを
              参照している（入れ子の）場合もたどるが、Google は入れ子のサイトマップインデックスをサポート
              しない（Search Console のサイトマップ レポートでエラーになる）ので、標準エラーに警告を出し、
              件数をサマリーに出す。
            - gzip 圧縮（.xml.gz）と、1行1URL のテキストサイトマップにも対応する。
              Content-Encoding: gzip で送られてくる XML も読める。gzip は Google も受け付ける
              （Google の上限は 1 ファイル 50,000 URL、サイズは展開後で 50MB）。
            - 名前空間の有無・接頭辞に関係なく <sitemap><loc> と <url><loc> を読む。
            - RSS 2.0 / Atom のフィードも読む（Google はフィードもサイトマップとして受け付ける）。
              RSS は <item><link>、Atom は <entry><link href>（rel なしか rel="alternate" の最初の1つ）。
              フィードに載るのはふつう最近の URL だけなので、サイト全体の監査には XML サイトマップを使う。
            - loc の前後の空白・改行は除く。相対 URL はサイトマップの URL（リダイレクト後）を基準に
              絶対 URL にする。空の loc と、http / https 以外の URL（mailto: など）はスキップして
              標準エラーに出す。userinfo（user:pass@ など）を含む loc は取得しない（制約・注意点を参照）。
            - 同じ URL は最初の1回だけ扱う。スキームとホストの大文字小文字、デフォルトポート、
              フラグメント、パーセントエンコードの表記の違いは同じ URL とみなす（パスの大文字小文字は区別する）。
            - XML が途中で切れている・壊れている場合は、壊れる前までの URL を使い、標準エラーに警告を出す。
            - UTF-8 以外の文字コード（UTF-16、Shift_JIS など）の XML は UTF-8 に変換して読み、警告を出す。
            - 1ファイルの URL が 50,000 件を超えるか、展開後の大きさが 50MB を超えるサイトマップは、Google の
              上限を超えている旨を標準エラーに警告し、件数をサマリーに出す（処理は安全のための上限 100MB まで続ける）。
            - ローカルファイルを指定した場合も、子サイトマップとページは HTTP で取得する。別のホストかどうかは
              最初の有効な loc のホストを基準に判定する。

出力
  CSV（UTF-8 の BOM 付き。Excel でそのまま開ける）。1行ごとに書き込んで flush するので、
  途中で止めても、それまでの行は残る。列は次の12列だけで、この順に並ぶ。
    url                 サイトマップに載っていた URL
    status              各段のステータスコードを ">" でつないだもの（例: 200 / 301>200 / 302>301>404）。
                        例外時は ERROR:Timeout / ERROR:ConnectionError / ERROR:SSLError /
                        ERROR:TooManyRedirects / ERROR:<例外クラス名>。
                        robots.txt で除外した URL は BLOCKED:robots.txt、内部アドレスに解決されるため
                        取得しなかった URL は BLOCKED:private-address、サイトマップと別のホストのため
                        取得しなかった URL は SKIPPED:other-host、URL（loc かリダイレクト先）に認証情報
                        （userinfo）が含まれるため取得しなかった URL は SKIPPED:credentials-in-url。
    redirect_to         リダイレクトが発生した場合の最終 URL（なければ空欄）
  url・redirect_to・canonical の URL に userinfo（user:pass@ の部分）があれば、*** に伏せて書く
  （例: https://***@example.jp/page）。
    title / title_len   最初の <title>（前後の空白を除き、連続する空白を1つにまとめる）と文字数。
                        HTML の仕様どおり、<title> の中のタグは文字列として扱う
    desc / desc_len     <meta name="description">（name の大文字小文字は区別しない）の content と文字数。
                        複数あれば最初のもの
    h1_count            <h1> の数
    canonical           <head> 内の最初の <link rel="canonical"> の href を絶対 URL にしたもの。HTML になければ
                        HTTP の Link ヘッダーの rel="canonical"。どちらもなければ空欄。
                        異なる canonical が複数あれば最初のものを採用し、標準エラーに注意を出す
    canonical_mismatch  canonical が最終 URL（リダイレクト後）と一致しなければ True、一致すれば False。
                        スキームとホストの大文字小文字、デフォルトポート、フラグメント、
                        パーセントエンコードの有無は無視する。末尾スラッシュやクエリの違いは不一致とする
    robots_noindex      meta robots / meta googlebot / X-Robots-Tag に noindex か none があれば True
    word_count          本文の分量。日本語ページは文字数（空白を除く）、それ以外は単語数（空白区切り）
  HTML でない 2xx のレスポンス（PDF など）は、canonical（Link ヘッダー）、canonical_mismatch、
  robots_noindex（X-Robots-Tag）だけを記録し、title・desc・h1_count・word_count などは空欄にする。
  HTML のページだけを集計するときは、h1_count が空欄でない行に絞る（HTML を解析した行は 0 以上の数になる）。
  4xx・5xx などのページは status と redirect_to だけを記録する。
  title と desc が Excel の1セルの上限（32,767 文字）を超える場合は、先頭 32,767 文字だけを書き出す
  （title_len / desc_len は元の文字数）。
  CSV インジェクション対策として、文字列の列（url, redirect_to, title, desc, canonical）で先頭が
  = + - @（またはタブ・CR）のセルの前に ' を付ける（例: title「-50%オフ」は「'-50%オフ」になる）。
  title_len / desc_len は元の文字数のまま。付けたセルの数はサマリーに出す。「-」で始まる正当な title にも
  付くので、pandas などで読むときは先頭の ' を除くか、--no-sanitize で出し直す。
  進捗（[12/300] 301>200 https://...）とサマリーは標準エラー出力に出す。

使い方
  python3 audit.py https://example.com/sitemap.xml
  python3 audit.py https://example.com/sitemap_index.xml -o audit.csv --limit 200
  python3 audit.py ./sitemap.xml --ignore-robots --count-mode chars

制約・注意点
  - JavaScript を実行しない（描画しない）。HTML の初期レスポンスだけを見る。クライアントサイドで
    描画するサイトでは、title・meta・本文が空または不正確になる。その場合は Search Console の
    URL 検査で「公開 URL をテスト」→「テスト済みのページを表示」から描画後の HTML を確認するか、
    JavaScript のレンダリングに対応したクローラーを使う。
  - ログインが必要なページは取得できない。認証情報（Authorization ヘッダー）は送らない。
    - URL に userinfo（https://user:pass@example.jp/ の user:pass@ の部分。ユーザー名だけの user@ と
      空の @ も含む）があると、requests はそれを Basic 認証として送るため、userinfo を含む URL は取得しない。
      最初のサイトマップ（引数）なら取得せずに終了コード 2、子サイトマップは取得せずに標準エラーに注意を出して
      件数をサマリーに出し、ページは SKIPPED:credentials-in-url にする。リダイレクト先（Location）に userinfo が
      あれば、その段で止める（ページは SKIPPED:credentials-in-url で、redirect_to にリダイレクト先を書く。
      サイトマップは取得できなかった扱い、robots.txt は全許可として扱う）。
    - 標準エラー・CSV・サマリーには元の userinfo を出さない。URL の userinfo は *** に伏せる
      （例: https://***@example.jp/sitemap.xml）。ページの canonical に userinfo があれば、それも伏せる。
    - ~/.netrc（環境変数 NETRC で指定したファイルを含む）の認証情報も使わない。requests の Session は
      trust_env が True だと、.netrc に載っているホストへのリクエストに Basic 認証を自動で付ける。trust_env を
      False にすると .netrc は止まるが、プロキシの環境変数（HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY）と
      macOS・Windows のシステムのプロキシ設定、REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE（社内 CA の証明書）まで
      無視されてしまう。そこで trust_env は True のままにし、Session.auth に何もしない認証（_NoAuth）を設定して
      いる（requests は Session.auth があると .netrc も URL の userinfo も使わない）。プロキシの URL に書いた
      認証情報は、requests がプロキシへの認証（Proxy-Authorization）に使う。
    - Cookie は、サーバーが Set-Cookie で返したものを、同じ実行の中の以降のリクエストで送り返す（requests の
      Session の既定の挙動）。外から Cookie を渡す手段はない。Googlebot は Cookie を保持しないので、Cookie で
      内容が変わるページでは Google の見え方と違うことがある。
  - hreflang、構造化データ、内部リンク、表示速度は調べない。表示速度（Core Web Vitals）は Search Console の
    Core Web Vitals レポートか PageSpeed Insights で確認する。
  - ページのリンクをたどらないので、サイトマップに載っていないページ（孤立ページを含む）は見つけられない。
    サイト全体を調べるときは、リンクをたどるクローラーの出力を同じ観点で分析する。
  - 自社サイトか、許可を得たサイトにだけ使う。アクセス間隔（--delay）を短くしすぎない。
  - Googlebot を詐称しない。User-Agent はツール名がわかる文字列を送る。
  - 内部アドレスには既定でアクセスしない。取得先のホスト名を DNS で解決し、プライベート（100.64.0.0/10 の
    共有アドレスを含む）・ループバック・リンクローカル・予約済み・マルチキャスト・未指定のアドレス
    （IPv4 / IPv6。IPv4 射影の IPv6 と NAT64 のアドレスは中の IPv4 アドレスで判定）が1つでも含まれていれば
    取得しない。サイトマップ・子サイトマップ・robots.txt・ページ・リダイレクトの各段のすべてに適用し、
    接続の直前にも解決し直して確かめる（DNS リバインディング対策）。社内ネットワークのステージング環境の
    監査や、ローカルでのテストでは --allow-private で許可する。プロキシを使う場合、プロキシ自体への接続は
    止めない（取得先の判定は手元の名前解決の結果で行う）。
  - サイトマップに載っている子サイトマップとページのうち、ルートのサイトマップのホスト（リダイレクト後の
    ホストを含む。ローカルファイルなら最初の有効な loc のホスト）と違うホストのものは、既定で取得しない
    （ページは SKIPPED:other-host）。ホスト名だけを比べ、スキームとポートは比べない。sitemaps.org の仕様では
    サイトマップの URL はサイトマップと同じホストに置く決まりで（Google では、Search Console か robots.txt で
    クロス送信を設定した場合が例外）、別のホストの URL はサイトマップの誤りの手がかりになる。
    --allow-other-hosts で取得する。リダイレクトで別のホストに移るのは許可する（内部アドレスの拒否は適用する）。
  - 429 / 503 が返ったら、Retry-After（秒数か HTTP 日付）に従って次のリクエストまで待つ（上限 120 秒）。
    Retry-After がない（または解釈できない）ときは、続いた回数に応じて間隔を --delay の 2 倍、4 倍…と
    延ばす（上限 60 秒）。429 / 503 を返した URL は取り直さず、その status を記録する。429 / 503 が 5 回
    続いたら、サーバーがアクセスを制限しているとみなしてクロールを中断する（書き込み済みの行は残し、
    未取得の件数をサマリーに出す）。
  - robots.txt は RFC 9309 と Google の robots.txt の仕様に沿って、このスクリプト自身が判定する。
    グループは --user-agent の先頭のプロダクトトークン（英字・ハイフン・アンダースコアの並び。
    デフォルトは seo-operator-audit）と大文字小文字を区別せずに照合し、一致するグループ
    （同じトークンのグループが複数あれば結合）、なければ User-agent: * のグループに従う。
    Googlebot 向けのグループは使わないので、Googlebot の判定とは一致しないことがある。
    パスは最長一致（同じ長さなら Allow を優先）で、* と $ のワイルドカードを解釈し、
    日本語のままの表記と %XX の表記の違いをそろえてから照合する。robots.txt は先頭の 500 KiB だけを読む
    （Google と同じ。境目で切れた行は捨てる）。
  - robots.txt が 4xx（429 を除く）なら全許可として扱う（Google も robots.txt がないものとして扱う）。
    5xx・429・タイムアウト・接続エラーのときも全許可として続行するが、標準エラーに警告を出す。
    Google の robots.txt の仕様では、サーバーエラー（5xx。タイムアウトなどのネットワークエラーも含む。
    429 も Google の HTTP ステータスコードの説明ではサーバーエラーとされている）のとき、最初の 12 時間は
    サイトのクロールを止めて robots.txt の取得を試み続け、取得できなければその後の 30 日間は最後に取得できた
    robots.txt を使う（それもなければ制限なしとみなす）。30 日を過ぎてもエラーが続くと、サイトが全体として
    利用できる状態なら robots.txt がないものとして扱い、利用できない状態が続いていればクロールを止める
    （どちらの場合も robots.txt の取得は続ける）。そのため結果は、この間の Google のクロールと一致しない。
  - リダイレクトは最大10回までたどる（Google のクローラーのデフォルトの上限に合わせた）。
    リダイレクト先が robots.txt で除外されていれば、そこで止めて BLOCKED:robots.txt とする。
  - canonical は <head> 側の link 要素だけを採用する。<body> 内のものと、<head> 内でも
    <head> に置けない要素（img・iframe・div など）より後にあるものは無視して、標準エラーに注意を出す
    （Google は <head> 内の rel="canonical" だけを受け付け、<head> に置けない要素を見つけると
    そこで <head> が終わったとみなすため）。
  - robots_noindex は robots と googlebot 向けの指定だけを見る（X-Robots-Tag の
    「otherbot: noindex」のような他のクローラー向けの指定は数えない）。
  - 文字コードは BOM → Content-Type ヘッダーの charset → HTML 内の meta charset の順に使う。
    宣言された文字コードで読めないときは UTF-8・EUC-JP・Shift_JIS（cp932）・ISO-2022-JP を試し、
    標準エラーに注意を出す（ブラウザでは文字化けしている可能性がある）。
  - word_count は分量の目安。auto では行ごとに単位（文字数 / 単語数）が変わりうる。
    単位をそろえたいときは --count-mode chars か words を使う。
  - 1ページあたり 10MB を超える HTML は、そこで打ち切って解析する。

終了コード
  0   正常終了（該当行が0件でも 0）
  2   最初のサイトマップを取得・解析できず URL が1件も得られない（内部アドレスのため取得しなかった場合と、
      リダイレクト先に userinfo があるため取得しなかった場合を含む）、または引数・パスの指定に誤りがある
      （-o が入力のサイトマップと同じファイルの場合も、上書きせずに 2 で止める）。
      最初のサイトマップの URL（引数）に認証情報（userinfo。user:pass@・user@・空の @）が含まれる場合も、
      取得せずに 2 で止める（理由を表示し、URL は https://***@example.jp/sitemap.xml のように伏せて表示する）
  3   429 / 503 が 5 回続いたため中断した（書き込み済みの行は CSV に残り、未取得の件数をサマリーに出す。
      サイトマップの収集中に中断したときは CSV を書き出さない）
  130 Ctrl+C で中断した（書き込み済みの行は CSV に残り、サマリーも出す）

依存: Python 3.9 以上、requests、beautifulsoup4（HTML は html.parser、XML は xml.etree.ElementTree）
"""

import argparse
import codecs
import csv
import datetime
import email.utils
import gzip
import importlib
import io
import ipaddress
import math
import os
import re
import shlex
import socket
import sys
import textwrap
import time
import urllib.request
import warnings
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from html import unescape as html_unescape
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

# macOS 標準の Python（LibreSSL）で urllib3 v2 が毎回出す警告を抑える。HTTPS の取得はできる
# （TLS で失敗した URL は ERROR:SSLError として行に記録される）
warnings.filterwarnings("ignore", message=r".*urllib3 v2 only supports OpenSSL.*")

# パッケージがなくても --help を表示できるように、ここでは終了しない。確認は main() で parse_args の後に行う
try:
    import requests
except ImportError:  # pragma: no cover
    requests = None
try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:  # pragma: no cover
    BeautifulSoup = NavigableString = Tag = None


DEFAULT_USER_AGENT = "seo-operator-audit/1.0 (+SEO audit script; Python requests)"
COLUMNS = [
    "url", "status", "redirect_to", "title", "title_len", "desc", "desc_len",
    "h1_count", "canonical", "canonical_mismatch", "robots_noindex", "word_count",
]
MAX_REDIRECTS = 10
MAX_HTML_BYTES = 10 * 1024 * 1024
MAX_SITEMAP_BYTES = 100 * 1024 * 1024
MAX_SITEMAP_UNCOMPRESSED = 100 * 1024 * 1024
MAX_ROBOTS_BYTES = 500 * 1024          # Google が読む上限（500 KiB）。それより後は無視する
MAX_DEPTH_LIMIT = 50
MAX_DELAY = 3600.0
MAX_TIMEOUT = 3600.0
EXCEL_CELL_LIMIT = 32767               # Excel の1セルに入る最大文字数
# CSV インジェクション対策: 表計算ソフトが数式として解釈しうる先頭の文字（OWASP の推奨に合わせた）と対象の列
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
SANITIZE_COLUMNS = ("url", "redirect_to", "title", "desc", "canonical")
MAX_SKIP_LOG = 10
REDIRECT_CODES = (301, 302, 303, 307, 308)
STATUS_PRIVATE = "BLOCKED:private-address"
STATUS_OTHER_HOST = "SKIPPED:other-host"
STATUS_CREDENTIALS = "SKIPPED:credentials-in-url"
# 出力の前に userinfo を伏せる列（CSV インジェクション対策より先に当てる）
URL_COLUMNS = ("url", "redirect_to", "canonical")
THROTTLE_CODES = (429, 503)
THROTTLE_LIMIT = 5                     # 429 / 503 がこの回数続いたらクロールを中断する
MAX_RETRY_AFTER = 120.0                # Retry-After に従って待つ上限（秒）
MAX_BACKOFF = 60.0                     # Retry-After がないときに延ばす間隔の上限（秒）
EXIT_THROTTLED = 3
GOOGLE_SITEMAP_MAX_URLS = 50000        # Google の上限: 1 ファイル 50,000 URL
GOOGLE_SITEMAP_MAX_BYTES = 50 * 1024 * 1024  # 同じく展開後 50MB（52,428,800 バイト）
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")  # 共有アドレス空間（RFC 6598）
_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")
_DIGITS_RE = re.compile(r"^[0-9]+$")
GZIP_MAGIC = b"\x1f\x8b"
BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
HTML_MIME_TYPES = ("text/html", "application/xhtml+xml")
EXCLUDED_TAGS = ["script", "style", "noscript", "template", "svg", "iframe"]
LAYOUT_TAGS = ["nav", "header", "footer", "aside"]
# Google が <head> 内で有効とする要素。これ以外が現れると、そこで <head> が終わったとみなされる
HEAD_ELEMENTS = frozenset(["title", "meta", "link", "script", "style", "base", "noscript", "template"])
ROBOTS_RULES_WITH_VALUE = {"max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"}
SITEMAP_KIND_LABEL = {"index": "サイトマップインデックス", "urlset": "URL セット",
                      "feed": "フィード（RSS / Atom）", "text": "テキスト"}
# 宣言された文字コードで読めないときに試す順番（EUC-JP を Shift_JIS より先に試す。
# Shift_JIS の文字は EUC-JP としてはほぼ必ず不正になるが、逆は誤って読めてしまうことがあるため）
FALLBACK_CODECS = ["utf-8", "euc_jp", "cp932", "iso2022_jp"]

# HTML の空白（半角スペース・タブ・改行・FF）だけをまとめる。全角スペースは表示に使われるので残す。
_HTML_WS_RE = re.compile(r"[ \t\n\r\f]+")
_URL_CTRL_RE = re.compile(r"[\t\n\r]")
_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?\s*([A-Za-z0-9_.:\-]+)", re.I)
_META_CHARSET_RE = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?\s*([A-Za-z0-9_.:\-]+)", re.I)
_XML_DECL_ENCODING_RE = re.compile(rb"^<\?xml[^>]*?encoding\s*=\s*[\"']([A-Za-z0-9._:\-]+)[\"']")
_XML_DECL_ENCODING_TEXT_RE = re.compile(r"^(<\?xml[^>]*?encoding\s*=\s*[\"'])[^\"']*([\"'])")
_ABS_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_SCHEME_AUTHORITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://[^/?#]*")
_URL_LINE_RE = re.compile(r"^https?://\S+$", re.I)
_DTD_RE = re.compile(rb"<!DOCTYPE|<!ENTITY", re.I)
_HTML_DOC_RE = re.compile(rb"(?is)^(?:<\?xml[^>]*>\s*)?(?:<!--.*?-->\s*)*<(?:!doctype\s+html|html[\s>])")
_PCT_RE = re.compile(r"%[0-9a-fA-F]{2}")
_HOST_PORT_RE = re.compile(r"^(\[[^\]]*\]|[^:]*)(?::(\d*))?$")
_UA_PREFIX_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*:\s*(.*)$", re.S)
# URL の先頭の「scheme://userinfo@」（スキーム省略の //userinfo@ を含む）。authority は最初の / ? # までで、
# userinfo はその中の最後の @ まで（urllib.parse と同じ切り方）
_USERINFO_RE = re.compile(r"^([\x00-\x20]*(?:[A-Za-z][A-Za-z0-9+.\-]*:)?//)[^/?#]*@")
# 文中の URL の userinfo。標準エラーに出す前にすべて伏せる（取りこぼしを防ぐ安全網）
_TEXT_USERINFO_RE = re.compile(r"(?<![A-Za-z0-9+.\-])([A-Za-z][A-Za-z0-9+.\-]*://)[^\s/?#]*@")
# スキームのない「user:pass@host/...」の形の引数（ローカルファイルとして見つからなかったとき）
_BARE_USERINFO_RE = re.compile(r"^[^/\\\s]*@")
_CLOSING_TAG_RE = re.compile(r"</[A-Za-z]")
# ひらがな・カタカナ（半角を含む）・漢字（々〆〇を含む）
_JA_CHAR_RE = re.compile(
    "[぀-ゟ゠-ヿㇰ-ㇿｦ-ﾟ"
    "㐀-䶿一-鿿豈-﫿々-〇\U00020000-\U0002ffff]"
)

# 文字コード名の別名。Shift_JIS は Windows の拡張文字（①、髙 など）を含む cp932 として読む。
_CODEC_CHAINS = {
    "shift_jis": ["cp932"], "shift-jis": ["cp932"], "sjis": ["cp932"], "x-sjis": ["cp932"],
    "ms_kanji": ["cp932"], "csshiftjis": ["cp932"], "windows-31j": ["cp932"], "ms932": ["cp932"],
    "cp932": ["cp932"],
    "euc-jp": ["euc_jp", "euc_jis_2004"], "euc_jp": ["euc_jp", "euc_jis_2004"],
    "eucjp": ["euc_jp", "euc_jis_2004"], "x-euc-jp": ["euc_jp", "euc_jis_2004"],
    "cseucpkdfmtjapanese": ["euc_jp", "euc_jis_2004"],
    "iso-2022-jp": ["iso2022_jp", "iso2022_jp_ext", "iso2022_jp_2"],
    "csiso2022jp": ["iso2022_jp", "iso2022_jp_ext", "iso2022_jp_2"],
    "iso-8859-1": ["cp1252"], "latin1": ["cp1252"], "latin-1": ["cp1252"],
    "us-ascii": ["cp1252"], "ascii": ["cp1252"], "gb2312": ["gbk"],
}


def log(message):
    # type: (str) -> None
    """標準エラーに1行出す。文中の URL の userinfo は伏せる（進捗・注意・サマリーのすべてがここを通る）。"""
    print(mask_userinfo_text(message), file=sys.stderr, flush=True)


def command_line(parts):
    # type: (List[str]) -> str
    """表示用のコマンド行を作る。コピーしてそのまま実行できるように引用する（Windows では空白を含む語だけを " で囲む）。"""
    if os.name == "nt":
        return " ".join('"{}"'.format(p) if (not p or " " in p) else p for p in parts)
    return shlex.join(parts)


def missing_packages(packages, argv):
    # type: (List[str], Optional[List[str]]) -> int
    """必要なパッケージがないときに、用意の方法を表示して終了コード 2 を返す。

    import に失敗した時点で終了すると --help も表示できないため、main() が parse_args の後に呼ぶ。
    """
    script = os.path.abspath(__file__)
    requirements = os.path.join(os.path.dirname(os.path.dirname(script)), "requirements.txt")
    args = list(sys.argv[1:] if argv is None else argv)
    log("エラー: 必要なパッケージが見つかりません（{}）。".format(", ".join(packages)))
    log("次のどちらかの方法で実行してください。")
    log("  uv を使う場合（必要なパッケージを自動で入れて実行します）:")
    log("    uv run " + command_line([script] + args))
    log("  pip を使う場合（仮想環境を作って有効にし、パッケージを入れてから、もう一度実行します）:")
    log("    pip install -r " + command_line([requirements]))
    return 2


# ---------------------------------------------------------------------------
# URL
# ---------------------------------------------------------------------------

def has_userinfo(url):
    # type: (str) -> bool
    """
    URL の authority に userinfo（user:pass@・user@・空の @）があれば True。requests はこれを Basic 認証として
    送るので、取得しない。urllib.parse で解釈できない URL も、先頭の形で判定する（どちらかで見つかれば True）。
    """
    try:
        netloc = urlsplit(url).netloc
    except ValueError:
        netloc = ""
    return "@" in netloc or _USERINFO_RE.match(url) is not None


def mask_userinfo(url):
    # type: (str) -> str
    """URL の userinfo を *** に伏せる（例: https://user:pass@example.jp/a → https://***@example.jp/a）。"""
    masked, count = _USERINFO_RE.subn(r"\1***@", url, count=1)
    if count or not has_userinfo(url):
        return masked
    return "***@" + url.rsplit("@", 1)[1]  # 先頭の形が崩れた URL（念のため）。@ より前をすべて伏せる


def mask_userinfo_text(text):
    # type: (str) -> str
    """文中にある URL の userinfo をすべて *** に伏せる。"""
    return _TEXT_USERINFO_RE.sub(r"\1***@", text) if "@" in text else text


# requests がないときも --help を表示できるように、基底クラスを object にする（その場合は main() で終了する）
class _NoAuth(requests.auth.AuthBase if requests is not None else object):
    """
    何もしない認証。Session.auth に設定すると、requests は ~/.netrc（NETRC）の認証情報と URL の userinfo を
    Basic 認証として付けなくなる（Session.prepare_request は Session.auth があれば .netrc を読まず、
    PreparedRequest.prepare_auth は auth があれば URL の userinfo を使わない）。trust_env は True のままなので、
    プロキシの環境変数とシステムのプロキシ設定、REQUESTS_CA_BUNDLE はそのまま使われる。
    """

    def __call__(self, request):
        # type: (requests.PreparedRequest) -> requests.PreparedRequest
        return request


def split_host_port(netloc):
    # type: (str) -> Tuple[str, str, Optional[str]]
    """netloc を (userinfo@, ホスト, ポート) に分ける。"""
    userinfo = ""
    if "@" in netloc:
        userinfo, netloc = netloc.rsplit("@", 1)
        userinfo += "@"
    match = _HOST_PORT_RE.match(netloc)
    host, port = (match.group(1), match.group(2)) if match else (netloc, None)
    host = host.lower()
    if any(ord(ch) > 127 for ch in host):
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            pass
    return userinfo, host, port


def normalize_url(url):
    # type: (str) -> str
    """
    同じ URL かどうかを比べるための正規化（canonical の比較と、サイトマップの重複除去に使う）。
    スキーム・ホストの小文字化、デフォルトポートとフラグメントの除去、パーセントエンコードの表記の統一。
    末尾スラッシュ、クエリ、パスの大文字小文字はそのまま残す。
    """
    url = (url or "").strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    scheme = parts.scheme.lower()
    userinfo, host, port = split_host_port(parts.netloc)
    if not port or (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
        port_part = ""
    else:
        port_part = ":" + port
    path = parts.path
    if not path and (host or port_part):
        path = "/"
    try:
        path = requests.utils.requote_uri(path)
        query = requests.utils.requote_uri(parts.query)
    except Exception:
        query = parts.query
    result = urlunsplit((scheme, userinfo + host + port_part, path, query, ""))
    return _PCT_RE.sub(lambda m: m.group(0).upper(), result)


def host_key(url):
    # type: (str) -> str
    """別ホストの判定に使うホスト名（小文字、IDN は xn-- の表記、末尾の . を除く）。スキームとポートは見ない。"""
    try:
        netloc = urlsplit(url).netloc
    except ValueError:
        return ""
    return split_host_port(netloc)[1].rstrip(".")


class HostScope(object):
    """
    取得してよいホスト。ルートのサイトマップのホスト（リダイレクト後のホストを含む）、ローカルファイルなら
    最初の有効な loc のホスト。allow_other_hosts が True なら制限しない。
    """

    def __init__(self, allow_other_hosts):
        # type: (bool) -> None
        self.allow = allow_other_hosts
        self.hosts = []  # type: List[str]

    def add(self, url):
        # type: (str) -> None
        key = host_key(url)
        if key and key not in self.hosts:
            self.hosts.append(key)

    def outside(self, url):
        # type: (str) -> bool
        return not self.allow and bool(self.hosts) and host_key(url) not in self.hosts


# ---------------------------------------------------------------------------
# 内部アドレスの拒否
# ---------------------------------------------------------------------------

def internal_address(address):
    # type: (str) -> bool
    """
    内部アドレスなら True。プライベート（100.64.0.0/10 の共有アドレスを含む）・ループバック・リンクローカル・
    予約済み・マルチキャスト・未指定と、IPv6 のサイトローカル。IPv4 射影の IPv6（::ffff:0:0/96）と
    NAT64（64:ff9b::/96）のアドレスは、中の IPv4 アドレスで判定する。解釈できない値は内部とみなす。
    """
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return True
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in _NAT64_PREFIX:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.version == 4 and ip in _SHARED_ADDRESS_SPACE:
        return True
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
            or ip.is_unspecified or (ip.version == 6 and ip.is_site_local))


def resolve_addresses(host, port=None):
    # type: (str, Optional[int]) -> List[str]
    """ホスト名を DNS で解決したアドレスの一覧（重複なし）。IP アドレスならそのまま。解決できなければ例外。"""
    found = []  # type: List[str]
    for info in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        address = str(info[4][0])
        if address not in found:
            found.append(address)
    return found


class AddressGuard(object):
    """取得の前に、取得先のホストが内部アドレスに解決されるかをホストごとに1回だけ調べる。"""

    def __init__(self):
        self._cache = {}  # type: Dict[str, Optional[str]]

    def internal(self, url):
        # type: (str) -> Optional[str]
        """ホストが内部アドレスに解決されれば、そのアドレスを返す。解決できなければ None（取得時のエラーに任せる）。"""
        try:
            host = urlsplit(url).hostname
        except ValueError:
            return None
        if not host:
            return None
        if host not in self._cache:
            try:
                addresses = resolve_addresses(host)
            except (OSError, UnicodeError, ValueError):
                addresses = []
            self._cache[host] = next((a for a in addresses if internal_address(a)), None)
        return self._cache[host]


class PrivateAddressBlocked(Exception):
    """接続先が内部アドレスだった。OSError ではないので、urllib3 に接続エラーとして包まれずに届く。"""

    def __init__(self, host, address):
        # type: (str, str) -> None
        Exception.__init__(self, "{} は内部アドレス {} に解決されます".format(host, address))
        self.address = address


_CONNECTION_GUARD = {"on": False, "exempt": frozenset(), "original": None}  # type: Dict[str, object]


def _guarded_create_connection(address, *args, **kwargs):
    # type: (Tuple[str, int], object, object) -> socket.socket
    """urllib3 の create_connection の代わり。解決したアドレスを確かめてから、そのアドレスに接続する。"""
    original = _CONNECTION_GUARD["original"]
    host, port = address[0], address[1]
    bare = host.strip("[]")
    if not _CONNECTION_GUARD["on"] or bare.lower() in _CONNECTION_GUARD["exempt"]:  # type: ignore[operator]
        return original(address, *args, **kwargs)  # type: ignore[operator]
    addresses = resolve_addresses(bare, port)  # 解決できなければ socket.gaierror（urllib3 が接続エラーにする）
    for resolved in addresses:
        if internal_address(resolved):
            raise PrivateAddressBlocked(bare, resolved)
    error = None  # type: Optional[OSError]
    for resolved in addresses:
        try:
            return original((resolved, port), *args, **kwargs)  # type: ignore[operator]
        except OSError as exc:
            error = exc
    raise error or OSError("名前解決の結果が空です: {}".format(bare))


def set_connection_guard(enabled, exempt_hosts=frozenset()):
    # type: (bool, frozenset) -> bool
    """
    urllib3 が接続を作る関数を包み、接続の直前に名前を解決し直して内部アドレスなら止める（取得前の判定と接続の
    間に DNS の答えが変わる DNS リバインディングへの対策）。exempt_hosts（プロキシのホスト）への接続は止めない。
    包めなければ False を返す（その場合は取得前の判定だけになる）。
    """
    try:
        module = importlib.import_module("urllib3.util.connection")
    except ImportError:
        return False
    current = getattr(module, "create_connection", None)
    if current is None:
        return False
    if current is not _guarded_create_connection:
        _CONNECTION_GUARD["original"] = current
        module.create_connection = _guarded_create_connection  # type: ignore[attr-defined]
    _CONNECTION_GUARD["on"] = enabled
    _CONNECTION_GUARD["exempt"] = frozenset(h.lower() for h in exempt_hosts)
    return True


def proxy_hosts():
    # type: () -> frozenset
    """環境変数とシステム設定にあるプロキシのホスト名。"""
    hosts = set()
    try:
        proxies = urllib.request.getproxies()
    except Exception:
        return frozenset()
    for scheme, value in proxies.items():
        if scheme == "no" or not value:
            continue
        try:
            host = urlsplit(value if "://" in value else "http://" + value).hostname
        except ValueError:
            continue
        if host:
            hosts.add(host.lower())
    return frozenset(hosts)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class FetchResult(object):
    """1つの URL を（リダイレクトをたどって）取得した結果。"""

    def __init__(self):
        self.codes = []            # type: List[int]
        self.final_url = ""        # 最後にリクエストした URL
        self.redirected = False
        self.headers = None        # 最後のレスポンスのヘッダー（requests の CaseInsensitiveDict）
        self.raw_headers = None    # 同じヘッダーの urllib3 版（同名ヘッダーを個別に取り出すため）
        self.content = None        # type: Optional[bytes]
        self.truncated = False
        self.error = None          # type: Optional[str]
        self.error_detail = ""
        self.error_url = ""
        self.blocked_url = None    # type: Optional[str]
        self.private_url = None    # type: Optional[str]  内部アドレスのため取得しなかった URL
        self.private_address = ""
        self.credentials_url = None  # type: Optional[str]  userinfo を含むため取得しなかった URL（伏せた表記）

    def status_text(self):
        # type: () -> str
        if self.error:
            return self.error
        if self.credentials_url:
            return STATUS_CREDENTIALS
        if self.private_url:
            return STATUS_PRIVATE
        if self.blocked_url:
            return "BLOCKED:robots.txt"
        return ">".join(str(code) for code in self.codes)

    def final_code(self):
        # type: () -> int
        return self.codes[-1] if self.codes else 0

    def header_values(self, name):
        # type: (str) -> List[str]
        values = []  # type: List[str]
        raw = self.raw_headers
        if raw is not None and hasattr(raw, "getlist"):
            try:
                values = [v for v in raw.getlist(name) if v]
            except Exception:
                values = []
        if not values and self.headers is not None:
            value = self.headers.get(name)
            if value:
                values = [value]
        return values


def classify_error(exc):
    # type: (BaseException) -> str
    errors = requests.exceptions
    if isinstance(exc, errors.Timeout):
        return "ERROR:Timeout"
    if isinstance(exc, errors.SSLError):
        return "ERROR:SSLError"
    if isinstance(exc, errors.TooManyRedirects):
        return "ERROR:TooManyRedirects"
    if isinstance(exc, errors.ConnectionError):
        inner = exc.args[0] if exc.args else None
        # 本文の読み込み中のタイムアウトは requests が ConnectionError に包んで送出する
        if type(inner).__name__ in ("ReadTimeoutError", "ConnectTimeoutError"):
            return "ERROR:Timeout"
        return "ERROR:ConnectionError"
    return "ERROR:" + type(exc).__name__


def read_limited(resp, max_bytes):
    # type: (requests.Response, int) -> Tuple[bytes, bool]
    buf = bytearray()
    for chunk in resp.iter_content(chunk_size=65536):
        if not chunk:
            continue
        buf.extend(chunk)
        if len(buf) > max_bytes:
            del buf[max_bytes:]
            return bytes(buf), True
    return bytes(buf), False


class CrawlAborted(Exception):
    """429 / 503 が THROTTLE_LIMIT 回続いたあとに、次のリクエストを出そうとした。"""


def retry_after_seconds(value, now=None):
    # type: (Optional[str], Optional[float]) -> Optional[float]
    """Retry-After の値（秒数か HTTP 日付）を、今から待つ秒数にする。解釈できなければ None。"""
    text = (value or "").strip()
    if not text:
        return None
    if _DIGITS_RE.match(text):
        return float(text)
    try:
        when = email.utils.parsedate_to_datetime(text)
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        target = when.timestamp()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return max(0.0, target - (time.time() if now is None else now))


class Fetcher(object):
    """
    すべての HTTP リクエスト（GET のみ）をここから出し、リクエストの間に --delay 秒の間隔を空ける。
    429 / 503 のあとは間隔を延ばし、THROTTLE_LIMIT 回続いたら以後のリクエストを出さない（CrawlAborted）。
    guard があれば、内部アドレスに解決されるホストには各段でリクエストを出さない。
    URL（最初の URL とリダイレクト先）に userinfo があれば、その段でリクエストを出さずに止める。
    """

    def __init__(self, delay, timeout, user_agent, guard=None):
        # type: (float, float, str, Optional[AddressGuard]) -> None
        self.delay = delay
        self.timeout = timeout
        self.guard = guard
        self.session = requests.Session()
        # trust_env は True のまま（プロキシの環境変数・システム設定と REQUESTS_CA_BUNDLE を使うため）にして、
        # ~/.netrc と URL の userinfo による自動の Basic 認証だけを止める（_NoAuth を参照）
        self.session.auth = _NoAuth()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        })
        self._last_done = None  # type: Optional[float]
        self._wait = delay      # 次のリクエストまでに空ける秒数
        self._wait_kind = None  # type: Optional[str]  429 / 503 のあとの待ち方（retry_after / backoff）
        self._sleep = time.sleep
        self.request_count = 0
        self.throttle_streak = 0   # 429 / 503 が続いている回数
        self.throttled = 0         # 429 / 503 の応答の合計
        self.retry_after_waits = 0  # 次のリクエストの前に実際に待った回数（中断した場合は数えない）
        self.backoff_waits = 0
        self.aborted = False

    def _wait_turn(self):
        # type: () -> None
        kind, self._wait_kind = self._wait_kind, None
        if self._last_done is None or self._wait <= 0:
            return
        if kind == "retry_after":
            self.retry_after_waits += 1
        elif kind == "backoff":
            self.backoff_waits += 1
        remaining = self._wait - (time.monotonic() - self._last_done)
        if remaining > 0:
            self._sleep(remaining)

    def _record_status(self, resp):
        # type: (Optional[requests.Response]) -> None
        """429 / 503 なら次のリクエストまでの間隔を延ばす。それ以外（例外を含む）なら元の間隔に戻す。"""
        if resp is None or resp.status_code not in THROTTLE_CODES:
            self.throttle_streak = 0
            self._wait = self.delay
            self._wait_kind = None
            return
        self.throttle_streak += 1
        self.throttled += 1
        header = resp.headers.get("Retry-After")
        retry_after = retry_after_seconds(header)
        if retry_after is not None:
            self._wait = max(self.delay, min(retry_after, MAX_RETRY_AFTER))
            self._wait_kind = "retry_after"
            reason = "Retry-After: {}".format(header.strip())  # type: ignore[union-attr]
        else:
            self._wait = max(self.delay, min(self.delay * 2 ** self.throttle_streak, MAX_BACKOFF))
            self._wait_kind = "backoff"
            reason = "Retry-After なし。{} 回続けて 429 / 503".format(self.throttle_streak)
        if self.throttle_streak >= THROTTLE_LIMIT:
            self.aborted = True
            log("  429 / 503 が {} 回続きました。サーバーがアクセスを制限しているとみなし、クロールを中断します".format(
                self.throttle_streak))
        else:
            log("  ステータス {} のため、次のリクエストまで {:.1f} 秒空けます（{}）".format(
                resp.status_code, self._wait, reason))

    def internal_address(self, url):
        # type: (str) -> Optional[str]
        return self.guard.internal(url) if self.guard is not None else None

    def fetch(self, url, read_body, max_bytes, hop_allowed=None):
        # type: (str, Callable[[requests.Response], bool], int, Optional[Callable[[str], bool]]) -> FetchResult
        """リダイレクトを1段ずつたどる（各段の間にも間隔を空け、各段のコードを記録するため）。"""
        if self.aborted:
            raise CrawlAborted()
        result = FetchResult()
        current = url
        if has_userinfo(current):  # 呼び出し側でも止めているが、ここを通るすべての取得に当てる
            result.credentials_url = mask_userinfo(current)
            return result
        try:
            address = self.internal_address(current)
            if address:
                result.private_url, result.private_address = current, address
                return result
            for _ in range(MAX_REDIRECTS + 1):
                if self.aborted:  # リダイレクト先の robots.txt の取得で中断が決まった場合
                    raise CrawlAborted()
                result.error_url = current
                self._wait_turn()
                self.request_count += 1
                try:
                    resp = self.session.get(current, allow_redirects=False,
                                            timeout=self.timeout, stream=True)
                    try:
                        self._record_status(resp)
                        result.codes.append(resp.status_code)
                        result.final_url = resp.url or current
                        target = self.session.get_redirect_target(resp)
                        if target is not None:
                            target = target.strip()
                        if not target:
                            result.headers = resp.headers
                            result.raw_headers = getattr(resp.raw, "headers", None)
                            if read_body(resp):
                                result.content, result.truncated = read_limited(resp, max_bytes)
                            return result
                    finally:
                        resp.close()
                finally:
                    self._last_done = time.monotonic()
                next_url = requests.utils.requote_uri(urljoin(result.final_url, target))
                result.redirected = True
                if has_userinfo(next_url):  # Location に userinfo（//user:pass@host/ の形を含む）
                    result.credentials_url = mask_userinfo(next_url)
                    return result
                address = self.internal_address(next_url)
                if address:
                    result.private_url, result.private_address = next_url, address
                    return result
                if hop_allowed is not None and not hop_allowed(next_url):
                    result.blocked_url = next_url
                    return result
                current = next_url
            raise requests.exceptions.TooManyRedirects(
                "リダイレクトが {} 回を超えました".format(MAX_REDIRECTS))
        except CrawlAborted:
            raise
        except PrivateAddressBlocked as exc:  # 接続の直前に内部アドレスとわかった（リクエストは出していない）
            self.request_count -= 1
            result.private_url, result.private_address = current, exc.address
            return result
        except Exception as exc:  # 例外で止めず、行に記録して次へ進む
            self._record_status(None)
            result.error = classify_error(exc)
            result.error_detail = "{}: {}".format(type(exc).__name__, exc)
            return result


# ---------------------------------------------------------------------------
# robots.txt（RFC 9309 と Google の robots.txt の仕様）
# ---------------------------------------------------------------------------

_ROBOTS_NEWLINE_RE = re.compile(r"\r\n|\r|\n")
_ROBOTS_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")
_PRODUCT_TOKEN_RE = re.compile(r"^[A-Za-z_-]+")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_URL_ASCII_OK = _UNRESERVED.union(":/?#[]@!$&'()*+,;=%")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def product_token(user_agent):
    # type: (str) -> str
    """User-Agent の先頭のプロダクトトークン（英字・ハイフン・アンダースコアの並び）を小文字で返す。"""
    match = _PRODUCT_TOKEN_RE.match((user_agent or "").strip())
    return match.group(0).lower() if match else ""


def robots_canonical_path(value):
    # type: (str) -> str
    """
    ルールのパスと URL のパスを同じ表記にそろえる（RFC 9309 2.2.2）。
    非 ASCII 文字と URL に使えない ASCII 文字は UTF-8 の %XX に、%xx の16進は大文字にし、
    予約されていない文字（英数字と - . _ ~）の %XX は元の文字に戻す。* と $ はそのまま残す。
    """
    out = []  # type: List[str]
    length = len(value)
    i = 0
    while i < length:
        ch = value[i]
        if ch == "%" and i + 2 < length and value[i + 1] in _HEX_DIGITS and value[i + 2] in _HEX_DIGITS:
            decoded = chr(int(value[i + 1:i + 3], 16))
            out.append(decoded if decoded in _UNRESERVED else "%" + value[i + 1:i + 3].upper())
            i += 3
            continue
        if ch in _URL_ASCII_OK:
            out.append(ch)
        else:
            out.append("".join("%{:02X}".format(b) for b in ch.encode("utf-8", "surrogatepass")))
        i += 1
    return "".join(out)


def robots_target(url):
    # type: (str) -> str
    """URL から照合に使う「パス + ?クエリ」を取り出す（フラグメントは除く）。"""
    rest = url.split("#", 1)[0]
    match = _SCHEME_AUTHORITY_RE.match(rest)
    if match:
        rest = rest[match.end():]
    if not rest.startswith("/"):
        rest = "/" + rest
    return robots_canonical_path(rest)


def robots_pattern_match(path, pattern):
    # type: (str, str) -> bool
    """
    パスの先頭からパターンを照合する。* は0文字以上の任意の文字、末尾の $ は URL の終わり
    （途中の $ はただの文字）。* で区切った断片を左から最短の位置で当てていくので、
    * が多いパターンでも処理時間は線形に近い（正規表現の後戻りによる暴走を避ける）。
    """
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    pieces = pattern.split("*")
    first = pieces[0]
    if not path.startswith(first):
        return False
    if len(pieces) == 1:
        return path == first if anchored else True
    pos = len(first)
    for piece in pieces[1:-1]:
        if not piece:
            continue
        found = path.find(piece, pos)
        if found < 0:
            return False
        pos = found + len(piece)
    last = pieces[-1]
    if anchored:
        return path.endswith(last) and len(path) - len(last) >= pos
    return not last or path.find(last, pos) >= 0


def parse_robots(text):
    # type: (str) -> List[Tuple[List[str], List[Tuple[str, bool]]]]
    """
    robots.txt を (User-agent の値のリスト, [(パターン, allow か)]) のグループのリストにする。
    連続する User-agent 行は1つのグループにまとめ、allow / disallow の後の User-agent 行から
    新しいグループを始める。sitemap など他の行はグループの区切りにしない。
    最初の User-agent より前のルールと、値が空のルールは無視する。
    """
    groups = []  # type: List[Tuple[List[str], List[Tuple[str, bool]]]]
    current = None  # type: Optional[Tuple[List[str], List[Tuple[str, bool]]]]
    in_agent_lines = False
    for raw_line in _ROBOTS_NEWLINE_RE.split(text):
        match = _ROBOTS_LINE_RE.match(raw_line.split("#", 1)[0])
        if not match:
            continue
        field = match.group(1).lower()
        value = match.group(2)
        if field == "user-agent":
            if current is None or not in_agent_lines:
                current = ([], [])
                groups.append(current)
                in_agent_lines = True
            current[0].append(value)
        elif field in ("allow", "disallow"):
            in_agent_lines = False
            if current is None or not value:
                continue
            current[1].append((robots_canonical_path(value), field == "allow"))
    return groups


def _is_global_agent(value):
    # type: (str) -> bool
    return value.startswith("*") and (len(value) == 1 or value[1].isspace())


def _agent_matches(value, token):
    # type: (str, str) -> bool
    match = _PRODUCT_TOKEN_RE.match(value)  # googlebot/1.2 や googlebot* は googlebot として扱う
    return bool(match) and match.group(0).lower() == token


class RobotsRules(object):
    """あるクローラーに適用するルール。長いパターンから順に並べ、同じ長さなら Allow を先にする。"""

    def __init__(self, rules, label):
        # type: (List[Tuple[str, bool]], str) -> None
        self.rules = sorted(rules, key=lambda rule: (-len(rule[0]), not rule[1]))
        self.label = label

    def allowed_path(self, path):
        # type: (str) -> bool
        if path == "/robots.txt":  # robots.txt 自体は常に許可
            return True
        for pattern, allow in self.rules:
            if robots_pattern_match(path, pattern):
                return allow
        return True

    def allowed(self, url):
        # type: (str) -> bool
        return self.allowed_path(robots_target(url))


def select_robots_rules(groups, tokens):
    # type: (List[Tuple[List[str], List[Tuple[str, bool]]]], List[str]) -> RobotsRules
    """
    tokens（具体的なものから順に並べたプロダクトトークン）のうち、一致するグループがある最初の
    トークンのグループをすべて結合して使う。どれも一致しなければ User-agent: * のグループ（これも結合）、
    それもなければルールなし（全許可）。
    """
    for token in tokens:
        if not token:
            continue
        matched = [g for g in groups if any(_agent_matches(a, token) for a in g[0])]
        if matched:
            return RobotsRules([r for g in matched for r in g[1]], "User-agent: {} のグループを適用".format(token))
    matched = [g for g in groups if any(_is_global_agent(a) for a in g[0])]
    if matched:
        return RobotsRules([r for g in matched for r in g[1]], "User-agent: * のグループを適用")
    return RobotsRules([], "該当するグループなし")


def origin_key(url):
    # type: (str) -> Optional[Tuple[str, str, str]]
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.netloc:
        return None
    _, host, port = split_host_port(parts.netloc)
    if not host:
        return None
    return scheme, host, port or ("443" if scheme == "https" else "80")


class RobotsCache(object):
    """ホストごとに robots.txt を1回だけ取得して判定する。"""

    def __init__(self, fetcher, user_agent):
        # type: (Fetcher, str) -> None
        self.fetcher = fetcher
        token = product_token(user_agent)
        self.tokens = [token] if token else []  # type: List[str]
        self._cache = {}  # type: Dict[Tuple[str, str, str], RobotsRules]

    def allowed(self, url):
        # type: (str) -> bool
        key = origin_key(url)
        if key is None:
            return True  # 取得時のエラーとして記録させる
        rules = self._cache.get(key)
        if rules is None:
            rules = self._load(url)
            self._cache[key] = rules
        try:
            return rules.allowed(url)
        except Exception:
            return True

    def _load(self, url):
        # type: (str) -> RobotsRules
        parts = urlsplit(url)
        robots_url = "{}://{}/robots.txt".format(parts.scheme.lower(), parts.netloc.rsplit("@", 1)[-1])
        allow_all = RobotsRules([], "全許可")
        res = self.fetcher.fetch(robots_url, lambda r: 200 <= r.status_code < 300, MAX_ROBOTS_BYTES)
        code = res.final_code()
        if res.credentials_url:
            log("  robots.txt を取得しません。リダイレクト先 {} に認証情報（userinfo）が含まれます。全許可として"
                "扱います: {}".format(res.credentials_url, robots_url))
            return allow_all
        if res.private_url:
            where = "リダイレクト先 {} が".format(res.private_url) if res.redirected else "ホストが"
            log("  robots.txt を取得しません。{}内部アドレス（{}）に解決されます。全許可として扱います: {}".format(
                where, res.private_address, robots_url))
            return allow_all
        if res.error == "ERROR:TooManyRedirects":
            log("  robots.txt のリダイレクトが多すぎます。robots.txt がない（4xx）場合と同じく"
                "全許可として扱います: {}".format(robots_url))
            return allow_all
        if res.error or code >= 500 or code == 429:
            reason = res.error or "ステータス {}".format(res.status_text())
            log("  警告: robots.txt を取得できませんでした（{}）。全許可として続行します: {}\n"
                "    Google はサーバーエラー（5xx。429 とタイムアウトなどのネットワークエラーを含む）のとき、"
                "最初の 12 時間はサイトのクロールを止め、その後 30 日間は最後に取得できた robots.txt を使います"
                "（なければ制限なしとみなす）。30 日を過ぎてもエラーが続くと、サイトが利用できる状態なら "
                "robots.txt がないものとして扱い、利用できない状態が続いていればクロールを止めます。この結果は、"
                "その間の Google のクロールと一致しません。".format(reason, robots_url))
            return allow_all
        if 200 <= code < 300 and res.content is not None:
            text = res.content.decode("utf-8", errors="replace").lstrip("\ufeff")
            if res.truncated:  # 途中で切れた最後の行は、短くなったパスが広すぎるルールになるので捨てる
                text = text[:max(text.rfind("\n"), text.rfind("\r"), 0)]
            rules = select_robots_rules(parse_robots(text), self.tokens)
            log("  robots.txt を読み込みました（{}、ルール {} 件{}）: {}".format(
                rules.label, len(rules.rules),
                "、500 KiB を超えた部分は無視" if res.truncated else "", robots_url))
            return rules
        if 400 <= code < 500:
            log("  robots.txt がありません（ステータス {}）。全許可として扱います: {}".format(
                res.status_text(), robots_url))
        else:
            log("  robots.txt を取得できませんでした（ステータス {}）。全許可として扱います: {}".format(
                res.status_text(), robots_url))
        return allow_all


# ---------------------------------------------------------------------------
# サイトマップ
# ---------------------------------------------------------------------------

class SitemapFormatError(ValueError):
    pass


def local_name(tag):
    # type: (object) -> str
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def clean_loc(text):
    # type: (Optional[str]) -> str
    """loc の前後の空白を除き、途中のタブ・改行も除く（ブラウザの URL の扱いと同じ）。"""
    return _URL_CTRL_RE.sub("", (text or "").strip())


def gunzip_limited(data, limit, notes):
    # type: (bytes, int, List[str]) -> bytes
    """gzip を展開する。途中で切れていれば展開できたところまで、上限を超えたら上限までを返す。"""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
            out = gz.read(limit + 1)
    except (EOFError, OSError, zlib.error) as exc:
        decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)
        buf = bytearray()
        for offset in range(0, len(data), 65536):
            try:
                buf.extend(decomp.decompress(data[offset:offset + 65536]))
            except zlib.error:
                break
            if len(buf) > limit:
                break
        if not buf:
            raise ValueError("gzip を展開できません（{}）".format(exc))
        notes.append("gzip が途中で切れているか壊れています（{}）。展開できたところまでを読みます".format(exc))
        out = bytes(buf)
    if len(out) > limit:
        notes.append("展開後のサイズが上限（{} MB）を超えたため、そこまでを読みます".format(limit // (1024 * 1024)))
        out = out[:limit]
    return out


def xml_to_utf8(body, notes):
    # type: (bytes, List[str]) -> bytes
    """UTF-8 以外で書かれた XML を UTF-8 に変換する（expat は多バイトの文字コードを読めないため）。"""
    if body.startswith(UTF16_BOMS):
        label = "UTF-16"
        text = body.decode("utf-16", errors="replace")  # type: Optional[str]
    else:
        match = _XML_DECL_ENCODING_RE.match(body)
        if not match:
            return body
        label = match.group(1).decode("ascii")
        try:
            if codecs.lookup(label).name in ("utf-8", "ascii"):
                return body
        except LookupError:
            pass
        text = decode_with_label(body, label)
        if text is None:
            raise ValueError("XML の文字コード（{}）を読めません".format(label))
    notes.append("サイトマップの文字コードが {} です。サイトマップは UTF-8 で書く決まりです（sitemaps.org）。"
                 "UTF-8 に変換して読みました".format(label))
    text = text.lstrip("\ufeff")
    text = _XML_DECL_ENCODING_TEXT_RE.sub(r"\1UTF-8\2", text, count=1)
    return text.encode("utf-8")


class _SitemapXmlReader(object):
    """XMLPullParser のイベントから URL を取り出す。途中で壊れていても、それまでの分は残る。"""

    def __init__(self):
        self.kind = None  # type: Optional[str]
        self.item_name = ""
        self.stack = []  # type: List[str]
        self.locs = []  # type: List[str]
        self.empty = 0
        self.root_base = None  # type: Optional[str]

    def consume(self, events):
        # type: (object) -> None
        for event, elem in events:  # type: ignore[attr-defined]
            name = local_name(elem.tag)
            if event == "start":
                if self.kind is None:
                    self._set_root(name, elem)
                self.stack.append(name)
                continue
            if self.stack:
                self.stack.pop()
            if name == self.item_name and self._is_item_level():
                loc = self._extract(elem)
                if loc:
                    self.locs.append(loc)
                else:
                    self.empty += 1
                elem.clear()

    def _set_root(self, name, elem):
        # type: (str, ET.Element) -> None
        if name == "sitemapindex":
            self.kind, self.item_name = "index", "sitemap"
        elif name == "urlset":
            self.kind, self.item_name = "urlset", "url"
        elif name in ("rss", "rdf"):
            self.kind, self.item_name = "feed", "item"
        elif name == "feed":
            self.kind, self.item_name = "feed", "entry"
            self.root_base = elem.get("{http://www.w3.org/XML/1998/namespace}base")
        else:
            raise SitemapFormatError("サイトマップとして認識できない XML です（ルート要素 <{}>）".format(name))

    def _is_item_level(self):
        # type: () -> bool
        if self.item_name == "item":  # RSS 2.0 は rss > channel > item、RSS 1.0 は rdf > item
            return len(self.stack) in (1, 2) and self.stack[-1] in ("channel", "rss", "rdf")
        return len(self.stack) == 1

    def _extract(self, elem):
        # type: (ET.Element) -> str
        if self.item_name in ("url", "sitemap"):
            for sub in elem:
                if local_name(sub.tag) == "loc":
                    return clean_loc(sub.text)
            return ""
        if self.item_name == "item":
            for sub in elem:
                if local_name(sub.tag) == "link":
                    text = clean_loc(sub.text)
                    if text:
                        return text
            return ""
        # Atom: rel がないか rel="alternate" の最初の link。xml:base があれば基準にする
        xml_base = "{http://www.w3.org/XML/1998/namespace}base"
        base = self.root_base
        if elem.get(xml_base):
            base = urljoin(base, elem.get(xml_base)) if base else elem.get(xml_base)
        for sub in elem:
            if local_name(sub.tag) != "link":
                continue
            rel = (sub.get("rel") or "").strip().lower()
            href = clean_loc(sub.get("href"))
            if rel in ("", "alternate") and href:
                link_base = base
                if sub.get(xml_base):
                    link_base = urljoin(base, sub.get(xml_base)) if base else sub.get(xml_base)
                return urljoin(link_base, href) if link_base else href
        return ""


def parse_sitemap_xml(body, notes):
    # type: (bytes, List[str]) -> Tuple[str, List[str], int]
    body = xml_to_utf8(body, notes)
    # サイトマップに DTD は不要。エンティティ展開による攻撃（XXE・billion laughs）を避けるため拒否する
    if _DTD_RE.search(body):
        raise ValueError("DOCTYPE / ENTITY 宣言を含む XML は安全のため読みません")
    parser = ET.XMLPullParser(events=("start", "end"))
    reader = _SitemapXmlReader()
    error = None  # type: Optional[Exception]
    try:
        step = 1024 * 1024
        for offset in range(0, len(body), step):
            parser.feed(body[offset:offset + step])
            reader.consume(parser.read_events())
        parser.close()
        reader.consume(parser.read_events())
    except SitemapFormatError:
        raise
    except (ET.ParseError, ValueError, LookupError) as exc:
        error = exc
    if reader.kind is None or (error is not None and not reader.locs):
        raise ValueError("XML として解析できません（{}）".format(error or "ルート要素がありません"))
    if error is not None:
        notes.append("XML が途中で切れているか壊れています（{}）。壊れる前までの {} 件だけを使います".format(
            error, len(reader.locs)))
    return reader.kind, reader.locs, reader.empty


def parse_sitemap(data, notes=None):
    # type: (bytes, Optional[List[str]]) -> Tuple[str, List[str]]
    """(種類, URL のリスト) を返す。種類は index / urlset / feed / text。警告は notes に足す。"""
    kind, locs, _, _ = parse_sitemap_ex(data, notes if notes is not None else [])
    return kind, locs


def parse_sitemap_ex(data, notes):
    # type: (bytes, List[str]) -> Tuple[str, List[str], int, int]
    """(種類, URL のリスト, 空の loc の数, 展開後のバイト数) を返す。"""
    if data[:2] == GZIP_MAGIC:
        data = gunzip_limited(data, MAX_SITEMAP_UNCOMPRESSED, notes)
    size = len(data)
    body = data.lstrip()
    if body.startswith(b"\xef\xbb\xbf"):
        body = body[3:].lstrip()
    if body.startswith(UTF16_BOMS):
        text = body.decode("utf-16", errors="replace").lstrip("\ufeff").lstrip()
        if text.startswith("<"):
            return parse_sitemap_xml(body, notes) + (size,)
    elif body.startswith(b"<"):
        if _HTML_DOC_RE.match(body[:4096]):
            raise ValueError("HTML のページが返されました（サイトマップではありません）")
        return parse_sitemap_xml(body, notes) + (size,)
    else:
        text = body.decode("utf-8", errors="replace")
    locs = [line.strip() for line in text.splitlines() if _URL_LINE_RE.match(line.strip())]
    if not locs:
        raise ValueError("XML でも1行1URLのテキストでもありません")
    return "text", locs, 0, size


class SitemapCollector(object):
    """サイトマップを再帰的にたどり、ページ URL を出現順・重複なしで集める。"""

    def __init__(self, fetcher, max_depth, limit, scope=None):
        # type: (Fetcher, int, Optional[int], Optional[HostScope]) -> None
        self.fetcher = fetcher
        self.max_depth = max_depth
        self.limit = limit
        self.scope = scope if scope is not None else HostScope(True)
        self.private = 0      # 内部アドレスのため取得しなかったサイトマップ
        self.other_host = 0   # 別のホストのため取得しなかった子サイトマップ
        self.credentials = 0  # userinfo を含むため取得しなかった子サイトマップ（リダイレクト先に含む場合も数える）
        self.over_urls = 0    # Google の上限（50,000 URL）を超えたサイトマップ
        self.over_size = 0    # Google の上限（展開後 50MB）を超えたサイトマップ
        self.visited = set()  # type: set
        self.pages = []  # type: List[str]
        self._seen_pages = set()  # type: set
        self.loaded = 0
        self.failed = 0
        self.skipped = 0
        # 別のインデックスから参照されていたインデックス（入れ子。Google は非対応）
        self.nested = []  # type: List[str]

    def full(self):
        # type: () -> bool
        return self.limit is not None and len(self.pages) >= self.limit

    def collect(self, source, is_local):
        # type: (str, bool) -> bool
        """最初のサイトマップを取得・解析できたら True。"""
        if not is_local:
            self.scope.add(source)
        ok = self._visit(source, 0, is_local)
        if self.skipped > MAX_SKIP_LOG:
            log("  スキップした loc は合計 {} 件です（最初の {} 件だけ表示）".format(self.skipped, MAX_SKIP_LOG))
        return ok

    def _skip(self, message):
        # type: (str) -> None
        self.skipped += 1
        if self.skipped <= MAX_SKIP_LOG:
            log("  " + message)

    def _visit(self, source, depth, is_local=False, parent=None):
        # type: (str, int, bool, Optional[str]) -> bool
        """parent は、このサイトマップを参照していたサイトマップインデックス（最初のサイトマップなら None）。"""
        key = os.path.abspath(source) if is_local else normalize_url(source)
        if key in self.visited:
            log("  サイトマップ: 訪問済みのためスキップ（ループ防止）: {}".format(source))
            return True
        self.visited.add(key)
        loaded = self._load(source, is_local)
        if loaded is None:
            self.failed += 1
            return False
        data, final_url = loaded
        if final_url:
            self.visited.add(normalize_url(final_url))
            if parent is None:  # ルートのサイトマップのリダイレクト後のホストも基準に加える
                self.scope.add(final_url)
        notes = []  # type: List[str]
        try:
            kind, locs, empty, size = parse_sitemap_ex(data, notes)
        except Exception as exc:
            for note in notes:
                log("  注意: {}: {}".format(note, source))
            log("  サイトマップを解析できませんでした（{}）: {}".format(exc, source))
            self.failed += 1
            return False
        for note in notes:
            log("  注意: {}: {}".format(note, source))
        self.loaded += 1
        log("  サイトマップ: {} {} 件: {}".format(SITEMAP_KIND_LABEL[kind], len(locs), source))
        if empty:
            self.skipped += empty
            log("  空の loc（URL のない項目）{} 件をスキップしました: {}".format(empty, source))
        self._check_google_limits(source, len(locs), size, kind)
        base = None if is_local else (final_url or source)
        if kind == "index" and parent is not None:
            # インデックスから参照されるのは子サイトマップだけなので、parent があればインデックスの入れ子
            self.nested.append(source)
            log("  警告: サイトマップインデックスが別のサイトマップインデックスを参照しています（入れ子）: {}"
                "（参照元: {}）。Google は入れ子のサイトマップインデックスをサポートしません（Search Console の"
                "サイトマップ レポートでエラーになります）。このスクリプトはたどって続けます。参照元のインデックスには"
                "子のサイトマップ（URL セット）を直接載せてください".format(source, parent))
        if kind == "index":
            if depth + 1 > self.max_depth:
                log("  深さの上限（--max-depth {}）に達したため、子サイトマップ {} 件はたどりません: {}".format(
                    self.max_depth, len(locs), source))
                return True
            for loc in locs:
                if self.full():
                    break
                child = self._resolve(loc, base)
                if child is None:
                    continue
                if has_userinfo(child):  # Basic 認証として送られるので取得しない（別のホストの判定より先）
                    self.credentials += 1
                    if self.credentials <= MAX_SKIP_LOG:
                        log("  注意: URL に認証情報（userinfo）を含む子サイトマップは取得しません: {}".format(
                            mask_userinfo(child)))
                    continue
                if not self.scope.hosts:  # ローカルファイルは最初の有効な loc のホストを基準にする
                    self.scope.add(child)
                if self.scope.outside(child):
                    self.other_host += 1
                    if self.other_host <= MAX_SKIP_LOG:
                        log("  サイトマップと別のホストの子サイトマップは取得しません（--allow-other-hosts で"
                            "取得）: {}".format(child))
                    continue
                self._visit(child, depth + 1, parent=source)
        else:
            for loc in locs:
                if self.full():
                    break
                url = self._resolve(loc, base)
                if url is None:
                    continue
                if not self.scope.hosts and not has_userinfo(url):  # userinfo 付きは取得しないので基準にしない
                    self.scope.add(url)
                page_key = normalize_url(url)
                if page_key in self._seen_pages:
                    continue
                self._seen_pages.add(page_key)
                self.pages.append(url)
        return True

    def _check_google_limits(self, source, count, size, kind):
        # type: (str, int, int, str) -> None
        if count > GOOGLE_SITEMAP_MAX_URLS:
            self.over_urls += 1
            # サイトマップインデックスの上限も loc 50,000 件。インデックスは入れ子にできないので、分けた先は別のインデックス
            remedy = ("複数のサイトマップインデックスに分けてください（インデックスの入れ子は Google が非対応）"
                      if kind == "index" else "50,000 件以下のファイルに分け、サイトマップインデックスにまとめてください")
            log("  警告: URL が {:,} 件あり、Google の上限（1 ファイル 50,000 件）を超えています。{}"
                "（このスクリプトは全件を読みます）: {}".format(count, remedy, source))
        if size > GOOGLE_SITEMAP_MAX_BYTES:
            self.over_size += 1
            log("  警告: 展開後の大きさが {:,} バイトあり、Google の上限（展開後 50MB = 52,428,800 バイト）を"
                "超えています。ファイルを分けてください（このスクリプトは {} MB まで読みます）: {}".format(
                    size, MAX_SITEMAP_UNCOMPRESSED // (1024 * 1024), source))

    def _resolve(self, loc, base):
        # type: (str, Optional[str]) -> Optional[str]
        shown = mask_userinfo(loc)  # スキップの表示にも userinfo を出さない（ftp://user:pass@... など）
        if _ABS_URL_RE.match(loc):
            url = loc
        elif base is None:
            self._skip("相対 URL の loc はローカルファイルからは解決できないためスキップ: {}".format(shown))
            return None
        else:
            url = urljoin(base, loc)
        try:
            parts = urlsplit(url)
        except ValueError:
            self._skip("URL として解釈できない loc をスキップ: {}".format(shown))
            return None
        if parts.scheme.lower() not in ("http", "https"):
            self._skip("http / https 以外の URL の loc をスキップ: {}".format(shown))
            return None
        if not parts.netloc:
            self._skip("ホスト名のない loc をスキップ: {}".format(shown))
            return None
        return url

    def _load(self, source, is_local):
        # type: (str, bool) -> Optional[Tuple[bytes, str]]
        if is_local:
            try:
                if os.path.getsize(source) > MAX_SITEMAP_BYTES:
                    log("  サイトマップが大きすぎます（{} MB 超）: {}".format(
                        MAX_SITEMAP_BYTES // (1024 * 1024), source))
                    return None
                with open(source, "rb") as fh:
                    return fh.read(), ""
            except OSError as exc:
                log("  サイトマップを読めませんでした（{}）: {}".format(exc, source))
                return None
        res = self.fetcher.fetch(source, lambda r: 200 <= r.status_code < 300, MAX_SITEMAP_BYTES)
        if res.credentials_url:
            self.credentials += 1
            where = "リダイレクト先 {} に".format(res.credentials_url) if res.redirected else "URL に"
            log("  注意: サイトマップを取得しません。{}認証情報（userinfo）が含まれます: {}".format(
                where, mask_userinfo(source)))
            return None
        if res.private_url:
            self.private += 1
            where = "リダイレクト先 {} が".format(res.private_url) if res.redirected else "ホストが"
            log("  サイトマップを取得しません。{}内部アドレス（{}）に解決されます。社内ネットワークのステージング環境や"
                "ローカルでのテストでは --allow-private を付けてください: {}".format(where, res.private_address, source))
            return None
        if res.error:
            log("  サイトマップを取得できませんでした（{}）: {}".format(res.error, source))
            return None
        code = res.final_code()
        if not (200 <= code < 300) or res.content is None:
            log("  サイトマップを取得できませんでした（ステータス {}）: {}".format(res.status_text(), source))
            return None
        if res.truncated:
            log("  サイトマップが {} MB を超えたため途中までしか読んでいません: {}".format(
                MAX_SITEMAP_BYTES // (1024 * 1024), source))
        return res.content, res.final_url


# ---------------------------------------------------------------------------
# HTML の解析
# ---------------------------------------------------------------------------

def clean_text(value):
    # type: (Optional[str]) -> str
    return _HTML_WS_RE.sub(" ", value or "").strip()


def attr_str(element, name):
    # type: (object, str) -> str
    value = element.get(name)  # type: ignore[attr-defined]
    if isinstance(value, list):
        value = " ".join(value)
    return value or ""


def codec_candidates(label):
    # type: (str) -> List[str]
    key = label.strip().strip("\"'").lower()
    names = []  # type: List[str]
    for name in _CODEC_CHAINS.get(key, [key]):
        try:
            names.append(codecs.lookup(name).name)
        except LookupError:
            continue
    return names


def strict_decode(content, label):
    # type: (bytes, str) -> Optional[str]
    for codec in codec_candidates(label):
        try:
            return content.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def decode_with_label(content, label):
    # type: (bytes, str) -> Optional[str]
    text = strict_decode(content, label)
    if text is not None:
        return text
    for codec in codec_candidates(label):
        try:
            return content.decode(codec, errors="replace")
        except LookupError:
            continue
    return None


def header_charset(content_type):
    # type: (str) -> Optional[str]
    match = _CHARSET_RE.search(content_type or "")
    return match.group(1) if match else None


def declared_charset(content):
    # type: (bytes) -> Optional[str]
    """<meta charset> / <meta http-equiv="Content-Type"> の宣言を Beautiful Soup の検出器で読む。"""
    try:
        from bs4.dammit import EncodingDetector
        return EncodingDetector.find_declared_encoding(content, is_html=True) or None
    except Exception:
        match = _META_CHARSET_RE.search(content[:4096])
        return match.group(1).decode("ascii", "replace") if match else None


def decode_html(content, content_type, notes):
    # type: (bytes, str, List[str]) -> Optional[str]
    """
    文字コードの決め方: Content-Type ヘッダーの charset → HTML 内の meta charset の順に、
    エラーなしで読めるものを使う。どちらでも読めなければ UTF-8・EUC-JP・Shift_JIS・ISO-2022-JP を試す。
    宣言がなければ None を返し、Beautiful Soup の自動判定に任せる。requests の r.text は charset が
    ないと ISO-8859-1 とみなして文字化けするので使わない。
    """
    sources = [("Content-Type ヘッダー", header_charset(content_type)), ("meta", declared_charset(content))]
    labels = []  # type: List[Tuple[str, str]]
    seen = set()  # type: set
    for where, label in sources:
        if not label:
            continue
        key = tuple(codec_candidates(label)) or label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append((where, label))
    if not labels:
        return None
    for index, (where, label) in enumerate(labels):
        text = strict_decode(content, label)
        if text is None:
            continue
        if index > 0:
            first_where, first_label = labels[0]
            notes.append("{} の charset（{}）では読めないため、{} の charset（{}）で読みました。"
                         "ブラウザは Content-Type ヘッダーを優先するため、文字化けしている可能性があります".format(
                             first_where, first_label, where, label))
        return text
    declared = "・".join("{}（{}）".format(label, where) for where, label in labels)
    for codec in FALLBACK_CODECS:
        try:
            text = content.decode(codec)
        except UnicodeDecodeError:
            continue
        notes.append("宣言された charset {} では読めない（または認識できない）ため、{} として読みました。"
                     "ブラウザでは文字化けしている可能性があります".format(declared, codec))
        return text
    for where, label in labels:
        text = decode_with_label(content, label)
        if text is not None:
            notes.append("charset {} で読めないバイトを置き換えました（文字化けの可能性）".format(declared))
            return text
    notes.append("charset {} を認識できないため、自動判定で読みました".format(declared))
    return None


def make_soup(content, content_type, notes=None):
    # type: (bytes, str, Optional[List[str]]) -> BeautifulSoup
    """BOM があれば最優先。なければ decode_html の結果を使う。"""
    if content.startswith(BOMS):
        return BeautifulSoup(content, "html.parser")
    text = decode_html(content, content_type, notes if notes is not None else [])
    if text is not None:
        return BeautifulSoup(text, "html.parser")
    return BeautifulSoup(content, "html.parser")


def has_noindex(content):
    # type: (str) -> bool
    for token in re.split(r"[,\s]+", content or ""):
        if token.strip().lower() in ("noindex", "none"):
            return True
    return False


def x_robots_noindex(values):
    # type: (List[str]) -> bool
    """X-Robots-Tag。「googlebot: noindex」のような UA 指定付きは googlebot 向けだけを数える。"""
    for value in values:
        target = None  # type: Optional[str]
        rules = value
        match = _UA_PREFIX_RE.match(value)
        if match and match.group(1).lower() not in ROBOTS_RULES_WITH_VALUE:
            target = match.group(1).lower()
            rules = match.group(2)
        if target not in (None, "googlebot"):
            continue
        if has_noindex(rules):
            return True
    return False


def rcdata_text(element):
    # type: (Tag) -> str
    """
    <title> の中身を文字列として取り出す。HTML の仕様では <title> の中のタグは文字列として扱う。
    Python 3.13 などの html.parser はそのとおりに読むが、3.9 などはタグとして読むので、
    タグがあれば元の表記に戻してそろえる。
    """
    if any(isinstance(child, Tag) for child in element.children):
        return html_unescape(element.decode_contents())
    return element.get_text()


def head_break(head):
    # type: (Tag) -> Optional[object]
    """<head> の直下にある、<head> に置けない要素か文字列（あればそこで <head> が終わる）。"""
    for child in head.children:
        if isinstance(child, Tag):
            if child.name.lower() == "body":  # </head> の書き忘れ（html.parser では <body> が <head> の子になる）
                return None
            if child.name.lower() not in HEAD_ELEMENTS:
                return child
        elif type(child) is NavigableString and child.strip(" \t\n\r\f"):
            return child
    return None


def describe_node(node):
    # type: (object) -> str
    if isinstance(node, Tag):
        return "<{}>".format(node.name)
    text = clean_text(str(node))
    return "文字列「{}」".format(text[:20] + ("…" if len(text) > 20 else ""))


def canonical_links_after_break(soup):
    # type: (BeautifulSoup) -> Tuple[set, str]
    """<head> に置けない要素より後にある link 要素の id の集合と、その要素の説明。"""
    head = soup.find("head")
    if head is None:
        return set(), ""
    breaker = head_break(head)
    if breaker is None:
        return set(), ""
    ids = set()
    started = False
    for child in head.children:
        if child is breaker:
            started = True
        if started and isinstance(child, Tag):
            if child.name == "link":
                ids.add(id(child))
            for link in child.find_all("link"):
                ids.add(id(link))
    return ids, describe_node(breaker)


def find_canonicals(soup, final_url, notes):
    # type: (BeautifulSoup, str, List[str]) -> List[str]
    """<head> 内の rel="canonical" の href（絶対 URL）を出現順に返す。"""
    base_url = final_url
    base_el = soup.find("base", href=True)
    if base_el is not None and attr_str(base_el, "href").strip():
        base_url = urljoin(final_url, _URL_CTRL_RE.sub("", attr_str(base_el, "href").strip()))
    after_break, breaker = canonical_links_after_break(soup)
    found = []  # type: List[str]
    ignored_in_body = None  # type: Optional[str]
    ignored_after_break = None  # type: Optional[str]
    for link in soup.find_all("link"):
        rels = link.get("rel") or []
        if isinstance(rels, str):
            rels = rels.split()
        if "canonical" not in [r.lower() for r in rels]:
            continue
        href = _URL_CTRL_RE.sub("", attr_str(link, "href").strip())
        if not href:
            continue
        if link.find_parent("body") is not None:
            if ignored_in_body is None:
                ignored_in_body = href
            continue
        if id(link) in after_break:
            if ignored_after_break is None:
                ignored_after_break = href
            continue
        found.append(urljoin(base_url, href))
    if ignored_in_body is not None:
        notes.append('<body> 内の rel="canonical" を無視しました'
                     '（Google は <head> 内のものだけを受け付ける）: {}'.format(ignored_in_body))
    if ignored_after_break is not None:
        notes.append('<head> に置けない要素 {} より後にある rel="canonical" を無視しました'
                     '（Google はそこで <head> が終わったとみなす）: {}'.format(breaker, ignored_after_break))
    elif breaker:
        notes.append("<head> に置けない要素 {} があります。Google はそこで <head> が終わったとみなし、"
                     "それより後の <head> 内の要素を読みません".format(breaker))
    return found


def canonical_from_headers(values, base_url):
    # type: (List[str], str) -> List[str]
    """Link ヘッダーの rel="canonical" の URL を出現順に返す。"""
    found = []  # type: List[str]
    for value in values:
        try:
            links = requests.utils.parse_header_links(value)
        except Exception:
            continue
        for link in links:
            rels = (link.get("rel") or "").lower().split()
            target = _URL_CTRL_RE.sub("", (link.get("url") or "").strip())
            if "canonical" in rels and target:
                found.append(urljoin(base_url, target))
    return found


def distinct_urls(urls):
    # type: (List[str]) -> List[str]
    seen = []  # type: List[str]
    for url in urls:
        key = normalize_url(url)
        if key not in seen:
            seen.append(key)
    return seen


def choose_canonical(html_canonicals, header_canonicals, notes):
    # type: (List[str], List[str], List[str]) -> str
    """
    方針: HTML の <head> 内の最初のものを採用し、なければ Link ヘッダーの最初のもの。
    異なる URL が複数指定されていれば（HTML 内・Link ヘッダー内・両者の間のいずれでも）注意を出す。
    """
    if len(distinct_urls(html_canonicals)) > 1:
        notes.append('<head> 内に異なる rel="canonical" が {} 個あります。最初のものを採用しました: {}'.format(
            len(distinct_urls(html_canonicals)), " / ".join(html_canonicals)))
    if len(distinct_urls(header_canonicals)) > 1:
        notes.append('Link ヘッダーに異なる rel="canonical" が {} 個あります。最初のものを採用しました: {}'.format(
            len(distinct_urls(header_canonicals)), " / ".join(header_canonicals)))
    if html_canonicals and header_canonicals and \
            normalize_url(html_canonicals[0]) != normalize_url(header_canonicals[0]):
        notes.append("HTML と Link ヘッダーで canonical が異なります（HTML を採用）: {} / {}".format(
            html_canonicals[0], header_canonicals[0]))
    if html_canonicals:
        return html_canonicals[0]
    return header_canonicals[0] if header_canonicals else ""


def mismatch_of(canonical, final_url):
    # type: (str, str) -> object
    if not canonical:
        return ""
    return normalize_url(canonical) != normalize_url(final_url)


def is_japanese_page(soup, compact_text):
    # type: (BeautifulSoup, str) -> bool
    html_el = soup.find("html")
    if html_el is not None:
        lang = (attr_str(html_el, "lang") or attr_str(html_el, "xml:lang")).strip().lower()
        if lang == "ja" or lang.startswith("ja-") or lang.startswith("ja_"):
            return True
    if not compact_text:
        return False
    return len(_JA_CHAR_RE.findall(compact_text)) / float(len(compact_text)) >= 0.2


def count_body(soup, count_mode):
    # type: (BeautifulSoup, str) -> Tuple[int, str]
    """本文の分量を数える。soup を書き換えるので、ほかの項目を取り出したあとに呼ぶ。"""
    root = soup.find("main")
    if root is None:
        root = soup.find("article")
    if root is None:
        root = soup.find("body")
        if root is None:
            root = soup
            for element in root.find_all(["head", "title", "meta", "link"]):
                element.extract()
        for element in root.find_all(LAYOUT_TAGS):
            element.extract()
    for element in root.find_all(EXCLUDED_TAGS):
        element.extract()
    text = root.get_text(" ")
    compact = re.sub(r"\s+", "", text)
    mode = count_mode
    if mode == "auto":
        mode = "chars" if is_japanese_page(soup, compact) else "words"
    if mode == "chars":
        return len(compact), "chars"
    return len(text.split()), "words"


def sanitize_cell(value):
    # type: (object) -> Tuple[object, bool]
    """CSV インジェクション対策。先頭が = + - @ タブ CR の文字列の前に ' を付ける。戻り値は (値, 付けたか)。

    ' を付けて Excel の1セルの上限を超える場合は、末尾を1文字削って上限に収める。
    """
    if not isinstance(value, str) or not value.startswith(FORMULA_PREFIXES):
        return value, False
    return ("'" + value)[:EXCEL_CELL_LIMIT], True


def mask_row_userinfo(row):
    # type: (Dict[str, object]) -> None
    """URL_COLUMNS の列の URL の userinfo を *** に伏せる（row を書き換える）。CSV に書く前に必ず通す。"""
    for column in URL_COLUMNS:
        value = row[column]
        if isinstance(value, str) and value:
            row[column] = mask_userinfo(value)


def sanitize_row(row):
    # type: (Dict[str, object]) -> int
    """SANITIZE_COLUMNS の列に sanitize_cell を当てる（row を書き換える）。戻り値は ' を付けたセルの数。"""
    count = 0
    for column in SANITIZE_COLUMNS:
        row[column], changed = sanitize_cell(row[column])
        count += int(changed)
    return count


def cell_text(value, column, notes):
    # type: (str, str, List[str]) -> str
    if len(value) <= EXCEL_CELL_LIMIT:
        return value
    notes.append("{} が {} 文字あり、Excel の1セルの上限（{} 文字）を超えるため、CSV には先頭だけを"
                 "書き出しました（{}_len は元の文字数）".format(column, len(value), EXCEL_CELL_LIMIT, column))
    return value[:EXCEL_CELL_LIMIT]


def analyze_html(res, content_type, count_mode, notes):
    # type: (FetchResult, str, str, List[str]) -> Tuple[Dict[str, object], str]
    soup = make_soup(res.content or b"", content_type, notes)
    final_url = res.final_url

    titles = [el for el in soup.find_all("title") if el.find_parent("svg") is None]  # <svg><title> は除く
    title = clean_text(rcdata_text(titles[0])) if titles else ""
    if len(titles) > 1:
        notes.append("<title> が {} 個あります。最初のものを採用しました".format(len(titles)))
    if _CLOSING_TAG_RE.search(title):
        notes.append("title にタグのような文字列が含まれています（</title> の閉じ忘れか、"
                     "< のエスケープ漏れの可能性）")

    metas = soup.find_all("meta")
    descs = [meta for meta in metas if attr_str(meta, "name").strip().lower() == "description"]
    desc = clean_text(attr_str(descs[0], "content")) if descs else ""
    if len(descs) > 1:
        notes.append('<meta name="description"> が {} 個あります。最初のものを採用しました'.format(len(descs)))

    h1_count = len(soup.find_all("h1"))

    canonical = choose_canonical(find_canonicals(soup, final_url, notes),
                                 canonical_from_headers(res.header_values("Link"), final_url), notes)

    noindex = False
    for meta in metas:
        name = attr_str(meta, "name").strip().lower()
        if name in ("robots", "googlebot") and has_noindex(attr_str(meta, "content")):
            noindex = True
            break
    if not noindex and x_robots_noindex(res.header_values("X-Robots-Tag")):
        noindex = True

    word_count, unit = count_body(soup, count_mode)
    fields = {
        "title": cell_text(title, "title", notes), "title_len": len(title),
        "desc": cell_text(desc, "desc", notes), "desc_len": len(desc),
        "h1_count": h1_count,
        "canonical": canonical, "canonical_mismatch": mismatch_of(canonical, final_url),
        "robots_noindex": noindex,
        "word_count": word_count,
    }  # type: Dict[str, object]
    return fields, unit


def header_fields(res, notes):
    # type: (FetchResult, List[str]) -> Dict[str, object]
    """HTML でないレスポンス（PDF など）で、HTTP ヘッダーから分かる項目だけを返す。"""
    canonical = choose_canonical([], canonical_from_headers(res.header_values("Link"), res.final_url), notes)
    return {
        "canonical": canonical,
        "canonical_mismatch": mismatch_of(canonical, res.final_url),
        "robots_noindex": x_robots_noindex(res.header_values("X-Robots-Tag")),
    }


def mime_of(content_type):
    # type: (Optional[str]) -> str
    return (content_type or "").split(";", 1)[0].strip().lower()


def looks_like_html(content):
    # type: (bytes) -> bool
    head = content[:1024].lstrip().lower()
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:].lstrip()
    return head.startswith(b"<!doctype html") or b"<html" in head


def audit_page(url, fetcher, robots, count_mode, scope=None):
    # type: (str, Fetcher, Optional[RobotsCache], str, Optional[HostScope]) -> Tuple[Dict[str, object], Dict[str, object]]
    """1ページを監査する。429 / 503 が続いて中断が決まっていれば CrawlAborted を送出する。"""
    row = dict.fromkeys(COLUMNS, "")  # type: Dict[str, object]
    row["url"] = url
    notes = []  # type: List[str]
    info = {"parsed": False, "headers_only": False, "unit": None, "notes": notes}  # type: Dict[str, object]

    if has_userinfo(url):  # 別のホスト・内部アドレス・robots.txt の判定より先（どれも取得しないが理由を優先する）
        row["url"] = mask_userinfo(url)
        row["status"] = STATUS_CREDENTIALS
        notes.append("URL に認証情報（userinfo）が含まれるため取得しませんでした（Basic 認証として送られるのを防ぐため）")
        return row, info
    if scope is not None and scope.outside(url):
        row["status"] = STATUS_OTHER_HOST
        return row, info
    address = fetcher.internal_address(url)
    if address:
        row["status"] = STATUS_PRIVATE
        notes.append("ホストが内部アドレス（{}）に解決されるため取得しませんでした（--allow-private で許可）".format(
            address))
        return row, info
    if robots is not None and not robots.allowed(url):
        row["status"] = "BLOCKED:robots.txt"
        return row, info

    def want_body(resp):
        # type: (requests.Response) -> bool
        if not (200 <= resp.status_code < 300):
            return False
        mime = mime_of(resp.headers.get("Content-Type"))
        return mime in HTML_MIME_TYPES or mime == ""

    res = fetcher.fetch(url, want_body, MAX_HTML_BYTES,
                        robots.allowed if robots is not None else None)
    row["status"] = res.status_text()
    if res.error:
        where = "（{} で発生）".format(res.error_url) if res.error_url and res.error_url != url else ""
        notes.append("{}{}".format(res.error_detail, where))
        return row, info
    if res.credentials_url:
        row["redirect_to"] = res.credentials_url
        notes.append("リダイレクト先の URL に認証情報（userinfo）が含まれるため取得しませんでした: {}".format(
            res.credentials_url))
        return row, info
    if res.private_url:
        if res.redirected:
            row["redirect_to"] = res.private_url
        notes.append("{}内部アドレス（{}）に解決されるため取得しませんでした（--allow-private で許可）{}".format(
            "リダイレクト先が" if res.redirected else "接続の直前に", res.private_address,
            ": " + res.private_url if res.redirected else ""))
        return row, info
    if res.blocked_url:
        row["redirect_to"] = res.blocked_url
        notes.append("リダイレクト先が robots.txt で除外されているため取得しませんでした: {}".format(
            res.blocked_url))
        return row, info
    if res.redirected:
        row["redirect_to"] = res.final_url
    code = res.final_code()
    if code in REDIRECT_CODES:
        notes.append("ステータス {} ですが Location ヘッダーがない（空の）ため、リダイレクト先をたどれません".format(code))
    if not (200 <= code < 300):
        return row, info  # 4xx・5xx などは status と redirect_to だけ
    content_type = res.headers.get("Content-Type", "") if res.headers is not None else ""
    is_html = res.content is not None and (
        mime_of(content_type) in HTML_MIME_TYPES or looks_like_html(res.content))
    if not is_html:  # PDF など: HTTP ヘッダーの canonical と X-Robots-Tag だけ
        row.update(header_fields(res, notes))
        info["headers_only"] = True
        return row, info
    if res.truncated:
        notes.append("HTML が {} MB を超えたため、先頭だけを解析しました".format(
            MAX_HTML_BYTES // (1024 * 1024)))
    try:
        fields, unit = analyze_html(res, content_type, count_mode, notes)
    except Exception as exc:
        notes.append("HTML を解析できませんでした（{}: {}）。HTTP ヘッダーの項目だけを記録します".format(
            type(exc).__name__, exc))
        row.update(header_fields(res, notes))
        info["headers_only"] = True
        return row, info
    row.update(fields)
    info["parsed"] = True
    info["unit"] = unit
    return row, info


# ---------------------------------------------------------------------------
# 集計と出力
# ---------------------------------------------------------------------------

class Stats(object):
    def __init__(self):
        self.rows = 0
        self.status = Counter()  # type: Counter
        self.parsed = 0
        self.headers_only = 0
        self.noindex = 0
        self.mismatch = 0
        self.no_title = 0
        self.no_desc = 0
        self.h1_zero = 0
        self.h1_multi = 0
        self.errors = 0
        self.blocked = 0      # robots.txt で除外
        self.private = 0      # 内部アドレスのため取得しなかった
        self.other_host = 0   # サイトマップと別のホストのため取得しなかった
        self.credentials = 0  # URL（loc かリダイレクト先）に userinfo があるため取得しなかった
        self.sanitized = 0
        self.units = Counter()  # type: Counter

    def add(self, row, info):
        # type: (Dict[str, object], Dict[str, object]) -> None
        self.rows += 1
        status = str(row["status"])
        self.status[status] += 1
        if status.startswith("ERROR:"):
            self.errors += 1
        if status == "BLOCKED:robots.txt":
            self.blocked += 1
        elif status == STATUS_PRIVATE:
            self.private += 1
        elif status == STATUS_OTHER_HOST:
            self.other_host += 1
        elif status == STATUS_CREDENTIALS:
            self.credentials += 1
        if row["robots_noindex"] is True:
            self.noindex += 1
        if row["canonical_mismatch"] is True:
            self.mismatch += 1
        if info["headers_only"]:
            self.headers_only += 1
        if info["parsed"]:
            self.parsed += 1
            if row["title_len"] == 0:
                self.no_title += 1
            if row["desc_len"] == 0:
                self.no_desc += 1
            if row["h1_count"] == 0:
                self.h1_zero += 1
            elif isinstance(row["h1_count"], int) and row["h1_count"] > 1:
                self.h1_multi += 1
            self.units[info["unit"]] += 1


def print_summary(stats, total, fetcher, collector, output, elapsed, state, sanitize=True):
    # type: (Stats, int, Fetcher, SitemapCollector, str, float, str, bool) -> None
    """state は中断の理由（Ctrl+C / 429・503 の連続。正常終了なら空）。"""
    log("")
    log("=== サマリー ===")
    if state:
        state = "（{}。未取得 {} 件）".format(state, total - stats.rows)
    log("処理した URL: {} / {} 件{}".format(stats.rows, total, state))
    log("サイトマップ: 読み込み {} 件 / 失敗 {} 件 / スキップした loc {} 件".format(
        collector.loaded, collector.failed, collector.skipped))
    log("入れ子のサイトマップインデックス（Google は非対応。Search Console でエラー）: {} 件".format(
        len(collector.nested)))
    log("Google の上限を超えるサイトマップ: URL 50,000 件超 {} 件 / 展開後 50MB 超 {} 件".format(
        collector.over_urls, collector.over_size))
    log("HTTP リクエスト: {} 回 / 所要時間: {:.1f} 秒".format(fetcher.request_count, elapsed))
    log("429 / 503 の応答: {} 回（Retry-After に従って待った: {} 回 / 間隔を延ばした: {} 回）".format(
        fetcher.throttled, fetcher.retry_after_waits, fetcher.backoff_waits))
    log("ステータス別:")
    for status, count in sorted(stats.status.items(), key=lambda kv: (-kv[1], kv[0])):
        log("  {}: {}".format(status, count))
    log("HTML を解析したページ: {} 件".format(stats.parsed))
    log("HTML 以外（HTTP ヘッダーの canonical と X-Robots-Tag だけを記録）: {} 件".format(stats.headers_only))
    log("noindex: {} 件".format(stats.noindex))
    log("canonical 不一致: {} 件".format(stats.mismatch))
    log("title なし（空を含む）: {} 件".format(stats.no_title))
    log("meta description なし（空を含む）: {} 件".format(stats.no_desc))
    log("h1 が1個でないページ: {} 件（0個: {} / 2個以上: {}）".format(
        stats.h1_zero + stats.h1_multi, stats.h1_zero, stats.h1_multi))
    log("エラー: {} 件".format(stats.errors))
    log("robots.txt で除外: {} 件".format(stats.blocked))
    if fetcher.guard is not None:
        log("内部アドレスのため取得しなかった（{}）: ページ {} 件 / サイトマップ {} 件".format(
            STATUS_PRIVATE, stats.private, collector.private))
    else:
        log("内部アドレスの拒否: 無効（--allow-private）")
    if collector.scope.allow:
        log("別のホストの URL の除外: 無効（--allow-other-hosts）")
    else:
        log("サイトマップと別のホストのため取得しなかった（{}）: ページ {} 件 / 子サイトマップ {} 件"
            "（基準のホスト: {}）".format(STATUS_OTHER_HOST, stats.other_host, collector.other_host,
                                    "・".join(collector.scope.hosts) or "なし"))
    log("URL に認証情報（userinfo）を含むため取得しなかった（{}）: ページ {} 件 / 子サイトマップ {} 件"
        "（リダイレクト先に含む場合を含む。Authorization ヘッダーと ~/.netrc の認証情報は送らない）".format(
            STATUS_CREDENTIALS, stats.credentials, collector.credentials))
    log("word_count の単位: 文字数 {} 件 / 単語数 {} 件".format(
        stats.units.get("chars", 0), stats.units.get("words", 0)))
    if sanitize:
        log("CSV インジェクション対策で ' を付けたセル: {} 個（url・redirect_to・title・desc・canonical の"
            "先頭が = + - @ タブ CR のもの。--no-sanitize で無効）".format(stats.sanitized))
    else:
        log("CSV インジェクション対策: 無効（--no-sanitize）")
    log("出力: {}".format(output))


def open_output(path):
    # type: (str) -> io.TextIOWrapper
    return open(path, "w", newline="", encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# 引数
# ---------------------------------------------------------------------------

def _parse_number(text, kind, expected):
    # type: (str, type, str) -> float
    try:
        value = kind(text.strip())
    except ValueError:
        raise argparse.ArgumentTypeError("{}を指定してください: {}".format(expected, text))
    if isinstance(value, float) and not math.isfinite(value):
        raise argparse.ArgumentTypeError("{}を指定してください: {}".format(expected, text))
    return value


def delay_seconds(text):
    # type: (str) -> float
    expected = "0 以上 {:g} 以下の秒数".format(MAX_DELAY)
    value = _parse_number(text, float, expected)
    if value < 0 or value > MAX_DELAY:
        raise argparse.ArgumentTypeError("{}を指定してください: {}".format(expected, text))
    return value


def timeout_seconds(text):
    # type: (str) -> float
    expected = "0 より大きく {:g} 以下の秒数".format(MAX_TIMEOUT)
    value = _parse_number(text, float, expected)
    if value <= 0 or value > MAX_TIMEOUT:
        raise argparse.ArgumentTypeError("{}を指定してください: {}".format(expected, text))
    return value


def positive_int(text):
    # type: (str) -> int
    expected = "1 以上の整数"
    value = int(_parse_number(text, int, expected))
    if value < 1:
        raise argparse.ArgumentTypeError("{}を指定してください: {}".format(expected, text))
    return value


def depth_int(text):
    # type: (str) -> int
    expected = "0 から {} までの整数".format(MAX_DEPTH_LIMIT)
    value = int(_parse_number(text, int, expected))
    if value < 0 or value > MAX_DEPTH_LIMIT:
        raise argparse.ArgumentTypeError("{}を指定してください: {}".format(expected, text))
    return value


EPILOG = """\
使用例:
  python3 audit.py https://example.com/sitemap.xml
  python3 audit.py https://example.com/sitemap_index.xml -o audit.csv --limit 200
  python3 audit.py ./sitemap.xml --ignore-robots --count-mode chars

出力列（この順）:
  url, status, redirect_to, title, title_len, desc, desc_len, h1_count,
  canonical, canonical_mismatch, robots_noindex, word_count
  status の例: 200 / 301>200 / 302>301>404 / ERROR:Timeout / BLOCKED:robots.txt /
  BLOCKED:private-address / SKIPPED:other-host / SKIPPED:credentials-in-url

注意:
  - JavaScript を実行しない（描画しない）。HTML の初期レスポンスだけを見るため、
    クライアントサイドで描画するサイトでは title・meta・本文が空または不正確になる。
    その場合は Search Console の URL 検査で「公開 URL をテスト」→「テスト済みのページを表示」
    から描画後の HTML を確認するか、JavaScript のレンダリングに対応したクローラーを使う。
  - 自社サイトか許可を得たサイトにだけ使う。--delay を短くしすぎない。
  - User-Agent はツール名がわかる文字列を送る。Googlebot を詐称しない。
  - ログインが必要なページは取得できない。認証情報（Authorization ヘッダー）は送らない:
    URL に userinfo（https://user:pass@example.jp/ の user:pass@ の部分。user@ と空の @ も含む）がある
    サイトマップ・loc・リダイレクト先は取得しない（最初のサイトマップなら終了コード 2、子サイトマップは
    注意を出して件数をサマリーに出す、ページは SKIPPED:credentials-in-url。リダイレクト先ならその段で
    止めて redirect_to に書く）。標準エラーと CSV では userinfo を *** に伏せる
    （例: https://***@example.jp/sitemap.xml）。~/.netrc（NETRC）の認証情報も使わない
    （プロキシの環境変数・システムのプロキシ設定と REQUESTS_CA_BUNDLE はそのまま使う）。
  - Cookie は、サーバーが Set-Cookie で返したものを同じ実行の中で送り返す（外から渡す手段はない）。
  - hreflang・構造化データ・内部リンク・表示速度は調べない
    （表示速度は Search Console の Core Web Vitals レポートか PageSpeed Insights で見る）。
  - ページのリンクをたどらないので、サイトマップに載っていないページは見つけられない。
  - サイトマップは XML（インデックス・.xml.gz を含む）、1行1URLのテキスト、RSS 2.0 / Atom の
    フィードを読む。http / https 以外の URL と空の loc はスキップする。
  - HTML でない 2xx（PDF など）は、Link ヘッダーの canonical・canonical_mismatch・
    X-Robots-Tag の noindex だけを記録する。4xx・5xx は status と redirect_to だけ。
    HTML のページだけを集計するときは、h1_count が空欄でない行に絞る。
  - 内部アドレス（プライベート・ループバック・リンクローカル・予約済み・マルチキャスト・未指定。
    IPv4 射影の IPv6 を含む）に解決されるホストには、サイトマップ・robots.txt・ページ・リダイレクトの
    どの段でもアクセスしない（ページは BLOCKED:private-address、最初のサイトマップなら終了コード 2）。
    社内ネットワークのステージング環境やローカルでのテストでは --allow-private を付ける。
  - ルートのサイトマップのホスト（リダイレクト後を含む。ローカルファイルなら最初の有効な loc のホスト）と
    違うホストの子サイトマップとページは取得しない（ページは SKIPPED:other-host）。サイトマップの URL は
    サイトマップと同じホストに置く決まりなので（Google ではクロス送信を設定した場合が例外）、サイトマップの
    誤りの手がかりになる。--allow-other-hosts で取得する。リダイレクトで別のホストに移るのは許可する。
  - 429 / 503 のあとは Retry-After（秒数か HTTP 日付。上限 120 秒）に従い、なければ間隔を --delay の
    2 倍ずつ延ばす（上限 60 秒）。429 / 503 を返した URL は取り直さない。429 / 503 が 5 回続いたら
    クロールを中断する（書き込み済みの行は残り、未取得の件数をサマリーに出す。終了コード 3）。
  - 1 ファイルの URL が 50,000 件を超えるか、展開後の大きさが 50MB を超えるサイトマップは、Google の上限を
    超えている旨を警告し、件数をサマリーに出す（処理は 100MB まで続ける）。
  - robots.txt は RFC 9309 / Google の仕様どおりに判定する（--user-agent の先頭のプロダクト
    トークンのグループ、なければ User-agent: *。最長一致、同じ長さなら Allow、* と $ に対応）。
    Googlebot 向けのグループは使わないので、Google の判定と違うことがある。
    robots.txt が 4xx（429 を除く）なら全許可。5xx・429・タイムアウト・接続エラーのときも全許可として
    続行し、警告を出す。Google はこれらをサーバーエラーとして扱い、最初の 12 時間はサイトのクロールを止め、
    その後 30 日間は最後に取得できた robots.txt を使う（なければ制限なし）。30 日を過ぎてもエラーが
    続くと、サイトが利用できる状態なら robots.txt がないものとして扱い、利用できない状態が続いていれば
    クロールを止める。
  - サイトマップインデックスが別のインデックスを参照している（入れ子の）場合は、たどったうえで警告を出し、
    件数をサマリーに出す（Google は入れ子のインデックスをサポートせず、Search Console でエラーになる）。
  - CSV インジェクション対策: url・redirect_to・title・desc・canonical で先頭が = + - @（またはタブ・CR）の
    セルの前に ' を付ける（title_len / desc_len は元の文字数。付けた数はサマリーに出す。--no-sanitize で無効）。

終了コード: 0 = 正常終了 / 2 = 最初のサイトマップから URL を得られない・指定の誤り・
  最初のサイトマップの URL に認証情報（userinfo）がある（取得しない。URL は伏せて表示）/
  3 = 429 / 503 が 5 回続いたため中断 / 130 = Ctrl+C で中断
"""


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """--help の折り返しでハイフンの位置では改行しない（ファイル名や User-Agent が途中で切れないようにする）。"""

    def _split_lines(self, text, width):
        # type: (str, int) -> List[str]
        return textwrap.wrap(re.sub(r"\s+", " ", text).strip(), width, break_on_hyphens=False)


class ArgumentParser(argparse.ArgumentParser):
    """引数の誤りのメッセージ（余分な引数をそのまま表示する unrecognized arguments など）でも userinfo を伏せる。"""

    def error(self, message):
        # type: (str) -> None
        argparse.ArgumentParser.error(self, mask_userinfo_text(message))


def build_parser():
    # type: () -> argparse.ArgumentParser
    parser = ArgumentParser(
        prog="audit.py",
        description=("サイトマップに載っている URL を取得し、HTTP ステータス・リダイレクト・title・"
                     "meta description・h1・canonical・noindex・本文の分量を CSV に書き出す。"),
        epilog=EPILOG,
        formatter_class=HelpFormatter,
    )
    parser.add_argument("-o", "--output", default="audit.csv",
                        help=("出力 CSV のパス（デフォルト: audit.csv）。UTF-8（BOM 付き）で書き出し、"
                              "CSV インジェクション対策をする（--no-sanitize を参照）"))
    parser.add_argument("--no-sanitize", dest="sanitize", action="store_false",
                        help=("CSV インジェクション対策を無効にする。既定では文字列の列（url, redirect_to, title, "
                              "desc, canonical）で、先頭が「=」「+」「-」「@」（またはタブ・CR）のセルの前に ' を"
                              "付ける（title_len / desc_len は元の文字数）。「-」で始まる正当な title（例:「-50%%オフ」）"
                              "にも付くので、pandas などで読むときは先頭の ' を除くか、このオプションで"
                              "出し直す"))
    parser.add_argument("--delay", metavar="秒", type=delay_seconds, default=1.0,
                        help=("すべての HTTP リクエスト（サイトマップ・robots.txt・ページ・リダイレクトの各段）"
                              "の間隔（デフォルト: 1.0）。0〜3600 秒。429 / 503 のあとは Retry-After に従い"
                              "（上限 120 秒）、なければこの値の 2 倍ずつ延ばす（上限 60 秒）"))
    parser.add_argument("--timeout", metavar="秒", type=timeout_seconds, default=15.0,
                        help="1回のリクエストのタイムアウト（デフォルト: 15）。0 より大きく 3600 秒以下")
    parser.add_argument("--limit", metavar="件数", type=positive_int, default=None,
                        help=("処理するページ URL の上限（デフォルト: なし）。1 以上。robots.txt・内部アドレス・"
                              "別のホスト・URL の認証情報（userinfo）のため取得しなかった URL も1件と数える。"
                              "上限に達したら、それ以上サイトマップをたどらない"))
    parser.add_argument("--user-agent", metavar="UA", default=DEFAULT_USER_AGENT,
                        help=("送信する User-Agent（デフォルト: %(default)s）。Googlebot を名乗らない。"
                              "robots.txt は先頭のプロダクトトークン（例: seo-operator-audit）で判定する"))
    parser.add_argument("--ignore-robots", action="store_true",
                        help="robots.txt を無視してすべての URL を取得する（自社サイトの監査用）")
    parser.add_argument("--allow-private", action="store_true",
                        help=("内部アドレス（プライベート・ループバック・リンクローカル・予約済み・マルチキャスト・"
                              "未指定。IPv4 射影の IPv6 を含む）に解決されるホストへのアクセスを許可する。既定では"
                              "取得せず、ページは BLOCKED:private-address にする。社内ネットワークのステージング環境の"
                              "監査や、ローカルでのテストに使う"))
    parser.add_argument("--allow-other-hosts", action="store_true",
                        help=("ルートのサイトマップのホスト（リダイレクト後を含む）と違うホストの子サイトマップと"
                              "ページも取得する。既定では取得せず、ページは SKIPPED:other-host にする。"
                              "ローカルファイルでは最初の有効な loc のホストを基準にする"))
    parser.add_argument("--count-mode", choices=["auto", "chars", "words"], default="auto",
                        help=("word_count の数え方（デフォルト: auto）。auto は <html lang> が ja で始まるか、"
                              "本文のひらがな・カタカナ・漢字の割合が 20%% 以上なら文字数（空白を除く）、"
                              "それ以外は単語数。日英混在サイトで単位をそろえたいときは chars"))
    parser.add_argument("--max-depth", metavar="N", type=depth_int, default=5,
                        help=("サイトマップインデックスをたどる深さの上限（デフォルト: 5）。0〜50。"
                              "最初のサイトマップが 0、その子が 1"))
    parser.add_argument("sitemap",
                        help=("サイトマップ（またはサイトマップインデックス）の URL か、ローカルファイルのパス。"
                              ".xml.gz、テキスト形式（1行1URL）、RSS 2.0 / Atom のフィードにも対応。"
                              "認証情報（user:pass@ などの userinfo）を含む URL は取得せず、終了コード 2 で止める"))
    return parser


def check_source(source):
    # type: (str) -> Tuple[Optional[bool], List[str]]
    """
    (ローカルファイルか, エラーメッセージ) を返す。エラーなら1つ目は None。
    メッセージに出す URL は userinfo を伏せる（userinfo を含む URL はここで止める）。
    """
    shown = mask_userinfo(source)
    if re.match(r"^https?://", source, re.I):
        if has_userinfo(source):
            return None, ["エラー: サイトマップの URL に認証情報（userinfo。user:pass@ などの部分）が含まれているため、"
                          "取得しません: {}".format(shown),
                          "  URL の userinfo は requests が Basic 認証（Authorization ヘッダー）として送り、CSV やログにも"
                          "残るため受け付けません。このスクリプトはログインが必要なページを監査できません。"
                          "userinfo を除いた URL を指定してください（例: https://example.jp/sitemap.xml）。"]
        try:
            host = urlsplit(source).hostname
        except ValueError as exc:
            return None, ["エラー: URL として解釈できません（{}）: {}".format(exc, shown)]
        if not host:
            return None, ["エラー: URL にホスト名がありません: {}".format(shown),
                          "  https://example.com/sitemap.xml のように指定してください。"]
        return False, []
    if source and os.path.isfile(source):
        return True, []
    if source and os.path.isdir(source):
        return None, ["エラー: フォルダが指定されています: {}".format(source),
                      "  サイトマップのファイルのパスか URL を指定してください。"]
    bare = _BARE_USERINFO_RE.match(source) if shown == source else None
    if bare:  # スキームのない user:pass@example.jp/... の形。スキームの案内（user: の URL）も出さない
        return None, ["エラー: サイトマップが見つかりません: ***{}".format(source[bare.end() - 1:]),
                      "  URL なら https:// で始め、認証情報（user:pass@ などの部分）を含めずに指定してください"
                      "（例: https://example.jp/sitemap.xml）。"]
    messages = ["エラー: サイトマップが見つかりません: {}".format(shown)]
    scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.\-]*):", source)
    if scheme and len(scheme.group(1)) > 1:  # 1文字は Windows のドライブ名
        messages.append("  {}: の URL には対応していません。http:// か https:// で始まる URL、"
                        "または存在するファイルのパスを指定してください。".format(scheme.group(1)))
    elif re.match(r"^[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+(:\d+)?/", source) or source.lower().startswith("www."):
        messages.append("  URL なら先頭に https:// を付けてください（例: https://{}）。".format(shown))
    else:
        messages.append("  http:// か https:// で始まる URL、または存在するファイルのパスを指定してください。")
    return None, messages


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main(argv=None):
    # type: (Optional[List[str]]) -> int
    args = build_parser().parse_args(argv)
    missing = [name for name, module in (("requests", requests), ("beautifulsoup4", BeautifulSoup))
               if module is None]
    if missing:
        return missing_packages(missing, argv)
    warnings.filterwarnings("ignore", module="bs4")

    source = args.sitemap.strip()
    is_local, messages = check_source(source)
    if is_local is None:
        for message in messages:
            log(message)
        return 2

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if not os.path.isdir(out_dir):
        log("エラー: 出力先のフォルダがありません: {}".format(out_dir))
        log("  -o で既存のフォルダ内のパスを指定してください。")
        return 2
    if os.path.isdir(args.output):
        log("エラー: 出力先がフォルダです: {}".format(args.output))
        log("  -o でファイル名まで指定してください（例: -o audit.csv）。")
        return 2
    if is_local and os.path.exists(args.output) and os.path.samefile(source, args.output):
        log("エラー: 出力先が入力のサイトマップと同じファイルです: {}".format(args.output))
        log("  -o で別のファイル名を指定してください（上書きするとサイトマップが消えます）。")
        return 2

    if "googlebot" in args.user_agent.lower():
        log("警告: User-Agent に Googlebot を含めないでください。Googlebot を詐称したアクセスは、"
            "相手のサイトのログや判定を誤らせます。")
    if args.delay < 0.5:
        log("注意: --delay {} 秒は短めです。自社サイト以外では 1 秒以上にしてください。".format(args.delay))
    if not args.ignore_robots and not product_token(args.user_agent):
        log("注意: User-Agent の先頭にプロダクトトークン（英字・ハイフン・アンダースコア）がないため、"
            "robots.txt は User-agent: * のグループだけで判定します。")

    guard = None if args.allow_private else AddressGuard()
    if guard is not None:
        set_connection_guard(True, proxy_hosts())
    else:
        _CONNECTION_GUARD["on"] = False  # 同じプロセスで先に main() を呼んでいた場合の判定を外す
        log("注意: --allow-private を指定したため、内部アドレス（プライベート IP など）にもアクセスします。")
    scope = HostScope(args.allow_other_hosts)
    fetcher = Fetcher(args.delay, args.timeout, args.user_agent, guard)
    robots = None if args.ignore_robots else RobotsCache(fetcher, args.user_agent)
    collector = SitemapCollector(fetcher, args.max_depth, args.limit, scope)
    started = time.monotonic()

    log("サイトマップを読み込みます: {}".format(source))
    try:
        root_ok = collector.collect(source, bool(is_local))
    except KeyboardInterrupt:
        log("中断しました（サイトマップの収集中）。CSV は書き出していません。")
        return 130
    except CrawlAborted:
        root_ok = False
    if fetcher.aborted:
        log("中断しました（サイトマップの収集中）: 429 / 503 が {} 回続いたため、サーバーがアクセスを制限しているとみなし"
            "ました。CSV は書き出していません。時間をおいてから、--delay を長くして実行し直してください。".format(
                THROTTLE_LIMIT))
        return EXIT_THROTTLED

    urls = collector.pages if args.limit is None else collector.pages[:args.limit]
    if not urls and not root_ok:
        log("エラー: 最初のサイトマップを取得・解析できず、URL が1件も得られませんでした: {}".format(source))
        if collector.private:
            log("  サイトマップのホストが内部アドレスに解決されます。社内ネットワークのステージング環境やローカルでの"
                "テストなら --allow-private を付けて実行し直してください。")
        elif collector.credentials:
            log("  サイトマップのリダイレクト先の URL に認証情報（userinfo）が含まれるため、取得しませんでした"
                "（Basic 認証として送られるのを防ぐため）。このスクリプトはログインが必要なページを監査できません。")
        else:
            log("  URL をブラウザで開けるか、XML（<urlset> / <sitemapindex>）、RSS / Atom、"
                "1行1URLのテキストのいずれかであるかを確認してください。")
        return 2
    log("ページ URL: {} 件{}".format(len(urls), "（--limit {}）".format(args.limit) if args.limit else ""))
    if not urls:
        log("注意: サイトマップにページ URL がありませんでした。ヘッダー行だけの CSV を書き出します。")
    n_other = sum(1 for url in urls if scope.outside(url) and not has_userinfo(url))  # userinfo 付きは別の status
    n_credentials = sum(1 for url in urls if has_userinfo(url))
    if n_credentials:
        log("注意: URL に認証情報（userinfo）を含むページが {} 件あります。取得せずに status を {} にします"
            "（Basic 認証として送られるのを防ぐため。CSV と標準エラーでは userinfo を *** に伏せます）。".format(
                n_credentials, STATUS_CREDENTIALS))
    if n_other:
        log("警告: サイトマップのホスト（{}）と別のホストの URL が {} 件あります。取得せずに status を {} にします"
            "（--allow-other-hosts で取得）。sitemaps.org の仕様では、サイトマップの URL はサイトマップと同じホストに"
            "置く決まりです（Google では、Search Console か robots.txt でクロス送信を設定した場合が例外）。".format(
                "・".join(scope.hosts), n_other, STATUS_OTHER_HOST))

    try:
        out = open_output(args.output)
    except OSError as exc:
        log("エラー: 出力ファイルを開けません（{}）: {}".format(exc, args.output))
        return 2

    stats = Stats()
    interrupted = False
    total = len(urls)
    with out:
        writer = csv.writer(out)
        writer.writerow(COLUMNS)
        out.flush()
        try:
            for index, url in enumerate(urls, 1):
                try:
                    row, info = audit_page(url, fetcher, robots, args.count_mode, scope)
                except CrawlAborted:
                    break
                mask_row_userinfo(row)  # url・redirect_to・canonical の userinfo を伏せる（--no-sanitize でも）
                n_sanitized = sanitize_row(row) if args.sanitize else 0  # 集計に使う列は変えない
                writer.writerow([row[column] for column in COLUMNS])
                out.flush()
                stats.add(row, info)
                stats.sanitized += n_sanitized
                log("[{}/{}] {} {}".format(index, total, row["status"], mask_userinfo(url)))
                for note in info["notes"]:  # type: ignore[union-attr]
                    log("    {}".format(note))
                if fetcher.aborted:
                    break
        except KeyboardInterrupt:
            interrupted = True
            log("中断しました。書き込み済みの {} 行は {} に残っています。".format(stats.rows, args.output))

    if fetcher.aborted:
        log("中断しました: 429 / 503 が {} 回続いたため、サーバーがアクセスを制限しているとみなしました。書き込み済みの"
            " {} 行は {} に残っています（未取得 {} 件）。時間をおいてから、--delay を長くするか --limit で件数を絞って"
            "実行し直してください。".format(THROTTLE_LIMIT, stats.rows, args.output, total - stats.rows))
    state = "Ctrl+C で中断" if interrupted else (
        "429 / 503 が {} 回続いたため中断".format(THROTTLE_LIMIT) if fetcher.aborted else "")
    print_summary(stats, total, fetcher, collector, args.output, time.monotonic() - started, state,
                  args.sanitize)
    if interrupted:
        return 130
    return EXIT_THROTTLED if fetcher.aborted else 0


if __name__ == "__main__":
    sys.exit(main())
