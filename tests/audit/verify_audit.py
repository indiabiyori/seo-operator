#!/usr/bin/env python3
"""
audit.py の検証。ローカル HTTP サーバー（server.py）を別プロセスで起動し、ケースごとに audit.py を
実行して、出力 CSV の各列・標準エラー・サーバー側のアクセスログを、手計算した期待値と照合する。
サーバーは終了時に必ず停止する。

  python verify_audit.py [--python /path/to/python] [--cases main,limit,...]
"""
import argparse
import ast
import csv
import importlib.util
import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import time
from collections import Counter

sys.dont_write_bytecode = True  # スキルのフォルダに __pycache__ を作らない

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
# 既定の対象は、このリポジトリの skills/seo-operator（環境変数 SEO_OPERATOR_DIR で切り替える）
REPO_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "skills", "seo-operator")
SKILL_ROOT = os.environ.get("SEO_OPERATOR_DIR", REPO_SKILL)
AUDIT = os.environ.get("AUDIT_PATH", os.path.join(SKILL_ROOT, "scripts", "audit.py"))
LOG = os.path.join(OUT, "access.log")
DEFAULT_UA = "seo-operator-audit/1.0 (+SEO audit script; Python requests)"
COLUMNS = ["url", "status", "redirect_to", "title", "title_len", "desc", "desc_len",
           "h1_count", "canonical", "canonical_mismatch", "robots_noindex", "word_count"]

RESULTS = []  # (name, ok, detail)


def record(name, failures, detail_ok):
    ok = not failures
    RESULTS.append((name, ok, detail_ok if ok else "; ".join(failures)))
    print("[{}] {}: {}".format("PASS" if ok else "FAIL", name, detail_ok if ok else "\n    " + "\n    ".join(failures)))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


CERT = os.path.join(OUT, "test-cert.pem")
KEY = os.path.join(OUT, "test-key.pem")


def make_cert():
    """localhost / 127.0.0.1 用の自己署名証明書を作る（本物の HTTPS へのリダイレクトの検証用）。"""
    proc = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", KEY, "-out", CERT,
                           "-days", "2", "-subj", "/CN=localhost",
                           "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], capture_output=True, text=True)
    return proc.returncode == 0 and os.path.exists(CERT)


class Server(object):
    def __init__(self, python):
        self.closed_port = free_port()
        if os.path.exists(LOG):
            os.remove(LOG)
        extra = ["--cert", CERT, "--key", KEY] if make_cert() else []
        self.proc = subprocess.Popen(
            [python, os.path.join(HERE, "server.py"), "--closed-port", str(self.closed_port), "--log", LOG] + extra,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline().split()
        if not line or line[0] != "PORT":
            raise RuntimeError("server did not start: {}".format(self.proc.stderr.read()))
        self.port, self.ssl_port = int(line[1]), int(line[2])
        self.https_port = int(line[3]) if len(line) > 3 else 0
        self.base = "http://127.0.0.1:{}".format(self.port)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)


def log_size():
    return os.path.getsize(LOG) if os.path.exists(LOG) else 0


def log_since(offset):
    with open(LOG, "r", encoding="utf-8") as f:
        f.seek(offset)
        return [json.loads(line) for line in f if line.strip()]


def run_audit(python, args, timeout=180, allow_private=True):
    # テストサーバーは 127.0.0.1 / localhost なので、既定の内部アドレスの拒否を外す（新しい挙動のテストでは False）
    if allow_private and "--allow-private" not in args:
        args = args + ["--allow-private"]
    # 前回の実行の CSV が残っていると失敗を見逃すので消しておく（入力と同じパスのときは消さない）
    if "-o" in args:
        out_path = args[args.index("-o") + 1]
        others = [a for i, a in enumerate(args) if i != args.index("-o") + 1]
        if os.path.isfile(out_path) and out_path not in others:
            os.remove(out_path)
    start = log_size()
    env = dict(os.environ, COLUMNS="200")
    if os.path.exists(CERT):
        env["REQUESTS_CA_BUNDLE"] = CERT  # テスト用の自己署名証明書だけを信頼する
    proc = subprocess.run([python, AUDIT] + args, capture_output=True, text=True, timeout=timeout, env=env)
    return proc, log_since(start)


def read_csv(path):
    with open(path, "rb") as f:
        raw = f.read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return has_bom, rows[0] if rows else [], [dict(zip(rows[0], r)) for r in rows[1:]], rows


def E(status, redirect_to="", title="", title_len="", desc="", desc_len="", h1="", canonical="",
      mismatch="", noindex="", wc=""):
    return {"status": status, "redirect_to": redirect_to, "title": title, "title_len": str(title_len),
            "desc": desc, "desc_len": str(desc_len), "h1_count": str(h1), "canonical": canonical,
            "canonical_mismatch": mismatch, "robots_noindex": noindex, "word_count": str(wc)}


def P(title, title_len, wc=7, desc="説明", desc_len=2, h1=1, canonical="", mismatch="", noindex="False",
      status="200", redirect_to=""):
    """HTML を解析したページの期待値。"""
    return E(status, redirect_to, title, title_len, desc, desc_len, h1, canonical, mismatch, noindex, wc)


def compare_rows(rows, expected, failures, prefix=""):
    got_urls = [r["url"] for r in rows]
    exp_urls = [u for u, _ in expected]
    if got_urls != exp_urls:
        failures.append("{}URL の順序・件数が不一致\n      got={}\n      exp={}".format(prefix, got_urls, exp_urls))
    by_url = {r["url"]: r for r in rows}
    for url, exp in expected:
        row = by_url.get(url)
        if row is None:
            failures.append("{}行がない: {}".format(prefix, url))
            continue
        for col, val in exp.items():
            if row.get(col) != val:
                failures.append("{}{} の {}: got={!r} exp={!r}".format(prefix, url, col, row.get(col), val))


def gaps(entries):
    ts = [e["t"] for e in entries]
    return [b - a for a, b in zip(ts, ts[1:])]


# ---------------------------------------------------------------------------

def case_main(py, srv):
    b = srv.base
    out = os.path.join(OUT, "main.csv")
    proc, log = run_audit(py, [b + "/sitemap_index.xml", "-o", out, "--delay", "0.1", "--timeout", "1"])
    f = []
    if proc.returncode != 0:
        f.append("終了コード {}（期待 0）stderr={}".format(proc.returncode, proc.stderr[-2000:]))
    has_bom, header, rows, _ = read_csv(out)
    if not has_bom:
        f.append("BOM がない（utf-8-sig でない）")
    if header != COLUMNS:
        f.append("ヘッダーが不一致: {}".format(header))
    ja = "これは監査スクリプトのテスト用に作った日本語のページです。"
    expected = [
        (b + "/p/ja-normal", P("日本語の正常なページ｜サンプル", 15, wc=19, desc=ja, desc_len=29,
                               canonical=b + "/p/ja-normal", mismatch="False")),
        (b + "/p/no-title", P("", 0, desc="説明文あり", desc_len=5)),
        (b + "/p/no-desc", P("複数の 空白 を含む　タイトル", 15, desc="", desc_len=0)),
        (b + "/p/two-h1", P("h1が2個", 5, wc=4, h1=2)),
        (b + "/p/noindex-meta", P("メタ除外", 4, noindex="True")),
        (b + "/p/noindex-header", P("ヘッダー除外", 6, noindex="True")),
        (b + "/p/xrobots-otherbot", P("他社向け", 4, noindex="False")),
        (b + "/p/none-googlebot", P("全拒否", 3, noindex="True")),
        (b + "/p/canonical-mismatch", P("不一致", 3, canonical=b + "/p/other", mismatch="True")),
        (b + "/p/canonical-relative", P("相対パス", 4, canonical=b + "/p/canonical-relative", mismatch="False")),
        (b + "/p/canonical-link-header", P("リンク見出し", 6, canonical=b + "/p/canonical-link-header",
                                          mismatch="False")),
        (b + "/p/canonical-body", P("本文内", 3, canonical="", mismatch="")),
        (b + "/p/canonical-normalize", P("正規化", 3, canonical=b + "/p/canonical-normalize#section",
                                        mismatch="False")),
        (b + "/p/canonical-base", P("基準URL", 5, canonical=b + "/p/canonical-base", mismatch="False")),
        (b + "/p/canonical-slash", P("末尾スラッシュ", 7, canonical=b + "/p/canonical-slash/", mismatch="True")),
        (b + "/p/%E6%97%A5%E6%9C%AC%E8%AA%9E", P("日本語URL", 6, canonical=b + "/p/日本語", mismatch="False")),
        (b + "/redirect/301", P("転送先A", 4, status="301>200", redirect_to=b + "/p/target-a",
                                canonical=b + "/p/target-a", mismatch="False")),
        (b + "/redirect/chain", P("転送先B", 4, status="302>301>200", redirect_to=b + "/p/target-b",
                                  canonical=b + "/p/target-b", mismatch="False")),
        (b + "/redirect/loop-a", E("ERROR:TooManyRedirects")),
        (b + "/p/not-found", E("404")),
        (b + "/p/server-error", E("500")),
        (b + "/p/slow", E("ERROR:Timeout")),
        ("http://127.0.0.1:{}/p/refused".format(srv.closed_port), E("BLOCKED:robots-unreachable")),
        ("https://127.0.0.1:{}/p/ssl".format(srv.ssl_port), E("BLOCKED:robots-unreachable")),
        (b + "/p/sjis", P("シフトJISのページ①髙", 12, wc=6, desc="機種依存文字①と髙を含む説明", desc_len=14)),
        (b + "/p/eucjp", P("EUC-JPのページ①", 11, wc=7, desc="日本語EUCの説明", desc_len=9)),
        (b + "/p/english", P("English Page", 12, wc=14, desc="An English description.", desc_len=23)),
        (b + "/p/doc.pdf", E("200", canonical=b + "/p/doc.pdf", mismatch="False", noindex="False")),
        (b + "/private/secret", E("BLOCKED:robots.txt")),
        (b + "/redirect/to-private", E("BLOCKED:robots.txt", redirect_to=b + "/private/landing")),
        (b + "/p/ja-nolang", P("言語指定なし", 6, wc=29)),
        (b + "/p/mixed", P("Mixed", 5, wc=11)),
        (b + "/p/ja-article", P("記事ページ", 5, wc=7)),
        (b + "/p/ja-body", P("本文の抽出", 5, wc=8)),
    ]
    compare_rows(rows, expected, f)

    err = proc.stderr
    for needle in ["missing.xml", "訪問済みのためスキップ", '<body> 内の rel="canonical" を無視',
                   "robots.txt を取得できませんでした（ERROR:ConnectionError）",
                   "robots.txt を取得できませんでした（ERROR:SSLError）",
                   "[1/34] 200 " + b + "/p/ja-normal", "[17/34] 301>200 " + b + "/redirect/301",
                   "=== サマリー ===", "noindex: 3 件", "canonical 不一致: 2 件", "title なし（空を含む）: 1 件",
                   "meta description なし（空を含む）: 1 件", "h1 が1個でないページ: 1 件（0個: 0 / 2個以上: 1）",
                   "エラー: 2 件", "robots.txt で除外: 2 件", "robots.txt を取得できずに除外: 2 件", "word_count の単位: 文字数 23 件 / 単語数 2 件",
                   "HTML を解析したページ: 25 件", "  BLOCKED:robots.txt: 2", "  BLOCKED:robots-unreachable: 2",
                   "HTML 以外（HTTP ヘッダーの canonical と X-Robots-Tag だけを記録）: 1 件",
                   # 2026-09-26 追加: sitemap_index.xml → nested_index.xml は入れ子のインデックス
                   "警告: サイトマップインデックスが別のサイトマップインデックスを参照しています（入れ子）: "
                   + b + "/sitemaps/nested_index.xml（参照元: " + b + "/sitemap_index.xml）",
                   "入れ子のサイトマップインデックス（Google は非対応。Search Console でエラー）: 1 件",
                   "CSV インジェクション対策で ' を付けたセル: 0 個"]:
        if needle not in err:
            f.append("stderr に {!r} がない".format(needle))
    if err.count("入れ子）:") != 1:
        f.append("入れ子の警告が {} 回（nested_index.xml の 1 回だけのはず）".format(err.count("入れ子）:")))
    if err.count("訪問済みのためスキップ") != 2:
        f.append("ループ防止のスキップが {} 回（期待 2）".format(err.count("訪問済みのためスキップ")))

    paths = [e["path"] for e in log]
    for p, n in [("/sitemap_index.xml", 1), ("/robots.txt", 1), ("/p/ja-normal", 1), ("/p/no-title", 1),
                 ("/private/secret", 0), ("/private/landing", 0), ("/sitemaps/missing.xml", 1),
                 ("/sitemaps/pages.xml.gz", 1), ("/redirect/loop-a", 6), ("/redirect/loop-b", 5)]:
        if paths.count(p) != n:
            f.append("サーバーへの {} のリクエストが {} 回（期待 {}）".format(p, paths.count(p), n))
    if proc.stdout:
        f.append("標準出力に何か出ている（進捗・サマリーは標準エラーのはず）: {!r}".format(proc.stdout[:200]))
    bad_ua = [e["ua"] for e in log if e["ua"] != DEFAULT_UA]
    if bad_ua or any("googlebot" in e["ua"].lower() for e in log):
        f.append("User-Agent が既定値でない: {}".format(bad_ua[:3]))
    g = gaps(log)
    if not g or min(g) < 0.1 - 0.005:
        f.append("リクエスト間隔の最小値 {:.4f} 秒 < 0.1 秒".format(min(g) if g else -1))
    detail = ("34 行・全列一致、BOM とヘッダー順 OK、サーバー側で {} リクエストの最小間隔 {:.3f} 秒（--delay 0.1）、"
              "UA は既定値、robots.txt 1回、/private/* へのアクセス 0 回、ループ 11 リクエストで停止").format(
        len(log), min(g) if g else -1)
    record("main: 全フィクスチャ（サイトマップ再帰・各ページ・各エラー・文字コード）", f, detail)
    return proc


def case_limit(py, srv):
    b = srv.base
    out = os.path.join(OUT, "limit.csv")
    proc, log = run_audit(py, [b + "/sitemap_index.xml", "-o", out, "--delay", "0.1", "--limit", "3"])
    f = []
    if proc.returncode != 0:
        f.append("終了コード {}".format(proc.returncode))
    _, header, rows, _ = read_csv(out)
    got = [r["url"] for r in rows]
    exp = [b + "/p/ja-normal", b + "/p/no-title", b + "/p/no-desc"]
    if got != exp:
        f.append("行が不一致: {}".format(got))
    paths = [e["path"] for e in log]
    sitemaps = [p for p in paths if p.startswith("/sitemap")]
    if sitemaps != ["/sitemap_index.xml", "/sitemaps/nested_index.xml", "/sitemaps/pages1.xml"]:
        f.append("上限到達後もサイトマップをたどった: {}".format(sitemaps))
    if len(paths) != 3 + 1 + 3:
        f.append("リクエスト数 {}（期待 7 = サイトマップ3 + robots 1 + ページ3）: {}".format(len(paths), paths))
    record("--limit 3", f, "3 行のみ出力。上限到達後は pages.xml.gz / urls.txt / missing.xml を取得しない（計7リクエスト）")


def case_ignore_robots(py, srv):
    b = srv.base
    out = os.path.join(OUT, "ignore_robots.csv")
    proc, log = run_audit(py, [b + "/sitemaps/robots-test.xml", "-o", out, "--delay", "0.1", "--ignore-robots"])
    f = []
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [
        (b + "/private/secret", P("秘密", 2)),
        (b + "/redirect/to-private", P("非公開の着地", 6, status="301>200", redirect_to=b + "/private/landing")),
    ], f)
    paths = [e["path"] for e in log]
    if "/robots.txt" in paths:
        f.append("--ignore-robots なのに robots.txt を取得した")
    if "/private/secret" not in paths or "/private/landing" not in paths:
        f.append("/private/* を取得していない: {}".format(paths))
    record("--ignore-robots", f, "disallow のページが 200 / 301>200 で取得され、robots.txt へのリクエストなし")


def case_count_mode(py, srv):
    b = srv.base
    f = []
    for mode, en, ja in [("chars", 63, 19), ("words", 14, 5), ("auto", 14, 19)]:
        out = os.path.join(OUT, "count_{}.csv".format(mode))
        proc, _ = run_audit(py, [b + "/sitemaps/countmode.xml", "-o", out, "--delay", "0.1", "--count-mode", mode])
        _, _, rows, _ = read_csv(out)
        got = {r["url"]: r["word_count"] for r in rows}
        if got.get(b + "/p/english") != str(en) or got.get(b + "/p/ja-normal") != str(ja):
            f.append("{}: got={} exp english={} ja={}".format(mode, got, en, ja))
    record("--count-mode chars / words / auto", f,
           "英語ページ chars=63 / words=14、日本語ページ chars=19 / words=5、auto は 14（単語）と 19（文字）")


def case_max_depth(py, srv):
    b = srv.base
    f = []
    out1 = os.path.join(OUT, "depth1.csv")
    proc1, log1 = run_audit(py, [b + "/deep/level1.xml", "-o", out1, "--delay", "0.1", "--max-depth", "1"])
    _, header1, rows1, _ = read_csv(out1)
    if proc1.returncode != 0 or rows1 or header1 != COLUMNS:
        f.append("--max-depth 1: rc={} rows={}".format(proc1.returncode, len(rows1)))
    if "--max-depth 1" not in proc1.stderr:
        f.append("--max-depth 1 のスキップが stderr にない")
    if "/deep/level3.xml" in [e["path"] for e in log1]:
        f.append("--max-depth 1 で level3 を取得した")
    out2 = os.path.join(OUT, "depth2.csv")
    proc2, _ = run_audit(py, [b + "/deep/level1.xml", "-o", out2, "--delay", "0.1", "--max-depth", "2"])
    _, _, rows2, _ = read_csv(out2)
    if proc2.returncode != 0 or [r["url"] for r in rows2] != [b + "/p/english"]:
        f.append("--max-depth 2: rc={} rows={}".format(proc2.returncode, [r["url"] for r in rows2]))
    record("--max-depth", f, "深さ1ではlevel3を取得せずヘッダーのみ・終了コード0、深さ2では1行")


def case_local_file(py, srv):
    b = srv.base
    path = os.path.join(OUT, "local_sitemap.xml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                 "<url><loc>{}/p/english</loc></url><url><loc>/p/two-h1</loc></url></urlset>".format(b))
    out = os.path.join(OUT, "local.csv")
    proc, _ = run_audit(py, [path, "-o", out, "--delay", "0.1"])
    f = []
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [(b + "/p/english", P("English Page", 12, wc=14, desc="An English description.", desc_len=23))], f)
    if "相対 URL の loc" not in proc.stderr:
        f.append("相対 URL のスキップが stderr にない")
    record("ローカルファイルのサイトマップ", f, "ページは HTTP で取得、相対 loc はスキップして記録")


def case_exit_codes(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "should_not_exist.csv")
    if os.path.exists(out):
        os.remove(out)
    for label, args, needle in [
        ("ルート 404", [b + "/nonexistent.xml"], "最初のサイトマップを取得・解析できず"),
        ("DTD 付き XML", [b + "/sitemaps/dtd.xml"], "DOCTYPE / ENTITY"),
        ("存在しないローカルパス", [os.path.join(OUT, "no_such_file.xml")], "サイトマップが見つかりません"),
    ]:
        proc, _ = run_audit(py, args + ["-o", out, "--delay", "0.1"])
        if proc.returncode != 2 or needle not in proc.stderr:
            f.append("{}: rc={} stderr={}".format(label, proc.returncode, proc.stderr[-300:]))
    if os.path.exists(out):
        f.append("終了コード 2 なのに CSV が作られた")
    proc, _ = run_audit(py, [b + "/sitemaps/small.xml", "-o", os.path.join(OUT, "nodir", "x.csv")])
    if proc.returncode != 2 or "出力先のフォルダがありません" not in proc.stderr:
        f.append("出力先なし: rc={}".format(proc.returncode))
    proc, _ = run_audit(py, [b + "/sitemaps/small.xml", "--delay", "-1"])
    if proc.returncode != 2:
        f.append("--delay -1: rc={}".format(proc.returncode))
    record("終了コード 2（入力エラー）", f, "ルート404・DTD付きXML・存在しないパス・出力先なし・不正な --delay がすべて 2、CSV は作らない")


def case_help(py, srv):
    f = []
    proc = subprocess.run([py, AUDIT, "--help"], capture_output=True, text=True, env=dict(os.environ, COLUMNS="200"))
    text = proc.stdout
    if proc.returncode != 0:
        f.append("rc={}".format(proc.returncode))
    for needle in ["usage: audit.py [-h] [-o OUTPUT] [--no-sanitize] [--delay 秒] [--timeout 秒] [--limit 件数]",
                   "CSV インジェクション対策を無効にする", "url, redirect_to, title, desc, canonical",
                   "title_len / desc_len は元の文字数", "先頭の ' を除くか",
                   "入れ子の）場合は、たどったうえで警告を出し", "Google は入れ子のインデックスをサポートせず",
                   "5xx・タイムアウト・接続エラーのときは RFC 9309 に従い", "429 のときは Google の仕様に合わせて", "h1_count が空欄でない行に絞る",
                   "Googlebot 向けのグループは使わない", "サイトマップに載っていないページは見つけられない",
                   "[--user-agent UA] [--ignore-robots] [--allow-private] [--allow-other-hosts]",
                   "[--count-mode {auto,chars,words}]",
                   "[--max-depth N]", "（デフォルト: 1.0）", "（デフォルト: 15）", "（デフォルト: 5）",
                   "デフォルト: " + DEFAULT_UA, "JavaScript を実行しない", "「公開 URL をテスト」→「テスト済みのページを表示」",
                   "Googlebot を詐称しない", "使用例:", "python3 audit.py https://example.com/sitemap.xml",
                   "RSS 2.0 / Atom", "HTML でない 2xx（PDF など）は、Link ヘッダーの canonical",
                   "RFC 9309", "最初の 12 時間はサイトのクロールを止め", "BLOCKED:robots-unreachable",
                   "--allow-private", "BLOCKED:private-address", "社内ネットワークのステージング環境",
                   "IPv4 射影の IPv6", "--allow-other-hosts", "SKIPPED:other-host", "リダイレクト後を含む",
                   "最初の有効な loc のホスト", "Retry-After", "上限 120 秒", "上限 60 秒", "5 回続いたら",
                   "3 = 429 / 503 が 5 回続いたため中断", "50,000 件", "50MB"]:
        if needle not in text:
            f.append("--help に {!r} がない".format(needle))
    with open(AUDIT, encoding="utf-8") as fh:
        src = fh.read()
    doc = ast.get_docstring(ast.parse(src)) or ""
    for needle in ["JavaScript を実行しない", "Googlebot を詐称しない", "ログインが必要なページは取得できない",
                   "hreflang、構造化データ、内部リンク", "自社サイトか、許可を得たサイト", "--delay",
                   "RFC 9309 と Google の robots.txt の仕様", "最長一致", "* と $ のワイルドカード",
                   "最初の 12 時間は", "--ignore-robots で続けられる", "BLOCKED:robots-unreachable", "RSS 2.0 / Atom",
                   "HTML でない 2xx のレスポンス（PDF など）は、canonical（Link ヘッダー）",
                   "BLOCKED:private-address", "SKIPPED:other-host", "--allow-private", "--allow-other-hosts",
                   "IPv4 射影の IPv6", "DNS リバインディング", "Retry-After", "上限 120 秒", "上限 60 秒",
                   "3   429 / 503 が 5 回続いたため中断", "50,000 件を超えるか、展開後の大きさが 50MB を超える",
                   "Google は入れ子のサイトマップインデックスをサポート", "gzip は Google も受け付ける",
                   "CSV インジェクション対策として、文字列の列（url, redirect_to, title, desc, canonical）",
                   "title_len / desc_len は元の文字数のまま", "--no-sanitize",
                   "サイトマップに載っていないページ（孤立ページを含む）は見つけられない", "Core Web Vitals"]:
        if needle not in doc:
            f.append("ヘッダーコメントに {!r} がない".format(needle))
    for stale in ["urllib.robotparser", "robotparser", "ワイルドカードを解釈しない", "解析するのは最終ステータスが 2xx の HTML だけ",
                  "入れ子のインデックスも可", "一時的な全拒否", "一時的な\n    全拒否"]:
        if stale in src:
            f.append("古い記述 {!r} が残っている".format(stale))
    if not src.startswith("#!/usr/bin/env python3\n"):
        f.append("シバンがない")
    record("--help とヘッダーコメント", f, "usage 行・デフォルト値（delay 1.0 / timeout 15 / max-depth 5）・JS 制約・使用例を確認")


def case_default_delay(py, srv):
    b = srv.base
    out = os.path.join(OUT, "default_delay.csv")
    proc, log = run_audit(py, [b + "/sitemaps/small.xml", "-o", out])
    f = []
    g = gaps(log)
    if len(log) != 4:
        f.append("リクエスト数 {}（期待 4）".format(len(log)))
    if not g or min(g) < 1.0 - 0.005:
        f.append("デフォルトの間隔が 1 秒未満: {}".format(["{:.3f}".format(x) for x in g]))
    record("--delay のデフォルト 1.0 秒（サーバー側の到着時刻）", f,
           "サイトマップ→robots.txt→ページ2件の間隔 {}".format(", ".join("{:.3f}s".format(x) for x in g)))


def case_interrupt(py, srv):
    b = srv.base
    out = os.path.join(OUT, "interrupt.csv")
    proc = subprocess.Popen([py, AUDIT, b + "/sitemaps/interrupt.xml", "-o", out, "--delay", "0.5", "--allow-private"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2.6)
    proc.send_signal(signal.SIGINT)
    _, err = proc.communicate(timeout=30)
    f = []
    if proc.returncode != 130:
        f.append("終了コード {}（期待 130）".format(proc.returncode))
    _, header, rows, raw = read_csv(out)
    if header != COLUMNS:
        f.append("ヘッダーが不一致")
    if not (1 <= len(rows) < 10):
        f.append("書き込み済みの行数 {}（期待 1〜9）".format(len(rows)))
    if any(len(r) != 12 for r in raw):
        f.append("12 列でない行がある")
    if "中断しました" not in err or "=== サマリー ===" not in err:
        f.append("中断メッセージかサマリーがない: {}".format(err[-500:]))
    progress = [line for line in err.splitlines() if line.startswith("[") and "/10] " in line]
    if len(progress) != len(rows):
        f.append("進捗行 {} 行と CSV の行数 {} が一致しない".format(len(progress), len(rows)))
    if "書き込み済みの {} 行".format(len(rows)) not in err:
        f.append("中断メッセージの行数が CSV と一致しない")
    # サイトマップの収集中（遅いサイトマップの取得中）に中断
    out2 = os.path.join(OUT, "interrupt_collect.csv")
    if os.path.exists(out2):
        os.remove(out2)
    proc2 = subprocess.Popen([py, AUDIT, b + "/sm/slow.xml", "-o", out2, "--delay", "0.1", "--allow-private"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    proc2.send_signal(signal.SIGINT)
    _, err2 = proc2.communicate(timeout=30)
    if proc2.returncode != 130 or "サイトマップの収集中" not in err2 or os.path.exists(out2):
        f.append("収集中の中断: rc={} csv={} stderr={}".format(proc2.returncode, os.path.exists(out2), err2[-300:]))
    if "Traceback" in err + err2:
        f.append("トレースバックが出ている")
    record("Ctrl+C（SIGINT）で中断", f, ("終了コード 130、書き込み済み {} 行が CSV に残り（進捗行と一致）、サマリーを出力。"
                                      "サイトマップ収集中の中断も 130・CSV なし").format(len(rows)))


def case_units(py, srv):
    spec = importlib.util.spec_from_file_location("audit_mod", AUDIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    n = mod.normalize_url
    f = []
    checks = [
        (n("HTTPS://Example.COM:443/a#x") == n("https://example.com/a"), "スキーム・ホスト・:443・フラグメント"),
        (n("http://example.com:80") == n("http://example.com/"), ":80 と空パス"),
        (n("https://example.com/a/") != n("https://example.com/a"), "末尾スラッシュは不一致"),
        (n("https://example.com/a?x=1") != n("https://example.com/a"), "クエリは不一致"),
        (n("https://example.com:8443/a") != n("https://example.com/a"), "デフォルト以外のポートは不一致"),
        (n("https://example.jp/日本語") == n("https://example.jp/%e6%97%a5%e6%9c%ac%e8%aa%9e"), "日本語パスと小文字 %xx"),
        (n("https://日本語.jp/") == n("https://xn--wgv71a119e.jp/"), "IDN ホスト"),
        (mod.x_robots_noindex(["googlebot: noindex"]) is True, "X-Robots-Tag googlebot: noindex"),
        (mod.x_robots_noindex(["otherbot: noindex"]) is False, "X-Robots-Tag otherbot: noindex"),
        (mod.x_robots_noindex(["NONE"]) is True, "X-Robots-Tag NONE"),
        (mod.x_robots_noindex(["unavailable_after: 25 Jun 2030 15:00:00 PST"]) is False, "unavailable_after"),
        (mod.x_robots_noindex(["max-snippet: 0, noindex"]) is True, "max-snippet の後の noindex"),
        (mod.classify_error(mod.requests.exceptions.ConnectTimeout()) == "ERROR:Timeout", "ConnectTimeout"),
        (mod.classify_error(ValueError()) == "ERROR:ValueError", "その他の例外"),
    ]
    for ok, label in checks:
        if not ok:
            f.append(label)
    record("単体: URL 正規化・X-Robots-Tag・例外分類", f, "{} 項目".format(len(checks)))


def case_py39_syntax(py, srv):
    with open(AUDIT, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src, feature_version=(3, 9))
    f = []
    for node in ast.walk(tree):
        if type(node).__name__ == "Match":
            f.append("match 文 line {}".format(node.lineno))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            f.append("| 演算子 line {}（X|Y 注釈の可能性）".format(node.lineno))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            f.append("関数注釈 line {}".format(node.lineno))
        if isinstance(node, ast.arg) and node.annotation is not None:
            f.append("引数注釈 line {}".format(node.lineno))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "zip" and any(k.arg == "strict" for k in node.keywords):
            f.append("zip(strict=) line {}".format(node.lineno))
    for bad in ["lxml", "import pandas", "removesuffix(", "removeprefix("]:
        if bad in src:
            f.append("{} を使っている".format(bad))
    sys39 = "/usr/bin/python3"
    if os.path.exists(sys39):
        ver = subprocess.run([sys39, "-c", "import sys;print(sys.version.split()[0])"], capture_output=True, text=True).stdout.strip()
        pc = subprocess.run([sys39, "-c", "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8').read())", AUDIT],
                            capture_output=True, text=True)
        if pc.returncode != 0:
            f.append("Python {} で構文エラー: {}".format(ver, pc.stderr[-300:]))
    else:
        ver = "なし"
    pc = subprocess.run([py, "-c", "import py_compile,sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)",
                         AUDIT, os.path.join(OUT, "audit.pyc")], capture_output=True, text=True)
    if pc.returncode != 0:
        f.append("py_compile 失敗: {}".format(pc.stderr))
    record("Python 3.9 互換の文法 + py_compile", f,
           "ast.parse(feature_version=(3,9)) で match 文・| 演算子・関数注釈なし、実機 Python {} で構文解析 OK、py_compile OK".format(ver))


# ---------------------------------------------------------------------------
# 攻撃的テスト（2026-09-25 追加）
# ---------------------------------------------------------------------------

_MOD = {}


def load_module():
    if "m" not in _MOD:
        spec = importlib.util.spec_from_file_location("audit_mod", AUDIT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MOD["m"] = mod
    return _MOD["m"]


def set_robots_mode(srv, mode):
    import urllib.request
    urllib.request.urlopen(srv.base + "/__admin/robots?mode=" + mode, timeout=5).read()


def urls_of(rows):
    return [r["url"] for r in rows]


def no_traceback(proc, f, label=""):
    if "Traceback" in proc.stderr:
        f.append("{}トレースバックが出ている: {}".format(label, proc.stderr[-500:]))


def case_robots_unit(py, srv):
    m = load_module()
    canon = m.robots_canonical_path
    f = []
    n = 0

    def pm(path, pattern):
        return m.robots_pattern_match(canon(path), canon(pattern))

    # Google の robots.txt 仕様の「パスの値に基づく URL の照合」の表
    fish = (["/fish", "/fish.html", "/fish/salmon.html", "/fishheads", "/fishheads/yummy.html",
             "/fish.php?id=anything"], ["/Fish.asp", "/catfish", "/?id=fish", "/desert/fish"])
    table = [
        ("/", ["/", "/a", "/fish.html"], []),
        ("/*", ["/", "/a", "/fish.html"], []),
        ("/$", ["/"], ["/a", "/fish"]),
        ("/fish", fish[0], fish[1]),
        ("/fish*", fish[0], fish[1]),
        ("/fish/", ["/fish/", "/fish/?id=anything", "/fish/salmon.htm"],
         ["/fish", "/fish.html", "/animals/fish/", "/Fish/Salmon.asp"]),
        ("/*.php", ["/index.php", "/filename.php", "/folder/filename.php", "/folder/filename.php?parameters",
                    "/folder/any.php.file.html", "/filename.php/"], ["/", "/windows.PHP"]),
        ("/*.php$", ["/filename.php", "/folder/filename.php"],
         ["/filename.php?parameters", "/filename.php/", "/filename.php5", "/windows.PHP"]),
        ("/fish*.php", ["/fish.php", "/fishheads/catfish.php?parameters"], ["/Fish.PHP"]),
    ]
    for pattern, yes, no in table:
        for path in yes:
            n += 1
            if not pm(path, pattern):
                f.append("{} は {} に一致するはず".format(pattern, path))
        for path in no:
            n += 1
            if pm(path, pattern):
                f.append("{} は {} に一致しないはず".format(pattern, path))

    # 優先順位の例（最長一致、同じ長さなら Allow）
    prec = [
        ("/page", [("/p", True), ("/", False)], True),
        ("/folder/page", [("/folder", True), ("/folder", False)], True),
        ("/page.htm", [("/page", True), ("/*.htm", False)], False),
        ("/page.php5", [("/page", True), ("/*.ph", False)], True),
        ("/", [("/$", True), ("/", False)], True),
        ("/page.htm", [("/$", True), ("/", False)], False),
    ]
    for path, rules, exp in prec:
        n += 1
        got = m.RobotsRules([(canon(p), a) for p, a in rules], "t").allowed_path(canon(path))
        if got != exp:
            f.append("優先順位 {} {}: got={} exp={}".format(path, rules, got, exp))

    def blocked(text, tokens, path):
        return not m.select_robots_rules(m.parse_robots(text), tokens).allowed_path(canon(path))

    ua_text = ("user-agent: googlebot-news\ndisallow: /news\n\n"
               "user-agent: *\ndisallow: /star\n\n"
               "user-agent: googlebot\ndisallow: /gb\n")
    ua_checks = [
        (["googlebot-news", "googlebot"], "/news", True), (["googlebot-news", "googlebot"], "/gb", False),
        (["googlebot-news", "googlebot"], "/star", False),
        (["googlebot"], "/gb", True), (["googlebot"], "/news", False), (["googlebot"], "/star", False),
        (["storebot-google"], "/star", True), (["storebot-google"], "/gb", False),
        (["otherbot"], "/star", True),
    ]
    for tokens, path, exp in ua_checks:
        n += 1
        if blocked(ua_text, tokens, path) != exp:
            f.append("UA の選択 {} {}: 期待 blocked={}".format(tokens, path, exp))

    misc = [
        # 同じ UA の複数グループは結合、* とは結合しない
        ("user-agent: a\ndisallow: /c\n\nuser-agent: b\ndisallow: /d\n\nuser-agent: A\ndisallow: /e\n\n"
         "user-agent: *\ndisallow: /f\n", ["a"], [("/c", True), ("/e", True), ("/d", False), ("/f", False)]),
        # sitemap 行はグループを区切らない（a と b の両方に disallow: / が効く）
        ("user-agent: a\nsitemap: https://example.com/sitemap.xml\n\nuser-agent: b\ndisallow: /\n", ["a"],
         [("/x", True)]),
        ("user-agent: a\nsitemap: https://example.com/sitemap.xml\n\nuser-agent: b\ndisallow: /\n", ["b"],
         [("/x", True)]),
        # 最初の User-agent より前のルールは無視
        ("disallow: /x\nuser-agent: *\nallow: /\n", ["zzz"], [("/x", False)]),
        # 空の Disallow は無視（全許可）
        ("user-agent: *\ndisallow:\n", ["zzz"], [("/anything", False)]),
        # googlebot/1.2 と googlebot* は googlebot と同じ
        ("User-agent: googlebot/1.2\nDisallow: /v\n", ["googlebot"], [("/v", True)]),
        ("user-agent: googlebot*\ndisallow: /w\n", ["googlebot"], [("/w", True)]),
        # 「* 」で始まる値は全体向け、*bot はどれにも一致しない
        ("user-agent: * extra\ndisallow: /g\n", ["zzz"], [("/g", True)]),
        ("user-agent: *bot\ndisallow: /g\n", ["zzz"], [("/g", False)]),
        # フィールド名と UA の値の大文字小文字、コメント、コロンのない行
        ("USER-AGENT: ZZZ\nDISALLOW: /u # コメント\nDisallow /nocolon\n", ["zzz"],
         [("/u", True), ("/u#", True), ("/nocolon", False)]),
        # パーセントエンコードの正規化
        ("user-agent: *\ndisallow: /foo/bar/ツ\n", ["zzz"], [("/foo/bar/%E3%83%84", True)]),
        ("user-agent: *\ndisallow: /foo/bar/%E3%83%84\n", ["zzz"], [("/foo/bar/ツ", True)]),
        ("user-agent: *\ndisallow: /foo/bar/%e3%83%84\n", ["zzz"], [("/foo/bar/%E3%83%84", True)]),
        ("user-agent: *\ndisallow: /foo/bar/%62%61%7A\n", ["zzz"], [("/foo/bar/baz", True)]),
        ("user-agent: *\ndisallow: /a%2Fb\n", ["zzz"], [("/a/b", False), ("/a%2fb", True)]),
        ("user-agent: *\ndisallow: /a b\n", ["zzz"], [("/a%20b", True)]),
        # 途中の $ はただの文字、クエリも照合対象
        ("user-agent: *\ndisallow: /a$b\n", ["zzz"], [("/a$bc", True), ("/ab", False)]),
        ("user-agent: *\ndisallow: /*?\n", ["zzz"], [("/p?x=1", True), ("/p", False)]),
        # /robots.txt は常に許可、グループがなければ全許可
        ("user-agent: *\ndisallow: /\n", ["zzz"], [("/robots.txt", False), ("/", True)]),
        ("", ["zzz"], [("/x", False)]),
        # CR だけの改行、CRLF
        ("user-agent: *\rdisallow: /cr\r", ["zzz"], [("/cr", True)]),
        ("user-agent: *\r\ndisallow: /crlf\r\n", ["zzz"], [("/crlf", True)]),
    ]
    for text, tokens, checks in misc:
        for path, exp in checks:
            n += 1
            if blocked(text, tokens, path) != exp:
                f.append("robots {!r} {} {}: 期待 blocked={}".format(text[:60], tokens, path, exp))

    targets = [
        ("http://h:80/a/b?x=1#frag", "/a/b?x=1"), ("http://h", "/"), ("http://h?q=1", "/?q=1"),
        ("https://h/日本?q=あ", "/%E6%97%A5%E6%9C%AC?q=%E3%81%82"), ("https://h/%7euser", "/~user"),
    ]
    for url, exp in targets:
        n += 1
        if m.robots_target(url) != exp:
            f.append("robots_target({}) = {} (期待 {})".format(url, m.robots_target(url), exp))
    for ua, exp in [(DEFAULT_UA, "seo-operator-audit"), ("Mozilla/5.0 (x)", "mozilla"), ("(x)", "")]:
        n += 1
        if m.product_token(ua) != exp:
            f.append("product_token({!r}) = {!r}".format(ua, m.product_token(ua)))

    # * の多いパターンでも暴走しない
    t0 = time.monotonic()
    bad = m.robots_pattern_match("/" + "a" * 20000, "/" + "*a" * 40 + "*b")
    dt = time.monotonic() - t0
    n += 1
    if bad or dt > 0.5:
        f.append("* が多いパターン: result={} {:.3f}s".format(bad, dt))
    record("robots.txt 判定（単体）: Google の照合表・優先順位・UA の選択・結合・正規化", f,
           "{} 項目（* が 41 個のパターンと 2 万文字のパスで {:.4f} 秒）".format(n, dt))


def _sitemap_xml(urls, extra=""):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join("<url><loc>{}</loc>{}</url>".format(u, extra) for u in urls) + "</urlset>").encode("utf-8")


def case_sitemap_unit(py, srv):
    import gzip as gz
    m = load_module()
    f = []
    urls = ["https://example.com/p/{}".format(i) for i in range(50000)]
    xml = _sitemap_xml(urls, "<lastmod>2026-09-01</lastmod>")
    t0 = time.monotonic()
    kind, locs = m.parse_sitemap(xml)
    dt = time.monotonic() - t0
    if kind != "urlset" or locs != urls:
        f.append("5 万件: kind={} 件数={}".format(kind, len(locs)))
    if dt > 5:
        f.append("5 万件の解析に {:.2f} 秒".format(dt))
    kind, locs = m.parse_sitemap(gz.compress(xml))
    if locs != urls:
        f.append(".xml.gz の 5 万件が一致しない")
    urlset_all = set(urls)

    def expect(data, exp_locs=None, note=None, error=None, label=""):
        notes = []
        try:
            kind, locs = m.parse_sitemap(data, notes)
        except Exception as exc:
            if error is None or error not in str(exc):
                f.append("{}: 例外 {}".format(label, exc))
            return None
        if error is not None:
            f.append("{}: 例外になるはず（{}）".format(label, error))
            return None
        if exp_locs is not None and locs != exp_locs:
            f.append("{}: locs={}".format(label, locs[:5]))
        if note is not None and not any(note in x for x in notes):
            f.append("{}: 注意 {!r} がない: {}".format(label, note, notes))
        return locs

    half = expect(xml[:len(xml) // 2], note="途中で切れているか壊れています", label="途中で切れた XML")
    if half is not None and (not (0 < len(half) < 50000) or not set(half) <= urlset_all):
        f.append("途中で切れた XML: {} 件（完全な URL だけのはず）".format(len(half)))
    cz = gz.compress(xml)
    half = expect(cz[:len(cz) // 2], note="gzip が途中で切れているか壊れています", label="途中で切れた gzip")
    if half is not None and (not (0 < len(half) < 50000) or not set(half) <= urlset_all):
        f.append("途中で切れた gzip: {} 件".format(len(half)))
    expect(b'<?xml version="1.0"?><urlset><url><lo', error="XML として解析できません", label="先頭で壊れた XML")
    expect(_sitemap_xml(["https://e.com/a"]) + b"<junk>", ["https://e.com/a"], note="壊れる前までの 1 件",
           label="ルート要素の後のゴミ")
    dtd = '<?xml version="1.0"?>\n<!DOCTYPE x [<!ENTITY a "b">]>\n<urlset><url><loc>https://e.com/&a;</loc></url></urlset>'
    expect(dtd.encode("utf-8"), error="DOCTYPE / ENTITY", label="DTD（UTF-8）")
    expect(dtd.replace('<?xml version="1.0"?>', '<?xml version="1.0" encoding="UTF-16"?>').encode("utf-16"),
           error="DOCTYPE / ENTITY", label="DTD（UTF-16。バイト列の検索をすり抜けないこと）")
    u16 = _sitemap_xml(["https://e.com/u16"]).decode("utf-8").replace('encoding="UTF-8"', 'encoding="UTF-16"')
    expect(u16.encode("utf-16"), ["https://e.com/u16"], note="UTF-16", label="UTF-16")
    sj = '<?xml version="1.0" encoding="Shift_JIS"?><urlset><url><loc>https://e.com/日本</loc></url></urlset>'
    expect(sj.encode("cp932"), ["https://e.com/日本"], note="Shift_JIS", label="Shift_JIS 宣言")
    expect(b"<!DOCTYPE html><html><body>404</body></html>", error="HTML のページ", label="HTML")
    expect(b'<?xml version="1.0"?>\n<!-- x --><html xmlns="http://www.w3.org/1999/xhtml"><body/></html>',
           error="HTML のページ", label="XHTML")
    expect(b'<?xml version="1.0"?><!-- <html> --><urlset><url><loc>https://e.com/c</loc></url></urlset>',
           ["https://e.com/c"], label="コメント内の <html> を HTML と誤判定しない")
    expect("https://e.com/1\nhttps://e.com/2\n".encode("utf-16"), ["https://e.com/1", "https://e.com/2"],
           label="UTF-16 のテキストサイトマップ")
    expect(b"<foo><loc>https://e.com/</loc></foo>", error="ルート要素 <foo>", label="未知のルート")
    expect(b"\xef\xbb\xbf" + _sitemap_xml(["https://e.com/bom"]), ["https://e.com/bom"], label="BOM")
    expect(b"<urlset><url><loc><![CDATA[ https://e.com/c?a=1&b=2 ]]></loc></url>"
           b"<url><loc>\n\t https://e.com/w \n</loc></url><url><loc>https://e.com/t\tab</loc></url></urlset>",
           ["https://e.com/c?a=1&b=2", "https://e.com/w", "https://e.com/tab"], label="CDATA・空白・タブ")
    expect(b"\xef\xbb\xbfhttps://e.com/1\r\n\r\nhttps://e.com/2\r\n# x\r\n", ["https://e.com/1", "https://e.com/2"],
           label="テキスト（BOM・CRLF）")
    expect(b'<rss version="2.0"><channel><link>https://e.com/</link><item><link>https://e.com/i</link></item>'
           b"</channel></rss>", ["https://e.com/i"], label="RSS 2.0")
    expect(b'<feed xmlns="http://www.w3.org/2005/Atom"><link href="https://e.com/"/><entry>'
           b'<link rel="self" href="https://e.com/s"/><link rel="alternate" href="https://e.com/a"/></entry></feed>',
           ["https://e.com/a"], label="Atom")
    record("サイトマップの解析（単体）", f,
           "5 万 URL を {:.2f} 秒で解析、gzip・途中切れ（XML / gzip）・ゴミ・DTD（UTF-8 / UTF-16）・UTF-16・"
           "Shift_JIS・HTML・未知のルート・BOM・CDATA・テキスト・RSS・Atom".format(dt))


def case_html_unit(py, srv):
    m = load_module()
    f = []
    from bs4 import BeautifulSoup
    notes = []
    html = ('<html><head><meta charset="Shift_JIS"><title>シフトJIS①</title></head></html>').encode("cp932")
    text = m.decode_html(html, "text/html; charset=utf-8", notes)
    if "シフトJIS①" not in (text or "") or not any("meta の charset（shift_jis）で読みました" in x.lower() for x in notes):
        f.append("ヘッダーの charset が誤り: {} {}".format((text or "")[:80], notes))
    notes = []
    text = m.decode_html('<html><head><meta charset="utf-8"><title>誤り</title></head></html>'.encode("cp932"),
                         "text/html", notes)
    if "誤り" not in (text or "") or not any("cp932 として読みました" in x for x in notes):
        f.append("meta の charset が誤り: {}".format(notes))
    notes = []
    text = m.decode_html("<title>不明</title>".encode("utf-8"), "text/html; charset=x-unknown-9", notes)
    if "不明" not in (text or "") or not notes:
        f.append("不明な charset: {} {}".format(text, notes))
    notes = []
    text = m.decode_html("<title>EUC①</title>".encode("euc_jis_2004"), "text/html; charset=EUC-JP", notes)
    if "EUC①" not in (text or "") or notes:
        f.append("EUC-JP（①を含む）で注意が出た: {}".format(notes))
    soup = BeautifulSoup("<html><head><title>foo <b>bar</b> &amp; baz</title></head></html>", "html.parser")
    if m.rcdata_text(soup.find("title")) != "foo <b>bar</b> & baz":
        f.append("title 内のタグ: {!r}".format(m.rcdata_text(soup.find("title"))))
    notes = []
    soup = BeautifulSoup('<html><head><title>x</title><img src=a><link rel=canonical href=/b></head></html>',
                         "html.parser")
    if m.find_canonicals(soup, "https://e.com/a", notes) or not any("<img> より後" in x for x in notes):
        f.append("<img> の後の canonical: {}".format(notes))
    notes = []
    soup = BeautifulSoup('<html><head><title>x</title><link rel=canonical href=/a><body><p>y</p></body></html>',
                         "html.parser")
    if m.find_canonicals(soup, "https://e.com/a", notes) != ["https://e.com/a"] or notes:
        f.append("</head> なし: {}".format(notes))
    got = m.canonical_from_headers(['<https://e.com/a>; rel="canonical", </b>; rel=canonical'], "https://e.com/x")
    if got != ["https://e.com/a", "https://e.com/b"]:
        f.append("Link ヘッダーの複数 canonical: {}".format(got))
    notes = []
    if len(m.cell_text("あ" * 40000, "title", notes)) != 32767 or not notes:
        f.append("Excel の上限")
    for values, exp in [(["noindex, nofollow"], True), (["nofollow"], False),
                        (["googlebot: nofollow", "otherbot: noindex"], False), (["GoogleBot: NoIndex"], True)]:
        if m.x_robots_noindex(values) is not exp:
            f.append("X-Robots-Tag {}".format(values))
    record("HTML の解析（単体）: 文字コードの誤り・title 内のタグ・<head> の途中終了・Link ヘッダー", f,
           "charset の誤り 4 種、title 内のタグ（Python のバージョン差を吸収）、<img> の後の canonical、"
           "</head> の書き忘れ、Link の複数 canonical、Excel の上限、X-Robots-Tag 4 種")


def case_sitemap_attack(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "sm_messy.csv")
    proc, _ = run_audit(py, [b + "/sm/messy.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    exp = [b + "/p/english", b + "/p/two-h1", b + "/h/entity-title?a=1&b=2", b + "/p/no-desc", b + "/p/no-title",
           b + "/P/English", b + "/p/ja-normal"]
    if urls_of(rows) != exp:
        f.append("messy の URL: {}".format(urls_of(rows)))
    if [r["status"] for r in rows] != ["200", "200", "200", "200", "200", "404", "200"]:
        f.append("messy の status: {}".format([r["status"] for r in rows]))
    for needle in ["http / https 以外の URL の loc をスキップ: mailto:someone@example.com",
                   "http / https 以外の URL の loc をスキップ: javascript:alert(1)",
                   "http / https 以外の URL の loc をスキップ: ftp://127.0.0.1/file.txt",
                   "空の loc（URL のない項目）3 件", "スキップした loc 6 件"]:
        if needle not in proc.stderr:
            f.append("messy の stderr に {!r} がない".format(needle))
    if proc.returncode != 0:
        f.append("messy rc={}".format(proc.returncode))

    variants = [
        ("/sm/bom.xml", [b + "/p/english"], None),
        ("/sm/ws-bom.xml", [b + "/p/two-h1"], None),
        ("/sm/utf16.xml", [b + "/p/english"], "サイトマップの文字コードが UTF-16 です"),
        ("/sm/sjis.xml", [b + "/p/日本語"], "サイトマップの文字コードが Shift_JIS です"),
        ("/sm/html-ct.xml", [b + "/p/english"], None),
        ("/sm/ce-gzip.xml", [b + "/p/english", b + "/p/two-h1"], None),
        ("/sm/double.xml.gz", [b + "/p/no-title"], None),
        ("/sm/truncated.xml", [b + "/p/english", b + "/p/two-h1"], "壊れる前までの 2 件だけを使います"),
        ("/sm/redirect.xml", [b + "/sm/sub/english-rel"], None),
    ]
    for path, exp_urls, needle in variants:
        out = os.path.join(OUT, "sm_{}.csv".format(path.split("/")[-1].replace(".", "_")))
        proc, _ = run_audit(py, [b + path, "-o", out, "--delay", "0.05", "--ignore-robots"])
        no_traceback(proc, f, path + ": ")
        _, _, rows, _ = read_csv(out)
        if proc.returncode != 0 or urls_of(rows) != exp_urls:
            f.append("{}: rc={} urls={} stderr={}".format(path, proc.returncode, urls_of(rows), proc.stderr[-300:]))
        elif any(r["status"] != "200" for r in rows):
            f.append("{}: status {}".format(path, [r["status"] for r in rows]))
        if needle and needle not in proc.stderr:
            f.append("{}: stderr に {!r} がない".format(path, needle))
    out = os.path.join(OUT, "sm_truncated_gz.csv")
    proc, _ = run_audit(py, [b + "/sm/truncated.xml.gz", "-o", out, "--delay", "0.05", "--ignore-robots",
                             "--limit", "1"])
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or urls_of(rows) != [b + "/p/english"] or \
            "gzip が途中で切れているか壊れています" not in proc.stderr or "壊れる前までの" not in proc.stderr:
        f.append("途中で切れた .xml.gz: rc={} {} {}".format(proc.returncode, urls_of(rows), proc.stderr[-400:]))

    for path, needle in [("/sm/broken-early.xml", "XML として解析できません"),
                         ("/sm/html-page.xml", "HTML のページが返されました"),
                         ("/sm/utf16-dtd.xml", "DOCTYPE / ENTITY")]:
        out = os.path.join(OUT, "sm_fail.csv")
        if os.path.exists(out):
            os.remove(out)
        proc, _ = run_audit(py, [b + path, "-o", out, "--delay", "0.05"])
        no_traceback(proc, f, path + ": ")
        if proc.returncode != 2 or needle not in proc.stderr or os.path.exists(out):
            f.append("{}: rc={} csv={} stderr={}".format(path, proc.returncode, os.path.exists(out), proc.stderr[-300:]))
    record("サイトマップの攻撃（空白・CDATA・実体参照・相対・スキーム・空の loc・重複・BOM・UTF-16・Shift_JIS・"
           "text/html・Content-Encoding・二重 gzip・途中切れ・リダイレクト後の相対 URL・HTML・DTD）", f,
           "messy 7 行（mailto / javascript / ftp / 空 3 件をスキップ、HTTP:// と #frag の重複を除去、/P/English は別 URL）、"
           "変種 9 本・途中切れ gzip・失敗 3 本（終了コード 2、CSV なし）")


def case_feeds(py, srv):
    b = srv.base
    f = []
    cases = [
        ("/f/rss.xml", [b + "/p/english", b + "/p/two-h1", b + "/p/no-desc"], "空の loc（URL のない項目）1 件"),
        ("/f/atom.xml", [b + "/p/english", b + "/p/two-h1", b + "/p/no-desc", b + "/p/no-title"],
         "空の loc（URL のない項目）1 件"),
        ("/f/rdf.xml", [b + "/p/english"], None),
        ("/f/atom03.xml", [b + "/p/two-h1"], None),
        ("/sm/index-mixed.xml", [b + "/p/english", b + "/p/two-h1", b + "/p/no-desc", b + "/p/no-title"],
         "http / https 以外の URL の loc をスキップ: mailto:x@example.com"),
    ]
    for path, exp_urls, needle in cases:
        out = os.path.join(OUT, "feed_{}.csv".format(path.split("/")[-1].replace(".", "_")))
        proc, log = run_audit(py, [b + path, "-o", out, "--delay", "0.05", "--ignore-robots"])
        no_traceback(proc, f, path + ": ")
        _, _, rows, _ = read_csv(out)
        if proc.returncode != 0 or urls_of(rows) != exp_urls:
            f.append("{}: rc={} urls={} stderr={}".format(path, proc.returncode, urls_of(rows), proc.stderr[-300:]))
        if "フィード（RSS / Atom）" not in proc.stderr:
            f.append("{}: 種類がフィードと表示されない".format(path))
        if needle and needle not in proc.stderr:
            f.append("{}: stderr に {!r} がない".format(path, needle))
        bad = [e["path"] for e in log if e["path"] in ("/", "/wrong", "/api/1", "/edit/4", "/x.mp3", "/p/guid-only")]
        if bad:
            f.append("{}: 項目の URL でないものを取得した: {}".format(path, bad))
    record("RSS 2.0 / Atom のフィード", f,
           "RSS 2.0（channel の link・atom:link・guid を無視、CDATA・空白・相対）、Atom 1.0（self / edit / enclosure を"
           "無視、xml:base の相対解決）、RSS 1.0、Atom 0.3、インデックスからのフィード参照")


def case_non_html(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "non_html.csv")
    proc, _ = run_audit(py, [b + "/sm/non-html.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [
        (b + "/p/doc.pdf", E("200", canonical=b + "/p/doc.pdf", mismatch="False", noindex="False")),
        (b + "/x/noindex.pdf", E("200", canonical=b + "/p/doc.pdf", mismatch="True", noindex="True")),
        (b + "/x/googlebot-noindex.pdf", E("200", canonical=b + "/x/other.pdf", mismatch="True", noindex="True")),
        (b + "/x/nolink.png", E("200", noindex="False")),
        (b + "/x/no-ct-binary", E("200", noindex="False")),
        (b + "/x/pdf-404", E("404")),
        (b + "/x/redirect-pdf", E("301>200", redirect_to=b + "/x/noindex.pdf", canonical=b + "/p/doc.pdf",
                                  mismatch="True", noindex="True")),
        (b + "/x/two-link.pdf", E("200", canonical=b + "/x/two-link.pdf", mismatch="False", noindex="False")),
        (b + "/x/empty-200", E("200", noindex="False")),
    ], f)
    for needle in ['Link ヘッダーに異なる rel="canonical" が 2 個あります',
                   "HTML 以外（HTTP ヘッダーの canonical と X-Robots-Tag だけを記録）: 8 件",
                   "HTML を解析したページ: 0 件", "noindex: 3 件", "canonical 不一致: 3 件",
                   "title なし（空を含む）: 0 件"]:
        if needle not in proc.stderr:
            f.append("stderr に {!r} がない".format(needle))
    record("HTML でない 2xx（PDF など）: Link ヘッダーの canonical と X-Robots-Tag", f,
           "9 行: canonical・canonical_mismatch・robots_noindex を記録し title〜word_count は空欄、404 の PDF は "
           "status のみ、リダイレクト後の PDF、otherbot 向けは数えない、Content-Type なしのバイナリと空の 200")


def case_html_attack(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "html_attack.csv")
    proc, _ = run_audit(py, [b + "/sm/html-attack.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    expected = [
        (b + "/h/entity-title", P("A & B <C> あ", 11)),
        (b + "/h/tag-in-title", P("foo <b>bar</b>", 14)),
        (b + "/h/desc-upper", P("大文字", 3, desc="大文字の説明", desc_len=6)),
        (b + "/h/desc-property", P("プロパティ", 5, desc="", desc_len=0)),
        (b + "/h/desc-two", P("説明2個", 4, desc="一つ目", desc_len=3)),
        (b + "/h/canonical-two-same", P("同じ2個", 4, canonical=b + "/h/canonical-two-same", mismatch="False")),
        (b + "/h/canonical-two-diff", P("異なる2個", 5, canonical=b + "/h/canonical-two-diff", mismatch="False")),
        (b + "/h/canonical-ws", P("空白", 2, canonical=b + "/h/canonical-ws", mismatch="False")),
        (b + "/h/canonical-after-img", P("画像の後", 4, canonical="", mismatch="")),
        (b + "/h/canonical-noclose-head", P("閉じなし", 4, canonical=b + "/h/canonical-noclose-head",
                                            mismatch="False")),
        (b + "/h/canonical-vs-header", P("食い違い", 4, canonical=b + "/h/canonical-vs-header", mismatch="False")),
        (b + "/h/xrobots-combo", P("組み合わせ", 5, noindex="True")),
        (b + "/h/xrobots-nofollow", P("nofollowのみ", 10, noindex="False")),
        (b + "/h/no-ct", P("ヘッダーなし", 6)),
        (b + "/h/wrong-charset-header", P("シフトJIS①", 7)),
        (b + "/h/wrong-charset-nometa", P("EUCのページ", 7)),
        (b + "/h/meta-wrong", P("メタが誤り", 5)),
        (b + "/h/title-two", P("一つ目のtitle", 9)),
    ]
    compare_rows([r for r in rows if r["url"] not in (b + "/h/long-title", b + "/h/unclosed-title")], expected, f)
    by = {r["url"]: r for r in rows}
    long_row = by.get(b + "/h/long-title", {})
    if long_row.get("title") != "あ" * 32767 or long_row.get("title_len") != "40000":
        f.append("long-title: セル {} 文字 / title_len {}".format(len(long_row.get("title", "")), long_row.get("title_len")))
    un = by.get(b + "/h/unclosed-title", {})
    if un.get("status") != "200" or not (un.get("title") == "閉じていない" or "title にタグのような文字列" in proc.stderr):
        f.append("unclosed-title: {}".format(un))
    err = proc.stderr
    for needle in ['<meta name="description"> が 2 個あります。最初のものを採用しました',
                   '<head> に置けない要素 <img> より後にある rel="canonical" を無視しました',
                   "HTML と Link ヘッダーで canonical が異なります（HTML を採用）",
                   "Content-Type ヘッダー の charset（utf-8）では読めないため、meta の charset（shift_jis）で読みました",
                   "euc_jp として読みました", "cp932 として読みました",
                   "title が 40000 文字あり、Excel の1セルの上限（32767 文字）",
                   "title にタグのような文字列が含まれています", "<title> が 2 個あります。最初のものを採用しました"]:
        if needle.lower() not in err.lower():
            f.append("stderr に {!r} がない".format(needle))
    if err.count('<head> 内に異なる rel="canonical"') != 1:
        f.append("異なる canonical の注意が {} 回（two-diff の 1 回だけのはず）".format(
            err.count('<head> 内に異なる rel="canonical"')))
    if "<head> に置けない要素 <body>" in err:
        f.append("</head> の書き忘れを不正な要素として扱った")
    record("HTML の攻撃（実体参照・title 内のタグ・Description・property・description 2個・canonical 2個・"
           "href の空白・<img> の後・</head> なし・Link との食い違い・X-Robots-Tag・Content-Type なし・charset の誤り・"
           "長い title・閉じていない title・title 2個）", f, "20 行・全列一致と stderr の注意 11 種")


def case_http_attack(py, srv):
    b = srv.base
    loc = "http://localhost:{}".format(srv.port)
    set_robots_mode(srv, "complex")
    f = []
    out = os.path.join(OUT, "http_attack.csv")
    proc, log = run_audit(py, [b + "/sm/http-attack.xml", "-o", out, "--delay", "0.05", "--timeout", "2"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [
        (b + "/r/cross-host", P("English Page", 12, wc=14, desc="An English description.", desc_len=23,
                                status="301>200", redirect_to=loc + "/p/english")),
        (b + "/r/to-https", E("BLOCKED:robots-unreachable", redirect_to="https://127.0.0.1:{}/p/x".format(srv.ssl_port))),
        (b + "/r/a/b/rel", P("English Page", 12, wc=14, desc="An English description.", desc_len=23,
                             status="302>200", redirect_to=b + "/p/english")),
        (b + "/r/no-location", E("301")),
        (b + "/r/empty-location", E("302")),
        (b + "/r/to-mailto", E("ERROR:InvalidSchema")),
        (b + "/r/to-real-https", P("English Page", 12, wc=14, desc="An English description.", desc_len=23,
                                   status="301>200", redirect_to="https://localhost:{}/p/english".format(srv.https_port))),
    ], f)
    if not srv.https_port:
        f.append("HTTPS サーバーが起動していない（openssl で証明書を作れなかった）")
    robots = [(e["host"], e["path"]) for e in log if e["path"] == "/robots.txt"]
    if sorted(robots) != sorted([("127.0.0.1:{}".format(srv.port), "/robots.txt"),
                                 ("localhost:{}".format(srv.port), "/robots.txt"),
                                 ("localhost:{}".format(srv.https_port), "/robots.txt")]):
        f.append("robots.txt の取得（ホストごとに1回ずつのはず）: {}".format(robots))
    if not any(e["host"].startswith("localhost") and e["path"] == "/p/english" for e in log):
        f.append("別ホストのリダイレクト先を取得していない")
    for needle in ["ステータス 301 ですが Location ヘッダーがない", "ステータス 302 ですが Location ヘッダーがない",
                   "警告: robots.txt を取得できませんでした（ERROR:SSLError）",
                   "User-agent: seo-operator-audit のグループを適用"]:
        if needle not in proc.stderr:
            f.append("stderr に {!r} がない".format(needle))
    record("HTTP の攻撃（ホストをまたぐリダイレクト・http→https・相対 Location・Location なし / 空・mailto:）", f,
           "7 行一致。http://127.0.0.1 → http://localhost と http://127.0.0.1 → https://localhost（自己署名証明書の"
           "本物の TLS）の両方で、リダイレクト先のホストの robots.txt をホストごとに1回だけ取得して判定。"
           "偽 TLS への移動は、移動先の robots.txt を取得できないため BLOCKED:robots-unreachable と警告")


def case_robots_integration(py, srv):
    b = srv.base
    loc = "http://localhost:{}".format(srv.port)
    set_robots_mode(srv, "complex")
    f = []
    paths = ["/p/english", "/x/nolink.png", "/x/noindex.pdf", "/x/noindex.pdf?download=1", "/p/no-title",
             "/p/no-desc", "/p/日本語", "/p/two-h1", "/p/two-h1?x=1", "/p/ja-normal", "/p/ja-article"]
    blocked_default = {"/x/noindex.pdf", "/p/no-desc", "/p/日本語", "/p/two-h1", "/p/ja-article"}
    runs = [
        ([], blocked_default, "User-agent: seo-operator-audit のグループを適用、ルール 7 件"),
        (["--user-agent", "OtherBot/1.0 (+test)"], {"/p/english"}, "User-agent: otherbot のグループを適用、ルール 1 件"),
        (["--user-agent", "(test) no token"], set(paths), "User-agent: * のグループを適用、ルール 1 件"),
    ]
    for extra, blocked, needle in runs:
        out = os.path.join(OUT, "robots_int.csv")
        proc, log = run_audit(py, [b + "/sm/robots-localhost.xml", "-o", out, "--delay", "0.05",
                                   "--allow-other-hosts"] + extra)
        no_traceback(proc, f)
        _, _, rows, _ = read_csv(out)
        got = {r["url"][len(loc):]: r["status"] for r in rows}
        for p in paths:
            want_blocked = p in blocked
            is_blocked = got.get(p) == "BLOCKED:robots.txt"
            if want_blocked != is_blocked:
                f.append("{} {}: status={}（期待 {}）".format(extra or "既定 UA", p, got.get(p),
                                                        "BLOCKED" if want_blocked else "取得"))
        fetched = [e["raw"] for e in log if e["host"].startswith("localhost") and e["path"] != "/robots.txt"]
        for p in blocked:
            if requests_quote(p) in fetched:
                f.append("{}: 除外した {} を取得した".format(extra or "既定 UA", p))
        if needle not in proc.stderr:
            f.append("{}: stderr に {!r} がない".format(extra or "既定 UA", needle))
    record("robots.txt 判定（結合）: グループの結合・大文字小文字・$・最長一致・Allow 優先・%XX の正規化・UA ごとの選択", f,
           "既定 UA で 11 URL 中 5 件を除外（除外した URL へのアクセス 0 回）、otherbot は 1 件、トークンなしは * で全件")


def requests_quote(path):
    from urllib.parse import quote
    return quote(path, safe="/?=&%")


def case_robots_status(py, srv):
    b = srv.base
    f = []
    deny = "--ignore-robots を付けて実行し直して"
    both = ["/p/english", "/p/two-h1"]
    unreachable = {"500", "503", "429", "slow"}  # 5xx・タイムアウトは RFC 9309、429 は Google の仕様に合わせて全拒否
    modes = [
        ("404", [], "robots.txt がありません（ステータス 404）", None),
        ("403", [], "robots.txt がありません（ステータス 403）", None),
        ("500", both, "警告: robots.txt を取得できませんでした（ステータス 500）", deny),
        ("503", both, "警告: robots.txt を取得できませんでした（ステータス 503）", deny),
        ("429", both, "警告: robots.txt を取得できませんでした（ステータス 429）", deny),
        ("slow", both, "警告: robots.txt を取得できませんでした（ERROR:Timeout）", deny),
        ("redirect", ["/p/english"], "User-agent: * のグループを適用、ルール 1 件", None),
        ("loop", [], "robots.txt のリダイレクトが多すぎます", None),
        ("html", [], "該当するグループなし、ルール 0 件", None),
        ("bom-cr", ["/p/english"], "User-agent: * のグループを適用、ルール 1 件", None),
        ("big", [], "500 KiB を超えた部分は無視", None),
        ("cut", [], "500 KiB を超えた部分は無視", "ルール 0 件"),
    ]
    loc = "http://localhost:{}".format(srv.port)
    try:
        for mode, blocked, needle, needle2 in modes:
            set_robots_mode(srv, mode)
            out = os.path.join(OUT, "robots_status.csv")
            proc, _ = run_audit(py, [b + "/sm/robots-status.xml", "-o", out, "--delay", "0.05", "--timeout", "1",
                                     "--allow-other-hosts"])
            no_traceback(proc, f, mode + ": ")
            _, _, rows, _ = read_csv(out)
            got = {r["url"][len(loc):]: r["status"] for r in rows}
            for p in both:
                blocked_status = "BLOCKED:robots-unreachable" if mode in unreachable else "BLOCKED:robots.txt"
                exp = blocked_status if p in blocked else "200"
                if got.get(p) != exp:
                    f.append("{}: {} status={}（期待 {}）".format(mode, p, got.get(p), exp))
            for nd in [needle, needle2] + (["robots.txt を取得できずに除外: 2 件"] if mode in unreachable else []):
                if nd and nd not in proc.stderr:
                    f.append("{}: stderr に {!r} がない".format(mode, nd))
            if proc.returncode != 0:
                f.append("{}: rc={}".format(mode, proc.returncode))
    finally:
        set_robots_mode(srv, "complex")
    record("robots.txt の取得結果（4xx・5xx・429・タイムアウト・リダイレクト・ループ・HTML・BOM と CR・500 KiB 超）", f,
           "4xx は全許可、5xx・タイムアウトは RFC 9309、429 は Google の仕様に合わせて全拒否（BLOCKED:robots-unreachable）し --ignore-robots を案内、リダイレクト先の内容を適用、"
           "ループは 4xx 扱い、BOM と CR 改行を解釈、500 KiB より後の行と境目で切れた行は無視")


def case_args(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "args_should_not_exist.csv")
    if os.path.exists(out):
        os.remove(out)
    small = b + "/sitemaps/small.xml"
    bad = [
        (["--limit", "0"], "1 以上の整数を指定してください: 0"),
        (["--limit", "1.5"], "1 以上の整数を指定してください: 1.5"),
        (["--limit", "abc"], "1 以上の整数を指定してください: abc"),
        (["--delay", "nan"], "0 以上 3600 以下の秒数を指定してください: nan"),
        (["--delay", "inf"], "0 以上 3600 以下の秒数を指定してください: inf"),
        (["--delay", "1e12"], "0 以上 3600 以下の秒数を指定してください: 1e12"),
        (["--timeout", "0"], "0 より大きく 3600 以下の秒数を指定してください: 0"),
        (["--timeout", "inf"], "0 より大きく 3600 以下の秒数を指定してください: inf"),
        (["--max-depth", "51"], "0 から 50 までの整数を指定してください: 51"),
    ]
    for args, needle in bad:
        proc, _ = run_audit(py, [small, "-o", out] + args)
        no_traceback(proc, f, "{}: ".format(args))
        if proc.returncode != 2 or needle not in proc.stderr:
            f.append("{}: rc={} stderr={}".format(args, proc.returncode, proc.stderr[-200:]))
    sources = [
        ("example.com/sitemap.xml", "先頭に https:// を付けてください（例: https://example.com/sitemap.xml）"),
        ("www.example.com", "先頭に https:// を付けてください"),
        ("ftp://example.com/sitemap.xml", "ftp: の URL には対応していません"),
        ("file:///etc/hosts", "file: の URL には対応していません"),
        (OUT, "フォルダが指定されています"),
        ("https://", "URL にホスト名がありません"),
        ("http://[::1", "URL として解釈できません"),
        ("", "サイトマップが見つかりません"),
        ("   ", "サイトマップが見つかりません"),
        ("no_such_file.xml", "サイトマップが見つかりません"),
    ]
    for source, needle in sources:
        proc, _ = run_audit(py, [source, "-o", out])
        no_traceback(proc, f, "{!r}: ".format(source))
        if proc.returncode != 2 or needle not in proc.stderr:
            f.append("{!r}: rc={} stderr={}".format(source, proc.returncode, proc.stderr[-200:]))
    proc, _ = run_audit(py, ["no_such_file.xml", "-o", out])
    if "先頭に https:// を付けて" in proc.stderr:
        f.append("存在しないファイル名に https:// を勧めている")
    if os.path.exists(out):
        f.append("終了コード 2 なのに CSV が作られた")
    same = os.path.join(OUT, "same_in_out.xml")
    content = _sitemap_xml([b + "/p/english"])
    with open(same, "wb") as fh:
        fh.write(content)
    proc, _ = run_audit(py, [same, "-o", same])
    with open(same, "rb") as fh:
        after = fh.read()
    if proc.returncode != 2 or "入力のサイトマップと同じファイル" not in proc.stderr or after != content:
        f.append("入力と出力が同じ: rc={} 内容が保たれた={}".format(proc.returncode, after == content))
    proc, _ = run_audit(py, [small, "-o", OUT])
    if proc.returncode != 2 or "出力先がフォルダです" not in proc.stderr:
        f.append("-o にフォルダ: rc={}".format(proc.returncode))
    out0 = os.path.join(OUT, "delay0.csv")
    proc, log = run_audit(py, [small, "-o", out0, "--delay", "0"])
    _, _, rows, _ = read_csv(out0)
    if proc.returncode != 0 or len(rows) != 2 or "--delay 0.0 秒は短めです" not in proc.stderr or len(log) != 4:
        f.append("--delay 0: rc={} rows={} req={}".format(proc.returncode, len(rows), len(log)))
    record("引数の攻撃（--limit 0・小数・文字、--delay nan / inf / 1e12、--timeout 0 / inf、URL でもファイルでもない"
           "文字列・スキームなし・ftp:・file:・フォルダ・ホストなし・壊れた IPv6・空、入力＝出力、-o にフォルダ、--delay 0）", f,
           "不正な値はすべて終了コード 2 と日本語の理由（トレースバックなし）、入力と同じ出力先はサイトマップを壊さずに拒否、"
           "--delay 0 は警告付きで正常終了")


def case_big_sitemap(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "big.csv")
    t0 = time.monotonic()
    proc, log = run_audit(py, [b + "/sm/big.xml", "-o", out, "--delay", "0", "--limit", "2", "--ignore-robots"])
    dt = time.monotonic() - t0
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or urls_of(rows) != [b + "/p/big/0", b + "/p/big/1"]:
        f.append("rc={} urls={}".format(proc.returncode, urls_of(rows)))
    if "URL セット 50000 件" not in proc.stderr:
        f.append("5 万件として読んでいない")
    if "URL 50,000 件超 0 件 / 展開後 50MB 超 0 件" not in proc.stderr or "Google の上限（1 ファイル" in proc.stderr:
        f.append("ちょうど 5 万件で上限超えの警告が出た")
    if dt > 20:
        f.append("所要時間 {:.1f} 秒".format(dt))
    record("5 万 URL のサイトマップ（実行全体）", f, "取得・解析・2 件の監査まで {:.2f} 秒（--limit 2）".format(dt))


def case_get_only(py, srv):
    with open(LOG, "r", encoding="utf-8") as fh:
        entries = [json.loads(line) for line in fh if line.strip()]
    methods = Counter(e.get("method", "?") for e in entries)
    f = []
    if set(methods) != {"GET"}:
        f.append("GET 以外のリクエスト: {}".format(dict(methods)))
    record("すべて GET（HEAD を使わない）", f, "このテスト全体のサーバー側の記録 {} 件がすべて GET".format(len(entries)))


def case_no_pycache(py, srv):
    skill = os.path.dirname(os.path.dirname(os.path.abspath(AUDIT)))
    found = []
    for root, dirs, files in os.walk(skill):
        if "__pycache__" in dirs:
            found.append(os.path.join(root, "__pycache__"))
        found.extend(os.path.join(root, x) for x in files if x.endswith(".pyc"))
    record("スキルのフォルダに __pycache__ / .pyc がない", ["残っている: {}".format(found)] if found else [],
           "{} を確認".format(skill))


# ---------------------------------------------------------------------------
# 2026-09-26 追加: CSV インジェクション対策と入れ子のサイトマップインデックス
# ---------------------------------------------------------------------------

def case_sanitize(py, srv):
    b = srv.base
    f = []
    m = load_module()
    # 単体: 5 つの文字列の列すべてと、対象外の列・先頭以外の記号・長さの上限
    row = {"url": "=u", "status": "-1", "redirect_to": "+r", "title": "\tt", "title_len": 2, "desc": "\rd",
           "desc_len": 2, "h1_count": "", "canonical": "@c", "canonical_mismatch": "", "robots_noindex": "",
           "word_count": ""}
    n = m.sanitize_row(row)
    want = {"url": "'=u", "status": "-1", "redirect_to": "'+r", "title": "'\tt", "title_len": 2, "desc": "'\rd",
            "canonical": "'@c"}
    if n != 5 or any(row[k] != v for k, v in want.items()):
        f.append("単体 sanitize_row: n={} row={}".format(n, {k: row[k] for k in want}))
    row = {"url": "https://e.com/", "redirect_to": "", "title": "a=b", "desc": "\u3000=全角空白の後", "canonical": ""}
    if m.sanitize_row(row) != 0 or row["title"] != "a=b":
        f.append("単体: 先頭以外の記号に ' を付けた: {}".format(row))
    cell, changed = m.sanitize_cell("=" + "あ" * 32766)
    if not changed or len(cell) != 32767 or not cell.startswith("'=あ"):
        f.append("単体: 上限ちょうどの値に ' を付けたときの長さ {}".format(len(cell)))

    # 結合: 既定（' を付ける）
    long_title = "=" + "あ" * 40000
    exp_on = [
        (b + "/h/formula-eq", P("'" + '=HYPERLINK("http://evil.example/","クリック")', 41,
                                desc="'=1+1 の説明", desc_len=8)),
        (b + "/h/formula-minus", P("'-50%オフ セール", 10, desc="'+81 から始まる電話番号", desc_len=13)),
        (b + "/h/formula-at", P("'@SUM(A1)", 8, desc="通常の説明", desc_len=5)),
        (b + "/h/formula-mid", P("価格 = 1,000円", 11, desc="a-b の説明", desc_len=7)),
        (b + "/h/formula-long", P(("'" + long_title)[:32767], 40001)),
    ]
    out = os.path.join(OUT, "sanitize_on.csv")
    proc, _ = run_audit(py, [b + "/sm/formula.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    no_traceback(proc, f)
    has_bom, header, rows, _ = read_csv(out)
    if proc.returncode != 0 or not has_bom or header != COLUMNS:
        f.append("既定: rc={} bom={} header={}".format(proc.returncode, has_bom, header))
    compare_rows(rows, exp_on, f, "既定: ")
    for needle in ["CSV インジェクション対策で ' を付けたセル: 6 個", "title が 40001 文字あり"]:
        if needle not in proc.stderr:
            f.append("既定: stderr に {!r} がない".format(needle))

    # 結合: --no-sanitize（元の値のまま）
    exp_off = [
        (b + "/h/formula-eq", P('=HYPERLINK("http://evil.example/","クリック")', 41, desc="=1+1 の説明", desc_len=8)),
        (b + "/h/formula-minus", P("-50%オフ セール", 10, desc="+81 から始まる電話番号", desc_len=13)),
        (b + "/h/formula-at", P("@SUM(A1)", 8, desc="通常の説明", desc_len=5)),
        (b + "/h/formula-mid", P("価格 = 1,000円", 11, desc="a-b の説明", desc_len=7)),
        (b + "/h/formula-long", P(long_title[:32767], 40001)),
    ]
    out = os.path.join(OUT, "sanitize_off.csv")
    proc, _ = run_audit(py, [b + "/sm/formula.xml", "-o", out, "--delay", "0.05", "--ignore-robots", "--no-sanitize"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, exp_off, f, "--no-sanitize: ")
    if "CSV インジェクション対策: 無効（--no-sanitize）" not in proc.stderr or "' を付けたセル" in proc.stderr:
        f.append("--no-sanitize: サマリーの表示が違う: {}".format(proc.stderr[-400:]))
    record("CSV インジェクション対策（url・redirect_to・title・desc・canonical、title_len / desc_len は元の文字数、"
           "Excel の上限、--no-sanitize）", f,
           "単体 3 種、既定で title 4 個・desc 2 個の計 6 個に ' を付けてサマリーに 6 個、先頭以外の記号は変えない、"
           "40001 文字の title は ' を含めて 32767 文字、--no-sanitize では元の値のまま")


def case_nested_index(py, srv):
    b = srv.base
    f = []
    warn = "警告: サイトマップインデックスが別のサイトマップインデックスを参照しています（入れ子）"
    summary = "入れ子のサイトマップインデックス（Google は非対応。Search Console でエラー）: {} 件"
    out = os.path.join(OUT, "nested.csv")
    proc, log = run_audit(py, [b + "/sm/idx-top.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or urls_of(rows) != [b + "/p/english", b + "/p/no-title", b + "/p/two-h1"]:
        f.append("入れ子 2 段: rc={} urls={}".format(proc.returncode, urls_of(rows)))
    for needle in [warn + ": " + b + "/sm/idx-mid.xml（参照元: " + b + "/sm/idx-top.xml）",
                   warn + ": " + b + "/sm/idx-mid2.xml（参照元: " + b + "/sm/idx-mid.xml）",
                   "Google は入れ子のサイトマップインデックスをサポートしません", summary.format(2)]:
        if needle not in proc.stderr:
            f.append("入れ子 2 段: stderr に {!r} がない".format(needle))
    if proc.stderr.count(warn) != 2:
        f.append("入れ子 2 段: 警告が {} 回（期待 2）".format(proc.stderr.count(warn)))
    fetched = [e["path"] for e in log if e["path"].startswith("/sm/idx-")]
    if fetched != ["/sm/idx-top.xml", "/sm/idx-mid.xml", "/sm/idx-leaf.xml", "/sm/idx-mid2.xml",
                   "/sm/idx-leaf2.xml", "/sm/idx-urls.xml"]:
        f.append("入れ子 2 段: たどった順 {}".format(fetched))

    out = os.path.join(OUT, "nested_depth1.csv")
    proc, log = run_audit(py, [b + "/sm/idx-top.xml", "-o", out, "--delay", "0.05", "--ignore-robots",
                               "--max-depth", "1"])
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or urls_of(rows) != [b + "/p/two-h1"] or summary.format(1) not in proc.stderr \
            or "--max-depth 1" not in proc.stderr:
        f.append("--max-depth 1: rc={} urls={} stderr={}".format(proc.returncode, urls_of(rows), proc.stderr[-400:]))

    out = os.path.join(OUT, "nested_flat.csv")
    proc, _ = run_audit(py, [b + "/sm/idx-flat.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or len(rows) != 2 or warn in proc.stderr or summary.format(0) not in proc.stderr:
        f.append("入れ子なしのインデックス: rc={} rows={} stderr={}".format(proc.returncode, len(rows),
                                                                  proc.stderr[-400:]))
    record("入れ子のサイトマップインデックス（たどったうえで警告、サマリーに件数）", f,
           "2 段の入れ子で警告 2 回（参照元つき）・サマリー 2 件・6 本を深さ優先で取得、--max-depth 1 では 1 件、"
           "入れ子のない通常のインデックスは警告なし・0 件")


# ---------------------------------------------------------------------------
# 2026-09-26 追加 2: 内部アドレスの拒否・別のホスト・429 / 503・サイトマップの大きさ
# ---------------------------------------------------------------------------

def run_main_inprocess(m, args):
    """audit.main() を同じプロセスで実行する（名前解決の判定をモックするため）。(終了コード, 標準エラー)。"""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = m.main(args)
    return rc, buf.getvalue()


def case_private_unit(py, srv):
    import socket as sk
    m = load_module()
    f = []
    internal = ["127.0.0.1", "127.8.9.10", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0",
                "224.0.0.1", "240.0.0.1", "255.255.255.255", "100.64.0.1", "::1", "::", "fe80::1", "fe80::1%en0",
                "fc00::1", "fd12:3456::1", "ff02::1", "fec0::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
                "::ffff:169.254.169.254", "64:ff9b::a00:1", "not-an-ip"]
    public = ["8.8.8.8", "1.1.1.1", "93.184.215.14", "2001:4860:4860::8888", "::ffff:8.8.8.8", "64:ff9b::808:808"]
    for a in internal:
        if m.internal_address(a) is not True:
            f.append("内部とみなすはず: {}".format(a))
    for a in public:
        if m.internal_address(a) is not False:
            f.append("外部とみなすはず: {}".format(a))
    # 名前解決のモック（外部に問い合わせない）
    table = {"internal.test": ["10.1.2.3"], "public.test": ["93.184.215.14"],
             "mixed.test": ["93.184.215.14", "fd00::1"], "mapped.test": ["::ffff:192.168.0.1"],
             "metadata.test": ["169.254.169.254"]}
    calls = []
    original = sk.getaddrinfo

    def fake(host, port, family=0, type=0, proto=0, flags=0):
        calls.append(host)
        if host not in table:
            raise sk.gaierror(8, "nodename nor servname provided, or not known")
        return [(sk.AF_INET6 if ":" in a else sk.AF_INET, sk.SOCK_STREAM, 6, "", (a, port or 0)) for a in table[host]]

    sk.getaddrinfo = fake
    try:
        guard = m.AddressGuard()
        for url, exp in [("http://internal.test/a", "10.1.2.3"), ("https://public.test/", None),
                         ("http://mixed.test/", "fd00::1"), ("http://mapped.test/", "::ffff:192.168.0.1"),
                         ("http://metadata.test/latest/meta-data/", "169.254.169.254"),
                         ("http://unknown.test/", None), ("http://INTERNAL.test:8080/b", "10.1.2.3")]:
            got = guard.internal(url)
            if got != exp:
                f.append("AddressGuard.internal({}) = {!r}（期待 {!r}）".format(url, got, exp))
        if calls.count("internal.test") != 1:
            f.append("同じホストの名前解決が {} 回（1 回のはず）".format(calls.count("internal.test")))
        m.set_connection_guard(True, frozenset())
        try:
            m._guarded_create_connection(("internal.test", 80), 1.0)
            f.append("接続時の判定で internal.test を止めなかった")
        except m.PrivateAddressBlocked as exc:
            if exc.address != "10.1.2.3":
                f.append("接続時の判定のアドレス: {}".format(exc.address))
    finally:
        sk.getaddrinfo = original
        m.set_connection_guard(False)
    record("単体: 内部アドレスの判定（IPv4 / IPv6・IPv4 射影・NAT64・共有アドレス）と名前解決のモック", f,
           "内部 {} 種・外部 {} 種を判定、モックした名前解決で内部 / 外部 / 混在 / 射影 / メタデータ / 解決不可、"
           "ホストごとに 1 回だけ解決、接続時の判定".format(len(internal), len(public)))


def case_private_default(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "private_should_not_exist.csv")
    for root in [b + "/sitemaps/small.xml", "http://localhost:{}/sitemaps/small.xml".format(srv.port),
                 "http://[::1]:{}/sitemaps/small.xml".format(srv.port),
                 "http://[::ffff:127.0.0.1]:{}/sitemaps/small.xml".format(srv.port)]:
        if os.path.exists(out):
            os.remove(out)
        proc, log = run_audit(py, [root, "-o", out, "--delay", "0.05"], allow_private=False)
        no_traceback(proc, f, root + ": ")
        if proc.returncode != 2 or "内部アドレス（" not in proc.stderr or "--allow-private を付けてください" not in proc.stderr \
                or "最初のサイトマップを取得・解析できず" not in proc.stderr:
            f.append("{}: rc={} stderr={}".format(root, proc.returncode, proc.stderr[-400:]))
        if log:
            f.append("{}: サーバーにリクエストが届いた: {}".format(root, [e["path"] for e in log]))
        if os.path.exists(out):
            f.append("{}: 終了コード 2 なのに CSV が作られた".format(root))

    # ローカルファイルのサイトマップ: ページは BLOCKED:private-address（robots.txt も取得しない）
    path = os.path.join(OUT, "private_pages.xml")
    pages = [b + "/p/english", "http://localhost:{}/p/two-h1".format(srv.port),
             "http://[::1]:{}/p/no-title".format(srv.port), "http://[::ffff:127.0.0.1]:{}/p/ja-normal".format(srv.port)]
    with open(path, "wb") as fh:
        fh.write(_sitemap_xml(pages))
    out = os.path.join(OUT, "private_pages.csv")
    proc, log = run_audit(py, [path, "-o", out, "--delay", "0.05", "--allow-other-hosts"], allow_private=False)
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [(u, E("BLOCKED:private-address")) for u in pages], f, "ページ: ")
    if proc.returncode != 0 or log:
        f.append("ページ: rc={} リクエスト={}".format(proc.returncode, [e["path"] for e in log]))
    for needle in ["ホストが内部アドレス（127.0.0.1）に解決されるため取得しませんでした（--allow-private で許可）",
                   "内部アドレス（::1）", "内部アドレス（::ffff:127.0.0.1）",
                   "内部アドレスのため取得しなかった（BLOCKED:private-address）: ページ 4 件 / サイトマップ 0 件",
                   "  BLOCKED:private-address: 4", "robots.txt で除外: 0 件"]:
        if needle not in proc.stderr:
            f.append("ページ: stderr に {!r} がない".format(needle))
    # 既定（別ホストも除外）: 最初の有効な loc のホスト 127.0.0.1 が基準。別ホストの判定が先
    out = os.path.join(OUT, "private_pages_scope.csv")
    proc, log = run_audit(py, [path, "-o", out, "--delay", "0.05"], allow_private=False)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [(pages[0], E("BLOCKED:private-address"))] + [(u, E("SKIPPED:other-host")) for u in pages[1:]],
                 f, "ページ（別ホストも除外）: ")
    if proc.returncode != 0 or log:
        f.append("ページ（別ホストも除外）: rc={} リクエスト={}".format(proc.returncode, len(log)))
    record("内部アドレスの拒否（既定）: 最初のサイトマップは終了コード 2、ページは BLOCKED:private-address", f,
           "127.0.0.1 / localhost / [::1] / [::ffff:127.0.0.1] のサイトマップは日本語の理由付きで 2・CSV なし・"
           "サーバーへのリクエスト 0 回。ローカルのサイトマップの 4 ページは BLOCKED（robots.txt も取得しない）")


def case_private_redirect(py, srv):
    """127.0.0.1 だけを外部のアドレスとみなすモックで、リダイレクト先と接続時の判定を確かめる。"""
    import socket as sk
    m = load_module()
    b = srv.base
    port = srv.port
    f = []
    original = m.internal_address
    m.internal_address = lambda a: False if a == "127.0.0.1" else original(a)
    try:
        out = os.path.join(OUT, "private_redirect.csv")
        start = log_size()
        rc, err = run_main_inprocess(m, [b + "/sm/to-internal.xml", "-o", out, "--delay", "0.05",
                                         "--ignore-robots", "--timeout", "2"])
        log = log_since(start)
        _, _, rows, _ = read_csv(out)
        localhost_other = [a for a in m.resolve_addresses("localhost") if a != "127.0.0.1"]
        loc_exp = (E("BLOCKED:private-address", redirect_to="http://localhost:{}/p/english".format(port))
                   if localhost_other else
                   P("English Page", 12, wc=14, desc="An English description.", desc_len=23, status="301>200",
                     redirect_to="http://localhost:{}/p/english".format(port)))
        compare_rows(rows, [
            (b + "/r/to-localhost", loc_exp),
            (b + "/r/to-ipv6-loopback", E("BLOCKED:private-address", redirect_to="http://[::1]:{}/p/english".format(port))),
            (b + "/r/to-mapped", E("BLOCKED:private-address",
                                   redirect_to="http://[::ffff:127.0.0.1]:{}/p/english".format(port))),
            (b + "/p/english", P("English Page", 12, wc=14, desc="An English description.", desc_len=23)),
        ], f, "リダイレクト: ")
        if rc != 0:
            f.append("リダイレクト: rc={} {}".format(rc, err[-400:]))
        if "リダイレクト先が内部アドレス（::1）に解決されるため取得しませんでした" not in err:
            f.append("リダイレクト: stderr に理由がない: {}".format(err[-600:]))
        bad = [e for e in log if not e["host"].startswith("127.0.0.1")]
        if bad and localhost_other:
            f.append("リダイレクト: 内部アドレスのホストにリクエストが届いた: {}".format(bad))
        # 最初のサイトマップのリダイレクト先が内部アドレス → 終了コード 2
        out2 = os.path.join(OUT, "private_redirect_root.csv")
        if os.path.exists(out2):
            os.remove(out2)
        rc, err = run_main_inprocess(m, [b + "/sm/redirect-to-v6.xml", "-o", out2, "--delay", "0.05"])
        if rc != 2 or "リダイレクト先 http://[::1]:{}/sitemaps/small.xml が内部アドレス（::1）".format(port) not in err \
                or os.path.exists(out2):
            f.append("サイトマップのリダイレクト: rc={} {}".format(rc, err[-400:]))
        # 子サイトマップが内部アドレス → 取得せず、その中のページは CSV に出ない（サマリーのサイトマップの件数）
        out3 = os.path.join(OUT, "private_child.csv")
        start = log_size()
        rc, err = run_main_inprocess(m, [b + "/sm/idx-internal-child.xml", "-o", out3, "--delay", "0.05",
                                         "--ignore-robots", "--allow-other-hosts"])
        _, _, rows, _ = read_csv(out3)
        if rc != 0 or urls_of(rows) != [b + "/p/english"] or \
                "サイトマップを取得しません。ホストが内部アドレス（::1）に解決されます" not in err or \
                "内部アドレスのため取得しなかった（BLOCKED:private-address）: ページ 0 件 / サイトマップ 1 件" not in err or \
                any(e["path"] == "/sm/idx-leaf2.xml" for e in log_since(start)):
            f.append("子サイトマップ: rc={} urls={} {}".format(rc, urls_of(rows), err[-400:]))
        # 接続時の判定（取得前の判定のあとで DNS の答えが変わった想定）: リクエストを出さずに止める
        m.internal_address = original
        guard = m.AddressGuard()
        guard._cache["127.0.0.1"] = None  # 取得前の判定では外部のアドレスだったことにする
        m.set_connection_guard(True, frozenset())
        fetcher = m.Fetcher(0.0, 2.0, DEFAULT_UA, guard)
        start = log_size()
        res = fetcher.fetch(b + "/p/english", lambda r: True, 1000)
        if res.status_text() != "BLOCKED:private-address" or res.private_address != "127.0.0.1" \
                or log_since(start) or fetcher.request_count != 0:
            f.append("接続時の判定: status={} address={} requests={}".format(
                res.status_text(), res.private_address, fetcher.request_count))
        # プロキシのホストへの接続は止めない
        m.set_connection_guard(True, frozenset(["127.0.0.1"]))
        res = m.Fetcher(0.0, 2.0, DEFAULT_UA, guard).fetch(b + "/p/english", lambda r: True, 1000)
        if res.status_text() != "200":
            f.append("プロキシのホストの除外: status={}".format(res.status_text()))
        # 同じプロセスで既定の main() のあとに --allow-private の main() を呼んでも、接続時の判定が残らない
        m.set_connection_guard(True, frozenset())
        out4 = os.path.join(OUT, "private_then_allow.csv")
        rc, err = run_main_inprocess(m, [b + "/sitemaps/small.xml", "-o", out4, "--delay", "0.05", "--ignore-robots",
                                         "--limit", "1", "--allow-private"])
        _, _, rows, _ = read_csv(out4)
        if rc != 0 or [r["status"] for r in rows] != ["200"]:
            f.append("--allow-private で接続時の判定が外れない: rc={} status={}".format(rc, [r["status"] for r in rows]))
    finally:
        m.internal_address = original
        m.set_connection_guard(False)
    record("内部アドレスの拒否: リダイレクト先・サイトマップのリダイレクト・接続時の再判定（DNS リバインディング）", f,
           "127.0.0.1 だけを外部とみなすモックで、[::1] と [::ffff:127.0.0.1] へのリダイレクトは BLOCKED（redirect_to に"
           "移動先）、localhost は {}、サイトマップのリダイレクト先が [::1] なら終了コード 2、[::1] の子サイトマップは"
           "取得せずサマリーに 1 件、取得前の判定を通っても接続の直前に止めてリクエスト 0 回、プロキシのホストは対象外、"
           "同じプロセスで続けて --allow-private の main() を呼ぶと接続時の判定が外れる".format(
               "::1 を含むので BLOCKED" if localhost_other else "127.0.0.1 だけなので取得"))


def case_other_host(py, srv):
    b = srv.base
    loc = "http://localhost:{}".format(srv.port)
    f = []
    english = P("English Page", 12, wc=14, desc="An English description.", desc_len=23)
    out = os.path.join(OUT, "other_host.csv")
    proc, log = run_audit(py, [b + "/sm/mixed-hosts.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [(b + "/p/english", english), (loc + "/p/two-h1", E("SKIPPED:other-host")),
                        (b + "/p/no-title", P("", 0, desc="説明文あり", desc_len=5)),
                        (loc + "/p/no-desc", E("SKIPPED:other-host"))], f, "既定: ")
    if proc.returncode != 0 or any(e["host"].startswith("localhost") for e in log):
        f.append("既定: rc={} localhost へのリクエスト {}".format(proc.returncode,
                                                         [e["path"] for e in log if e["host"].startswith("localhost")]))
    for needle in ["警告: サイトマップのホスト（127.0.0.1）と別のホストの URL が 2 件あります",
                   "サイトマップと別のホストのため取得しなかった（SKIPPED:other-host）: ページ 2 件 / 子サイトマップ 0 件"]:
        if needle not in proc.stderr:
            f.append("既定: stderr に {!r} がない".format(needle))
    out = os.path.join(OUT, "other_host_allow.csv")
    proc, log = run_audit(py, [b + "/sm/mixed-hosts.xml", "-o", out, "--delay", "0.05", "--ignore-robots",
                               "--allow-other-hosts"])
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or [r["status"] for r in rows] != ["200"] * 4 or \
            sum(1 for e in log if e["host"].startswith("localhost")) != 2 or \
            "別のホストの URL の除外: 無効（--allow-other-hosts）" not in proc.stderr:
        f.append("--allow-other-hosts: rc={} status={}".format(proc.returncode, [r["status"] for r in rows]))
    # 子サイトマップ
    out = os.path.join(OUT, "other_host_index.csv")
    proc, log = run_audit(py, [b + "/sm/mixed-index.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or urls_of(rows) != [b + "/p/english"] or "/sm/idx-leaf2.xml" in [e["path"] for e in log] \
            or "サイトマップと別のホストの子サイトマップは取得しません（--allow-other-hosts で取得）: " + loc + \
            "/sm/idx-leaf2.xml" not in proc.stderr or "子サイトマップ 1 件" not in proc.stderr:
        f.append("子サイトマップ: rc={} urls={} stderr={}".format(proc.returncode, urls_of(rows), proc.stderr[-400:]))
    proc, _ = run_audit(py, [b + "/sm/mixed-index.xml", "-o", out, "--delay", "0.05", "--ignore-robots",
                             "--allow-other-hosts"])
    _, _, rows, _ = read_csv(out)
    if urls_of(rows) != [b + "/p/english", b + "/p/no-title"]:
        f.append("子サイトマップ（--allow-other-hosts）: {}".format(urls_of(rows)))
    # ルートのサイトマップのリダイレクト後のホストも基準に含む
    out = os.path.join(OUT, "other_host_redirect.csv")
    proc, _ = run_audit(py, [b + "/sm/redirect-to-localhost.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or [r["status"] for r in rows] != ["200"] * 4 or \
            "基準のホスト: 127.0.0.1・localhost" not in proc.stderr:
        f.append("リダイレクト後のホスト: rc={} status={}".format(proc.returncode, [r["status"] for r in rows]))
    # ローカルファイル: 最初の有効な loc（相対 URL はスキップ）のホストが基準
    path = os.path.join(OUT, "other_host_local.xml")
    with open(path, "wb") as fh:
        fh.write(_sitemap_xml(["/relative", loc + "/p/english", b + "/p/two-h1"]))
    out = os.path.join(OUT, "other_host_local.csv")
    proc, log = run_audit(py, [path, "-o", out, "--delay", "0.05", "--ignore-robots"])
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [(loc + "/p/english", english), (b + "/p/two-h1", E("SKIPPED:other-host"))], f, "ローカル: ")
    if "基準のホスト: localhost" not in proc.stderr or any(e["host"].startswith("127.0.0.1") for e in log):
        f.append("ローカル: stderr={}".format(proc.stderr[-400:]))
    # リダイレクトで別のホストに移るのは許可（http_attack の /r/cross-host と同じ）
    out = os.path.join(OUT, "other_host_cross.csv")
    proc, _ = run_audit(py, [b + "/sm/http-attack.xml", "-o", out, "--delay", "0.05", "--ignore-robots", "--limit", "1"])
    _, _, rows, _ = read_csv(out)
    if [r["status"] for r in rows] != ["301>200"]:
        f.append("別のホストへのリダイレクト: {}".format([r["status"] for r in rows]))
    record("別のホストの URL（既定で SKIPPED:other-host、--allow-other-hosts で取得）", f,
           "ページ 2 件と子サイトマップ 1 件を取得せず（localhost へのリクエスト 0 回）、警告とサマリーに件数、"
           "--allow-other-hosts で全件取得、ルートのリダイレクト後のホストを基準に追加、ローカルファイルは最初の"
           "有効な loc のホスト、リダイレクトで別のホストに移るのは許可")


def case_retry_after(py, srv):
    b = srv.base
    f = []
    m = load_module()
    now = time.time()
    import calendar
    import contextlib
    import email.utils as eu
    import io
    for value, exp in [("2", 2.0), (" 10 ", 10.0), ("0", 0.0), ("soon", None), ("-1", None), ("1.5", None), ("", None),
                       (None, None), (eu.formatdate(now - 60, usegmt=True), 0.0),
                       ("Sun, 06 Nov 2044 08:49:37", calendar.timegm((2044, 11, 6, 8, 49, 37)) - now)]:
        got = m.retry_after_seconds(value, now)
        if (got is None) != (exp is None) or (got is not None and abs(got - exp) > 0.001):
            f.append("retry_after_seconds({!r}) = {!r}（期待 {!r}）".format(value, got, exp))
    got = m.retry_after_seconds(eu.formatdate(now + 30, usegmt=True), now)
    if got is None or not (29.0 < got <= 30.0):
        f.append("HTTP 日付 +30 秒: {}".format(got))

    # サーバー側の到着時刻: 秒数（2 秒）と HTTP 日付（2〜3 秒）と、解釈できない値（間隔を延ばす）
    out = os.path.join(OUT, "retry_after.csv")
    proc, log = run_audit(py, [b + "/sm/retry-after.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or [r["status"] for r in rows] != ["503", "200", "429", "200", "503", "200"]:
        f.append("rc={} status={}".format(proc.returncode, [r["status"] for r in rows]))
    t = {e["path"]: e["t"] for e in log}
    g1 = t["/p/english"] - t["/t/ra-secs"]
    g2 = t["/p/two-h1"] - t["/t/ra-date"]
    g3 = t["/p/no-title"] - t["/t/ra-bad"]
    if not (2.0 - 0.01 <= g1 < 2.8):
        f.append("Retry-After: 2 の間隔 {:.3f} 秒".format(g1))
    if not (2.0 - 0.01 <= g2 < 3.8):
        f.append("Retry-After（HTTP 日付 +3 秒）の間隔 {:.3f} 秒".format(g2))
    if not (0.1 - 0.005 <= g3 < 0.6):
        f.append("解釈できない Retry-After の間隔 {:.3f} 秒（--delay の 2 倍 = 0.1 のはず）".format(g3))
    g_after = t["/t/ra-date"] - t["/p/english"]
    if g_after > 0.5:
        f.append("200 のあとも間隔が戻っていない: {:.3f} 秒".format(g_after))
    for needle in ["ステータス 503 のため、次のリクエストまで 2.0 秒空けます（Retry-After: 2）",
                   "429 / 503 の応答: 3 回（Retry-After に従って待った: 2 回 / 間隔を延ばした: 1 回）"]:
        if needle not in proc.stderr:
            f.append("stderr に {!r} がない".format(needle))

    # 上限（120 秒・60 秒）は待たずに、要求した待ち時間を記録して確かめる
    fetcher = m.Fetcher(0.05, 2.0, DEFAULT_UA)
    sleeps = []
    fetcher._sleep = sleeps.append
    body = lambda r: False
    quiet = io.StringIO()
    with contextlib.redirect_stderr(quiet):
        for path in ["/t/ra-big", "/p/english", "/t/ra-far-date", "/p/english"]:
            fetcher.fetch(b + path, body, 1000)
    capped = [x for x in sleeps if x > 1]
    if len(capped) != 2 or any(not (119.5 < x <= 120.0) for x in capped):
        f.append("Retry-After の上限 120 秒: {}".format(sleeps))
    fetcher = m.Fetcher(10.0, 2.0, DEFAULT_UA)
    sleeps = []
    fetcher._sleep = sleeps.append
    with contextlib.redirect_stderr(quiet):
        for path in ["/t/429/c1", "/t/429/c2", "/t/503/c3", "/t/429/c4", "/p/english", "/p/two-h1"]:
            fetcher.fetch(b + path, body, 1000)
    if "（Retry-After: 100000）" not in quiet.getvalue() or "120.0 秒空けます" not in quiet.getvalue():
        f.append("上限で待つときの表示: {}".format(quiet.getvalue()[:300]))
    exp = [20.0, 40.0, 60.0, 60.0, 10.0]
    if len(sleeps) != len(exp) or any(not (e - 0.5 < x <= e) for x, e in zip(sleeps, exp)):
        f.append("間隔の延長（--delay 10 → 20, 40, 60, 60（上限）, 200 のあと 10）: {}".format(
            ["{:.2f}".format(x) for x in sleeps]))
    record("429 / 503 と Retry-After（秒数・HTTP 日付・上限 120 秒、なければ 2 倍ずつ・上限 60 秒）", f,
           "サーバー側の到着間隔: Retry-After: 2 で {:.2f} 秒、HTTP 日付（+3 秒）で {:.2f} 秒、解釈できない値は "
           "{:.2f} 秒（--delay 0.05 の 2 倍）。Retry-After: 100000 と 1 日後の日付は 120 秒、--delay 10 で 20・40・"
           "60・60 秒、200 のあとは 10 秒に戻る（待ち時間の記録で確認）".format(g1, g2, g3))


def case_throttle_abort(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "throttle_abort.csv")
    proc, log = run_audit(py, [b + "/sm/throttle-abort.xml", "-o", out, "--delay", "0.1", "--ignore-robots"])
    no_traceback(proc, f)
    _, header, rows, raw = read_csv(out)
    exp = [(b + "/p/english", P("English Page", 12, wc=14, desc="An English description.", desc_len=23))] + \
          [(b + p, E(p.split("/")[2])) for p in ["/t/429/1", "/t/503/2", "/t/429/3", "/t/503/4", "/t/429/5"]]
    compare_rows(rows, exp, f)
    if proc.returncode != 3:
        f.append("終了コード {}（期待 3）".format(proc.returncode))
    paths = [e["path"] for e in log]
    if "/p/two-h1" in paths or "/p/no-title" in paths:
        f.append("中断後にリクエストした: {}".format(paths))
    t = {e["path"]: e["t"] for e in log}
    seq = ["/t/429/1", "/t/503/2", "/t/429/3", "/t/503/4", "/t/429/5"]
    g = [t[b2] - t[a2] for a2, b2 in zip(seq, seq[1:])]
    for got, want in zip(g, [0.2, 0.4, 0.8, 1.6]):
        if not (want - 0.01 <= got < want + 0.4):
            f.append("間隔 {:.3f} 秒（期待 {:.1f} 秒）".format(got, want))
    for needle in ["429 / 503 が 5 回続きました", "書き込み済みの 6 行は", "未取得 2 件",
                   "処理した URL: 6 / 8 件（429 / 503 が 5 回続いたため中断。未取得 2 件）",
                   # 5 回目のあとは中断するので待たない（実際に待ったのは 4 回）
                   "429 / 503 の応答: 5 回（Retry-After に従って待った: 0 回 / 間隔を延ばした: 4 回）"]:
        if needle not in proc.stderr:
            f.append("stderr に {!r} がない".format(needle))
    if header != COLUMNS or any(len(r) != 12 for r in raw):
        f.append("CSV の形が崩れている")
    # 200 をはさめば連続は途切れる（最大 4 回なので中断しない）
    out = os.path.join(OUT, "throttle_reset.csv")
    proc, log = run_audit(py, [b + "/sm/throttle-reset.xml", "-o", out, "--delay", "0.05", "--ignore-robots"])
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or len(rows) != 8 or rows[-1]["status"] != "200":
        f.append("連続の途切れ: rc={} rows={}".format(proc.returncode, [r["status"] for r in rows]))
    t = {e["path"]: e["t"] for e in log}
    if not (0.8 - 0.01 <= t["/p/two-h1"] - t["/t/429/f"] < 1.2) or not (t["/t/429/c"] - t["/p/english"] < 0.3):
        f.append("連続の途切れ: 間隔が期待と違う（f→two-h1 {:.3f}、english→c {:.3f}）".format(
            t["/p/two-h1"] - t["/t/429/f"], t["/t/429/c"] - t["/p/english"]))
    # サイトマップの収集中に 5 回続いた → 終了コード 3、CSV なし
    out = os.path.join(OUT, "throttle_collect.csv")
    if os.path.exists(out):
        os.remove(out)
    proc, log = run_audit(py, [b + "/sm/throttle-index.xml", "-o", out, "--delay", "0.05"])
    no_traceback(proc, f, "収集中: ")
    if proc.returncode != 3 or os.path.exists(out) or "サイトマップの収集中" not in proc.stderr or \
            "/sitemaps/small.xml" in [e["path"] for e in log]:
        f.append("収集中: rc={} csv={} stderr={}".format(proc.returncode, os.path.exists(out), proc.stderr[-400:]))
    record("429 / 503 が 5 回続いたら中断（終了コード 3、書き込み済みの行は残る）", f,
           "8 URL 中 6 行を書いて中断・未取得 2 件をサマリーに出力、中断後のリクエスト 0 回、到着間隔 "
           "{}（--delay 0.1 の 2・4・8・16 倍）、200 をはさむと連続が途切れて正常終了、収集中の中断は CSV なしで 3".format(
               " / ".join("{:.2f}s".format(x) for x in g)))


def case_sitemap_limits(py, srv):
    b = srv.base
    f = []
    out = os.path.join(OUT, "over50k.csv")
    proc, _ = run_audit(py, [b + "/sm/over50k.xml", "-o", out, "--delay", "0", "--limit", "1", "--ignore-robots"])
    no_traceback(proc, f)
    for needle in ["警告: URL が 50,001 件あり、Google の上限（1 ファイル 50,000 件）を超えています",
                   "URL 50,000 件超 1 件 / 展開後 50MB 超 0 件"]:
        if needle not in proc.stderr:
            f.append("50,001 件: stderr に {!r} がない".format(needle))
    if proc.returncode != 0:
        f.append("50,001 件: rc={}".format(proc.returncode))
    if "50,000 件以下のファイルに分け、サイトマップインデックスにまとめてください" not in proc.stderr:
        f.append("50,001 件: URL セットの直し方がない")
    # サイトマップインデックスの loc が 50,001 件: 直し方はインデックスを分ける（入れ子にしない）
    out = os.path.join(OUT, "over50k_index.csv")
    proc, log = run_audit(py, [b + "/sm/over50k-index.xml", "-o", out, "--delay", "0", "--limit", "1",
                               "--ignore-robots"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    for needle in ["警告: URL が 50,001 件あり、Google の上限（1 ファイル 50,000 件）を超えています。複数のサイトマップ"
                   "インデックスに分けてください（インデックスの入れ子は Google が非対応）",
                   "URL 50,000 件超 1 件 / 展開後 50MB 超 0 件"]:
        if needle not in proc.stderr:
            f.append("インデックス 50,001 件: stderr に {!r} がない".format(needle))
    if proc.returncode != 0 or urls_of(rows) != [b + "/p/english"] or \
            any(e["path"].startswith("/sm/none/") for e in log):
        f.append("インデックス 50,001 件: rc={} urls={}".format(proc.returncode, urls_of(rows)))
    out = os.path.join(OUT, "over50mb.csv")
    t0 = time.monotonic()
    proc, _ = run_audit(py, [b + "/sm/over50mb.xml.gz", "-o", out, "--delay", "0", "--limit", "1", "--ignore-robots"],
                        timeout=300)
    dt = time.monotonic() - t0
    no_traceback(proc, f)
    import re as _re
    match = _re.search(r"展開後の大きさが ([0-9,]+) バイトあり、Google の上限（展開後 50MB = 52,428,800 バイト）", proc.stderr)
    size = int(match.group(1).replace(",", "")) if match else 0
    if not (52428800 < size < 100 * 1024 * 1024):
        f.append("50MB 超: 警告がないか大きさが違う: {}".format(proc.stderr[-600:]))
    if "URL 50,000 件超 0 件 / 展開後 50MB 超 1 件" not in proc.stderr or "URL セット 40000 件" not in proc.stderr:
        f.append("50MB 超: サマリーか件数が違う")
    _, _, rows, _ = read_csv(out)
    if proc.returncode != 0 or len(rows) != 1:
        f.append("50MB 超: rc={} rows={}".format(proc.returncode, len(rows)))
    record("サイトマップの大きさ（50,000 URL 超・展開後 50MB 超の警告とサマリー）", f,
           "50,001 件で件数の警告（URL セットとサイトマップインデックスで直し方を分ける）、40,000 件・展開後 {:,} バイトの "
           ".xml.gz で大きさの警告（{:.1f} 秒）、ちょうど 5 万件は警告なし（big_sitemap）".format(size, dt))


# ---------------------------------------------------------------------------
# 2026-09-26 追加 3: URL の認証情報（userinfo）と ~/.netrc
# ---------------------------------------------------------------------------

STATUS_CRED = "SKIPPED:credentials-in-url"
NETRC_CONTROL = "/p/english?netrc-control"  # 対照の素の requests が送るリクエスト（Authorization を付けてよい唯一のもの）


def leaked(secrets, *texts):
    """secrets のうち、texts のどれかに含まれているもの。"""
    return [s for s in secrets if any(s in (t or "") for t in texts)]


def file_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return fh.read()


def auth_sent(entries):
    """Authorization ヘッダー付きで届いたリクエスト（パス, 値）。"""
    return [(e["path"], e.get("auth")) for e in entries if e.get("auth")]


def case_cred_unit(py, srv):
    m = load_module()
    import requests as rq
    f = []
    n = 0
    for url, has, masked in [
        ("http://u:p@h/a", True, "http://***@h/a"), ("http://user@h/", True, "http://***@h/"),
        ("http://@h/", True, "http://***@h/"), ("HTTPS://U:P@H:8080/a?b=c@d#e@f", True, "HTTPS://***@H:8080/a?b=c@d#e@f"),
        ("https://a@b@h/x", True, "https://***@h/x"), ("//u:p@h/x", True, "//***@h/x"),
        ("ftp://u:p@h/x", True, "ftp://***@h/x"), ("https://u:p@[::1/x", True, "https://***@[::1/x"),
        ("http://u%40x:p%3Aq@h/", True, "http://***@h/"),
        ("https://h/a@b", False, "https://h/a@b"), ("https://h/?q=a@b", False, "https://h/?q=a@b"),
        ("https://h#x@y", False, "https://h#x@y"), ("https://h/a//b@c", False, "https://h/a//b@c"),
        ("mailto:a@b", False, "mailto:a@b"), ("", False, ""),
    ]:
        n += 1
        if m.has_userinfo(url) is not has:
            f.append("has_userinfo({!r}) = {}".format(url, m.has_userinfo(url)))
        if m.mask_userinfo(url) != masked:
            f.append("mask_userinfo({!r}) = {!r}（期待 {!r}）".format(url, m.mask_userinfo(url), masked))
    text = m.mask_userinfo_text("元 http://u:p@h/a と https://h/a//b@c、https://h/?n=https://q:r@z/ と mailto:x@y")
    n += 1
    if text != "元 http://***@h/a と https://h/a//b@c、https://h/?n=https://***@z/ と mailto:x@y":
        f.append("mask_userinfo_text: {!r}".format(text))
    row = dict.fromkeys(COLUMNS, "")
    row.update({"url": "http://a:b@h/x", "redirect_to": "https://c@h/y", "canonical": "https://d:e@h/z", "title": "t@x"})
    m.mask_row_userinfo(row)
    n += 1
    if [row["url"], row["redirect_to"], row["canonical"], row["title"]] != \
            ["http://***@h/x", "https://***@h/y", "https://***@h/z", "t@x"]:
        f.append("mask_row_userinfo: {}".format(row))
    # Session: trust_env は True のまま、Session.auth で .netrc と URL の userinfo からの Basic 認証を止める
    fetcher = m.Fetcher(0.0, 2.0, DEFAULT_UA)
    prepared = fetcher.session.prepare_request(rq.Request("GET", "http://u:p@127.0.0.1/"))
    n += 1
    if fetcher.session.trust_env is not True or fetcher.session.auth is None or "Authorization" in prepared.headers:
        f.append("Session: trust_env={} auth={} Authorization={}".format(
            fetcher.session.trust_env, fetcher.session.auth, prepared.headers.get("Authorization")))
    # Fetcher に userinfo 付きの URL を直接渡してもリクエストを出さない
    start = log_size()
    url = "http://u:p@127.0.0.1:{}/p/english".format(srv.port)
    res = fetcher.fetch(url, lambda r: True, 1000)
    n += 1
    if res.status_text() != STATUS_CRED or res.credentials_url != "http://***@127.0.0.1:{}/p/english".format(srv.port) \
            or fetcher.request_count != 0 or log_since(start):
        f.append("Fetcher.fetch: status={} url={} requests={}".format(
            res.status_text(), res.credentials_url, fetcher.request_count))
    record("単体: userinfo の判定と伏せ字・Session の認証（trust_env は True、Session.auth で .netrc を止める）", f,
           "{} 項目（user:pass@・user@・空の @・%XX・スキーム省略・壊れた IPv6、パスやクエリの @ は対象外、文中の URL、"
           "CSV の URL 列、prepare_request で Authorization なし、Fetcher に直接渡してもリクエスト 0 回）".format(n))


def case_cred_help(py, srv):
    f = []
    proc = subprocess.run([py, AUDIT, "--help"], capture_output=True, text=True, env=dict(os.environ, COLUMNS="200"))
    for needle in ["SKIPPED:credentials-in-url", "認証情報（Authorization ヘッダー）は送らない",
                   "https://***@example.jp/sitemap.xml", "~/.netrc（NETRC）の認証情報も使わない",
                   "REQUESTS_CA_BUNDLE はそのまま使う", "最初のサイトマップの URL に認証情報（userinfo）がある",
                   "Cookie は、サーバーが Set-Cookie で返したもの", "終了コード 2 で止める"]:
        if needle not in proc.stdout:
            f.append("--help に {!r} がない".format(needle))
    with open(AUDIT, encoding="utf-8") as fh:
        src = fh.read()
    doc = ast.get_docstring(ast.parse(src)) or ""
    for needle in ["ログインが必要なページは取得できない。認証情報（Authorization ヘッダー）は送らない",
                   "SKIPPED:credentials-in-url", "https://***@example.jp/sitemap.xml", "trust_env",
                   "Session.auth に何もしない認証（_NoAuth）", "HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY",
                   "REQUESTS_CA_BUNDLE", "最初のサイトマップの URL（引数）に認証情報（userinfo",
                   "Googlebot は Cookie を保持しない"]:
        if needle not in doc:
            f.append("ヘッダーコメントに {!r} がない".format(needle))
    if "（Cookie や認証情報を送らない）" in src:
        f.append("実際と合わない古い記述「（Cookie や認証情報を送らない）」が残っている")
    record("--help とヘッダーコメント: 認証情報・.netrc・Cookie の記述と終了コード 2", f,
           "SKIPPED:credentials-in-url・伏せ字の例・.netrc・trust_env の判断・Cookie の挙動・終了コード 2 の追記を確認")


def case_cred_root(py, srv):
    port = srv.port
    f = []
    out = os.path.join(OUT, "cred_should_not_exist.csv")
    small = "http://***@127.0.0.1:{}/sitemaps/small.xml".format(port)
    reason = "サイトマップの URL に認証情報（userinfo。user:pass@ などの部分）が含まれているため、取得しません: "
    variants = [
        ("http://rootUser:rootPass@127.0.0.1:{}/sitemaps/small.xml".format(port), reason + small),
        ("http://rootOnlyUser@127.0.0.1:{}/sitemaps/small.xml".format(port), reason + small),
        ("http://@127.0.0.1:{}/sitemaps/small.xml".format(port), reason + small),
        ("HTTPS://upperUser:upperPass@example.jp/sitemap.xml", reason + "HTTPS://***@example.jp/sitemap.xml"),
        ("https://v6User:v6Pass@[::1/sitemap.xml", reason + "https://***@[::1/sitemap.xml"),
        ("http://hostlessUser:hostlessPass@/sitemap.xml", reason + "http://***@/sitemap.xml"),
        ("ftp://ftpUser:ftpPass@example.jp/sitemap.xml", "サイトマップが見つかりません: ftp://***@example.jp/sitemap.xml"),
        ("bareUser:barePass@example.jp/sitemap.xml", "サイトマップが見つかりません: ***@example.jp/sitemap.xml"),
    ]
    secrets = ["rootUser", "rootPass", "rootOnlyUser", "upperUser", "upperPass", "v6User", "v6Pass", "hostlessUser",
               "hostlessPass", "ftpUser", "ftpPass", "bareUser", "barePass"]
    for arg, needle in variants:
        for allow_private in (True, False):
            if os.path.exists(out):
                os.remove(out)
            proc, log = run_audit(py, [arg, "-o", out, "--delay", "0.05"], allow_private=allow_private)
            label = "{}{}: ".format(needle.rsplit(": ", 1)[-1], "" if allow_private else "（--allow-private なし）")
            no_traceback(proc, f, label)
            if proc.returncode != 2 or needle not in proc.stderr:
                f.append("{}rc={} stderr={}".format(label, proc.returncode, proc.stderr[-300:]))
            if leaked(secrets, proc.stdout, proc.stderr):
                f.append("{}認証情報が出力に出た: {}".format(label, leaked(secrets, proc.stdout, proc.stderr)))
            if log:
                f.append("{}サーバーにリクエストが届いた: {}".format(label, [e["path"] for e in log]))
            if os.path.exists(out):
                f.append("{}終了コード 2 なのに CSV が作られた".format(label))
    # 余分な引数（unrecognized arguments）の表示でも伏せる
    proc, log = run_audit(py, [srv.base + "/sitemaps/small.xml", "http://extraUser:extraPass@127.0.0.1/x", "-o", out])
    if proc.returncode != 2 or "http://***@127.0.0.1/x" not in proc.stderr or \
            leaked(["extraUser", "extraPass"], proc.stdout, proc.stderr) or log:
        f.append("余分な引数: rc={} stderr={}".format(proc.returncode, proc.stderr[-300:]))
    record("引数の URL に userinfo: 終了コード 2・理由を表示・URL は伏せる・リクエスト 0 回", f,
           "user:pass@ / user@ / 空の @ / 大文字のスキーム / 壊れた IPv6 / ホストなしは理由付きで 2（--allow-private の"
           "有無とも）、ftp:// とスキームなしの user:pass@host も伏せて 2、余分な引数のエラーも伏せる。どれも "
           "stdout / stderr に認証情報なし・CSV なし・サーバーへのリクエスト 0 回")


def case_cred_pages(py, srv):
    b = srv.base
    port = srv.port
    masked = "http://***@127.0.0.1:{}".format(port)
    two_h1 = P("h1が2個", 5, wc=4, h1=2)
    secrets = ["pageUser", "pagePass", "pageOnlyUser", "otherUser", "otherPass", "enc%40User", "enc@User", "p%3Ass",
               "relUser", "relPass"]
    expected = [(masked + "/p/english", E(STATUS_CRED)), (masked + "/p/english?only", E(STATUS_CRED)),
                (masked + "/p/english?empty", E(STATUS_CRED)),
                ("http://***@localhost:{}/p/english".format(port), E(STATUS_CRED)),
                ("HTTP://***@127.0.0.1:{}/p/english?pct".format(port), E(STATUS_CRED)),
                (masked + "/p/english?rel", E(STATUS_CRED)), (b + "/p/two-h1", two_h1)]
    f = []
    for label, extra in [("既定", []), ("--no-sanitize", ["--no-sanitize"])]:
        out = os.path.join(OUT, "cred_pages{}.csv".format("" if not extra else "_nosanitize"))
        proc, log = run_audit(py, [b + "/sm/cred-pages.xml", "-o", out, "--delay", "0.05"] + extra)
        no_traceback(proc, f, label + ": ")
        _, _, rows, _ = read_csv(out)
        compare_rows(rows, expected, f, label + ": ")
        if proc.returncode != 0:
            f.append("{}: rc={}".format(label, proc.returncode))
        if [e["path"] for e in log] != ["/sm/cred-pages.xml", "/robots.txt", "/p/two-h1"] or auth_sent(log):
            f.append("{}: リクエスト={} Authorization={}".format(label, [e["raw"] for e in log], auth_sent(log)))
        if leaked(secrets, proc.stdout, proc.stderr, file_text(out)):
            f.append("{}: 認証情報が出力に出た: {}".format(label, leaked(secrets, proc.stdout, proc.stderr, file_text(out))))
        for needle in ["[1/7] SKIPPED:credentials-in-url " + masked + "/p/english\n",
                       "URL に認証情報（userinfo）が含まれるため取得しませんでした（Basic 認証として送られるのを防ぐため）",
                       "注意: URL に認証情報（userinfo）を含むページが 6 件あります",
                       "URL に認証情報（userinfo）を含むため取得しなかった（SKIPPED:credentials-in-url）: ページ 6 件 / "
                       "子サイトマップ 0 件", "  SKIPPED:credentials-in-url: 6",
                       "サイトマップと別のホストのため取得しなかった（SKIPPED:other-host）: ページ 0 件"]:
            if needle not in proc.stderr:
                f.append("{}: stderr に {!r} がない".format(label, needle))
        if "別のホストの URL が" in proc.stderr:
            f.append("{}: userinfo 付きの別のホストの URL を別のホストの警告に数えている".format(label))
    # ローカルファイル: userinfo 付きの loc は基準のホストにしない。スキップの表示（ftp:// と //user:pass@）も伏せる
    path = os.path.join(OUT, "cred_local.xml")
    with open(path, "wb") as fh:
        fh.write(_sitemap_xml(["http://locUser:locPass@localhost:{}/p/english".format(port), b + "/p/two-h1",
                               "ftp://ftpLocUser:ftpLocPass@127.0.0.1/x", "//relLocUser:relLocPass@127.0.0.1/y"]))
    out = os.path.join(OUT, "cred_local.csv")
    proc, log = run_audit(py, [path, "-o", out, "--delay", "0.05"])
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [("http://***@localhost:{}/p/english".format(port), E(STATUS_CRED)), (b + "/p/two-h1", two_h1)],
                 f, "ローカル: ")
    local_secrets = ["locUser", "locPass", "ftpLocUser", "ftpLocPass", "relLocUser", "relLocPass"]
    if proc.returncode != 0 or leaked(local_secrets, proc.stdout, proc.stderr, file_text(out)) or auth_sent(log) or \
            any(e["host"].startswith("localhost") for e in log):
        f.append("ローカル: rc={} leaked={} requests={}".format(
            proc.returncode, leaked(local_secrets, proc.stderr, file_text(out)), [e["raw"] for e in log]))
    for needle in ["http / https 以外の URL の loc をスキップ: ftp://***@127.0.0.1/x",
                   "相対 URL の loc はローカルファイルからは解決できないためスキップ: //***@127.0.0.1/y",
                   "基準のホスト: 127.0.0.1）"]:
        if needle not in proc.stderr:
            f.append("ローカル: stderr に {!r} がない".format(needle))
    record("loc に userinfo: SKIPPED:credentials-in-url・url 列は伏せる・リクエストも Authorization も 0", f,
           "user:pass@ / user@ / 空の @ / 別のホスト / %XX / スキーム省略の 6 件を取得せず（別のホストより優先）、"
           "サーバーに届いたのはサイトマップ・robots.txt・通常のページだけ、Authorization なし、CSV（--no-sanitize "
           "でも）・進捗行・サマリーに認証情報なし。ローカルファイルでは userinfo 付きの loc を基準のホストにせず、"
           "ftp:// と //user:pass@ のスキップ表示も伏せる")


def case_cred_redirect(py, srv):
    b = srv.base
    port = srv.port
    masked = "http://***@127.0.0.1:{}".format(port)
    f = []
    out = os.path.join(OUT, "cred_redirects.csv")
    proc, log = run_audit(py, [b + "/sm/cred-redirects.xml", "-o", out, "--delay", "0.05"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [(b + "/r/to-cred", E(STATUS_CRED, redirect_to=masked + "/p/english")),
                        (b + "/r/to-cred-user", E(STATUS_CRED, redirect_to=masked + "/p/english?user")),
                        (b + "/r/to-cred-empty", E(STATUS_CRED, redirect_to=masked + "/p/english?empty")),
                        (b + "/r/to-cred-schemeless", E(STATUS_CRED, redirect_to=masked + "/p/english?schemeless")),
                        (b + "/r/chain-to-cred", E(STATUS_CRED, redirect_to=masked + "/p/english")),
                        (b + "/p/two-h1", P("h1が2個", 5, wc=4, h1=2))], f, "リダイレクト: ")
    paths = [e["path"] for e in log]
    if proc.returncode != 0 or "/p/english" in paths or auth_sent(log) or \
            paths != ["/sm/cred-redirects.xml", "/robots.txt", "/r/to-cred", "/r/to-cred-user", "/r/to-cred-empty",
                      "/r/to-cred-schemeless", "/r/chain-to-cred", "/r/to-cred", "/p/two-h1"]:
        f.append("リダイレクト: rc={} リクエスト={} Authorization={}".format(proc.returncode, paths, auth_sent(log)))
    secrets = ["redirUser", "redirPass", "redirOnlyUser", "slUser", "slPass"]
    if leaked(secrets, proc.stdout, proc.stderr, file_text(out)):
        f.append("リダイレクト: 認証情報が出力に出た: {}".format(leaked(secrets, proc.stderr, file_text(out))))
    for needle in ["リダイレクト先の URL に認証情報（userinfo）が含まれるため取得しませんでした: " + masked + "/p/english",
                   "（SKIPPED:credentials-in-url）: ページ 5 件 / 子サイトマップ 0 件"]:
        if needle not in proc.stderr:
            f.append("リダイレクト: stderr に {!r} がない".format(needle))
    # 最初のサイトマップのリダイレクト先に userinfo → 取得できなかった扱いで終了コード 2
    out2 = os.path.join(OUT, "cred_redirect_root.csv")
    if os.path.exists(out2):
        os.remove(out2)
    proc, log = run_audit(py, [b + "/sm/redirect-to-cred.xml", "-o", out2, "--delay", "0.05"])
    no_traceback(proc, f, "サイトマップ: ")
    if proc.returncode != 2 or os.path.exists(out2) or [e["path"] for e in log] != ["/sm/redirect-to-cred.xml"] or \
            auth_sent(log) or leaked(["smUser", "smPass"], proc.stdout, proc.stderr):
        f.append("サイトマップ: rc={} csv={} リクエスト={} stderr={}".format(
            proc.returncode, os.path.exists(out2), [e["path"] for e in log], proc.stderr[-400:]))
    for needle in ["リダイレクト先 {}/sitemaps/small.xml に認証情報（userinfo）が含まれます".format(masked),
                   "最初のサイトマップを取得・解析できず",
                   "サイトマップのリダイレクト先の URL に認証情報（userinfo）が含まれるため、取得しませんでした"]:
        if needle not in proc.stderr:
            f.append("サイトマップ: stderr に {!r} がない".format(needle))
    record("リダイレクト先に userinfo: その段で止めて SKIPPED:credentials-in-url、redirect_to は伏せる", f,
           "301 / 302 / 307 / 308・user@・空の @・スキーム省略の //user:pass@・2 段のチェーンで止め、リダイレクト先への"
           "リクエストと Authorization は 0、最初のサイトマップのリダイレクト先なら終了コード 2（CSV なし）")


def case_cred_child(py, srv):
    b = srv.base
    port = srv.port
    masked = "http://***@127.0.0.1:{}".format(port)
    f = []
    out = os.path.join(OUT, "cred_child.csv")
    proc, log = run_audit(py, [b + "/sm/idx-cred-child.xml", "-o", out, "--delay", "0.05"])
    no_traceback(proc, f)
    _, _, rows, _ = read_csv(out)
    compare_rows(rows, [(b + "/p/english", P("English Page", 12, wc=14, desc="An English description.", desc_len=23))],
                 f)
    paths = [e["path"] for e in log]
    if proc.returncode != 0 or "/sm/idx-leaf2.xml" in paths or "/sm/idx-urls.xml" in paths or auth_sent(log) or \
            "/sm/child-redirect-cred.xml" not in paths:
        f.append("rc={} リクエスト={} Authorization={}".format(proc.returncode, paths, auth_sent(log)))
    secrets = ["childUser", "childPass", "crUser", "crPass"]
    if leaked(secrets, proc.stdout, proc.stderr, file_text(out)):
        f.append("認証情報が出力に出た: {}".format(leaked(secrets, proc.stderr, file_text(out))))
    for needle in ["注意: URL に認証情報（userinfo）を含む子サイトマップは取得しません: " + masked + "/sm/idx-leaf2.xml",
                   "注意: URL に認証情報（userinfo）を含む子サイトマップは取得しません: " + masked + "/sm/idx-urls.xml",
                   "注意: サイトマップを取得しません。リダイレクト先 {}/sm/idx-leaf2.xml に認証情報（userinfo）が"
                   "含まれます: {}/sm/child-redirect-cred.xml".format(masked, b),
                   "（SKIPPED:credentials-in-url）: ページ 0 件 / 子サイトマップ 3 件",
                   "サイトマップ: 読み込み 2 件 / 失敗 1 件"]:
        if needle not in proc.stderr:
            f.append("stderr に {!r} がない".format(needle))
    record("子サイトマップに userinfo: 取得せず注意を出し、サマリーに件数", f,
           "user:pass@ と空の @ の子サイトマップ 2 本と、リダイレクト先に userinfo がある 1 本を取得せず（リクエスト・"
           "Authorization 0）、伏せた URL で注意、サマリーに子サイトマップ 3 件")


def case_cred_netrc(py, srv):
    import base64
    import shutil
    b = srv.base
    f = []
    home = os.path.join(OUT, "netrc_home")  # 絶対パス（OUT は絶対パス）
    if os.path.isdir(home):
        shutil.rmtree(home)
    os.makedirs(home)
    netrc_path = os.path.join(home, ".netrc")
    with open(netrc_path, "w", encoding="ascii") as fh:
        for machine in ["127.0.0.1", "localhost", "proxy-target.invalid"]:
            fh.write("machine {} login netrcUser password netrcPass\n".format(machine))
    os.chmod(netrc_path, 0o600)
    expected = "Basic " + base64.b64encode(b"netrcUser:netrcPass").decode("ascii")
    env = dict(os.environ, HOME=home, COLUMNS="200")
    for name in ["NETRC", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy",
                 "NO_PROXY", "no_proxy", "REQUEST_METHOD"]:
        env.pop(name, None)
    if os.path.exists(CERT):
        env["REQUESTS_CA_BUNDLE"] = CERT
    control = "import sys, requests; requests.get(sys.argv[1], timeout=5).close()"
    details = []
    try:
        for label, run_env in [("HOME の ~/.netrc", env), ("環境変数 NETRC", dict(env, HOME=OUT, NETRC=netrc_path))]:
            # 対照: 素の requests はこの .netrc で Basic 認証を付ける（テストの前提が成り立っていることの確認）
            start = log_size()
            ctl = subprocess.run([py, "-c", control, b + NETRC_CONTROL], env=run_env, capture_output=True, text=True,
                                 timeout=60)
            got = [e.get("auth") for e in log_since(start)]
            if ctl.returncode != 0 or got != [expected]:
                f.append("{}: 対照（素の requests）で .netrc の認証が付かない（前提が崩れている）: rc={} auth={} {}".format(
                    label, ctl.returncode, got, ctl.stderr[-300:]))
            out = os.path.join(OUT, "cred_netrc.csv")
            if os.path.exists(out):
                os.remove(out)
            start = log_size()
            proc = subprocess.run([py, AUDIT, b + "/sitemaps/small.xml", "-o", out, "--delay", "0.05", "--allow-private"],
                                  env=run_env, capture_output=True, text=True, timeout=120)
            log = log_since(start)
            _, _, rows, _ = read_csv(out)
            if proc.returncode != 0 or [r["status"] for r in rows] != ["200", "200"] or len(log) != 4 or auth_sent(log):
                f.append("{}: rc={} status={} リクエスト {} 件 Authorization={}".format(
                    label, proc.returncode, [r["status"] for r in rows], len(log), auth_sent(log)))
            if leaked(["netrcUser", "netrcPass"], proc.stdout, proc.stderr, file_text(out)):
                f.append("{}: .netrc の認証情報が出力に出た".format(label))
            details.append("{}: 対照は Authorization あり・audit.py は {} 件とも なし".format(label, len(log)))
        # trust_env は True のまま: プロキシの環境変数は使う（テストサーバーをプロキシに見立てる）。.netrc は使わない
        out = os.path.join(OUT, "cred_proxy.csv")
        start = log_size()
        proc = subprocess.run([py, AUDIT, "http://proxy-target.invalid/sitemaps/small.xml", "-o", out, "--delay", "0.05",
                               "--allow-private", "--ignore-robots", "--allow-other-hosts", "--limit", "1"],
                              env=dict(env, HTTP_PROXY=b, http_proxy=b), capture_output=True, text=True, timeout=120)
        log = log_since(start)
        _, _, rows, _ = read_csv(out)
        proxied = [e for e in log if e["raw"].startswith("http://proxy-target.invalid/")]
        if proc.returncode != 0 or [r["status"] for r in rows] != ["200"] or len(proxied) != 1 or \
                proxied[0]["host"] != "proxy-target.invalid" or auth_sent(log):
            f.append("プロキシ: rc={} status={} リクエスト={} Authorization={} stderr={}".format(
                proc.returncode, [r["status"] for r in rows], [e["raw"] for e in log], auth_sent(log),
                proc.stderr[-300:]))
        details.append("HTTP_PROXY 経由の取得も成功（プロキシへ絶対 URI で到着）・Authorization なし")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    if os.path.exists(home):
        f.append("一時フォルダを消せなかった: {}".format(home))
    record("~/.netrc による自動の Basic 認証が起きない（HOME を一時フォルダに差し替え）・プロキシの環境変数は使う", f,
           " / ".join(details))


def case_cred_no_auth_anywhere(py, srv):
    """このテスト全体でサーバーに届いたリクエストに、Authorization が1度もないこと（対照のリクエストを除く）。"""
    with open(LOG, "r", encoding="utf-8") as fh:
        entries = [json.loads(line) for line in fh if line.strip()]
    sent = [(e["raw"], e.get("auth")) for e in entries if e.get("auth") and e["raw"] != NETRC_CONTROL]
    record("Authorization ヘッダーが1度も送られていない（このテスト全体のサーバー側の記録）", ["送られた: {}".format(sent)] if sent else [],
           "記録 {} 件（.netrc の対照の素の requests を除く）".format(len(entries)))


CASES = [("units", case_units), ("syntax", case_py39_syntax), ("help", case_help), ("main", case_main),
         ("limit", case_limit), ("ignore_robots", case_ignore_robots), ("count_mode", case_count_mode),
         ("max_depth", case_max_depth), ("local_file", case_local_file), ("exit_codes", case_exit_codes),
         ("default_delay", case_default_delay), ("interrupt", case_interrupt),
         ("robots_unit", case_robots_unit), ("sitemap_unit", case_sitemap_unit), ("html_unit", case_html_unit),
         ("sitemap_attack", case_sitemap_attack), ("feeds", case_feeds), ("non_html", case_non_html),
         ("html_attack", case_html_attack), ("http_attack", case_http_attack),
         ("robots_integration", case_robots_integration), ("robots_status", case_robots_status),
         ("args", case_args), ("big_sitemap", case_big_sitemap), ("sanitize", case_sanitize),
         ("nested_index", case_nested_index), ("private_unit", case_private_unit),
         ("private_default", case_private_default), ("private_redirect", case_private_redirect),
         ("other_host", case_other_host), ("retry_after", case_retry_after), ("throttle_abort", case_throttle_abort),
         ("sitemap_limits", case_sitemap_limits),
         ("cred_unit", case_cred_unit), ("cred_help", case_cred_help), ("cred_root", case_cred_root),
         ("cred_pages", case_cred_pages), ("cred_redirect", case_cred_redirect), ("cred_child", case_cred_child),
         ("cred_netrc", case_cred_netrc), ("cred_no_auth_anywhere", case_cred_no_auth_anywhere),
         ("get_only", case_get_only), ("no_pycache", case_no_pycache)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--cases", default="")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    selected = [c for c in args.cases.split(",") if c]
    srv = Server(sys.executable)
    try:
        print("server: {} (ssl-fake {}, closed {}) / audit python: {}".format(
            srv.base, srv.ssl_port, srv.closed_port, args.python))
        for name, fn in CASES:
            if selected and name not in selected:
                continue
            try:
                fn(args.python, srv)
            except Exception as exc:  # 検証スクリプト自体の失敗も FAIL として記録
                record(name, ["例外 {}: {}".format(type(exc).__name__, exc)], "")
    finally:
        srv.stop()
        print("server stopped: returncode={}".format(srv.proc.returncode))
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n{}/{} passed".format(passed, len(RESULTS)))
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
        json.dump([{"name": n, "ok": ok, "detail": d} for n, ok, d in RESULTS], fh, ensure_ascii=False, indent=1)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
