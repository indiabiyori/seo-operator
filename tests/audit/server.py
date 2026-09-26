#!/usr/bin/env python3
"""
audit.py のテスト用ローカル HTTP サーバー。

起動すると標準出力に1行 "PORT <http のポート> <偽 TLS のポート>" を出す。
すべてのリクエストを JSON Lines でアクセスログに記録する（時刻・メソッド・Host・パス・User-Agent・
Authorization・Cookie）。プロキシとして絶対 URI（GET http://host/path）で受けた場合も、パスで応答する。
Host が localhost のときの robots.txt は /__admin/robots?mode=... で切り替えられる（ログには残さない）。

  python3 server.py --closed-port 54321 --log access.log
"""
import argparse
import email.utils
import gzip
import json
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
STATE = {"port": 0, "ssl_port": 0, "https_port": 0, "closed_port": 0, "log": None, "robots_mode": "complex"}
CACHE = {}

STD_MAIN = "<main><h1>見出し</h1><p>本文です</p></main>"  # 見出し(3)+本文です(4) = 7 文字


def B():
    return "http://127.0.0.1:{}".format(STATE["port"])


def html_page(body, title=None, desc=None, head_extra="", lang="ja"):
    parts = ["<!DOCTYPE html>", '<html lang="{}">'.format(lang) if lang else "<html>", "<head>",
             '<meta charset="utf-8">']
    if title is not None:
        parts.append("<title>{}</title>".format(title))
    if desc is not None:
        parts.append('<meta name="description" content="{}">'.format(desc))
    parts.append(head_extra)
    parts.append("</head>")
    parts.append("<body>{}</body></html>".format(body))
    return "\n".join(parts).encode("utf-8")


HTML_UTF8 = "text/html; charset=utf-8"


def simple(title, head_extra="", headers=None, body=STD_MAIN, desc="説明", lang="ja"):
    return (200, [("Content-Type", HTML_UTF8)] + (headers or []),
            html_page(body, title=title, desc=desc, head_extra=head_extra, lang=lang))


def urlset(urls, ns=True):
    xmlns = ' xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' if ns else ""
    items = "".join("<url><loc>{}</loc></url>\n".format(u) for u in urls)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset{}>\n{}</urlset>\n'.format(xmlns, items).encode("utf-8")


def sitemapindex(urls):
    items = "".join("<sitemap><loc>{}</loc></sitemap>\n".format(u) for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{}</sitemapindex>\n'
            .format(items)).encode("utf-8")


XML = [("Content-Type", "application/xml")]


def L():
    return "http://localhost:{}".format(STATE["port"])


LOCALHOST_ROBOTS_COMPLEX = """User-agent: *
Disallow: /

# コメント行
User-Agent: SEO-Operator-Audit   # 値の大文字小文字は区別しない
Disallow: /x/*.pdf$
Disallow: /p/no-
Allow: /p/no-title
Disallow: /p/%E6%97%A5
Sitemap: {L}/sitemap.xml

user-agent: otherbot
disallow: /p/english

user-agent: seo-operator-audit/2.0
disallow: /p/two-h1$
allow: /p/ja-normal$
disallow: /p/ja-
"""


def robots_for_localhost(path):
    mode = STATE["robots_mode"]
    txt = [("Content-Type", "text/plain; charset=utf-8")]
    if path == "/robots-real.txt":
        return 200, txt, b"User-agent: *\nDisallow: /p/english\n", 0
    if path == "/robots-loop":
        return 302, [("Location", "/robots.txt")], b"", 0
    if mode == "complex":
        return 200, txt, LOCALHOST_ROBOTS_COMPLEX.format(L=L()).encode("utf-8"), 0
    if mode in ("404", "500", "503", "429", "403"):
        return int(mode), txt, b"error", 0
    if mode == "slow":
        return 200, txt, b"User-agent: *\nDisallow: /\n", 3.0
    if mode == "redirect":
        return 301, [("Location", "/robots-real.txt")], b"", 0
    if mode == "loop":
        return 302, [("Location", "/robots-loop")], b"", 0
    if mode == "html":
        return 200, [("Content-Type", HTML_UTF8)], html_page("<p>Disallow: /p/english</p>", title="robots"), 0
    if mode == "bom-cr":
        return 200, txt, "\ufeffUser-agent: *\rDisallow: /p/english\r".encode("utf-8"), 0
    if mode == "cut":  # 500 KiB の境目で「Disallow: /p/」まで読める位置に行を置く
        head = "User-agent: *\n"
        target = 500 * 1024 - len("Disallow: /p/")
        body = head + "#" + "x" * (target - len(head) - 2) + "\n" + "Disallow: /p/zzzz\n"
        return 200, txt, body.encode("utf-8"), 0
    if mode == "big":
        body = "User-agent: *\n" + ("# " + "x" * 98 + "\n") * 5200 + "Disallow: /p/english\n"
        return 200, txt, body.encode("utf-8"), 0
    raise ValueError(mode)


def big_sitemap():
    if "big" not in CACHE:
        CACHE["big"] = urlset([B() + "/p/big/{}".format(i) for i in range(50000)])
    return CACHE["big"]


def over50k_sitemap():
    if "50k" not in CACHE:
        CACHE["50k"] = urlset([B() + "/p/big/{}".format(i) for i in range(50001)])
    return CACHE["50k"]


def over50mb_gz():
    """展開後 50MB（52,428,800 バイト）を超え、URL は 40,000 件の gzip サイトマップ。"""
    if "50mb" not in CACHE:
        pad = "x" * 1300
        xml = urlset([B() + "/p/pad/{}?q={}".format(i, pad) for i in range(40000)])
        CACHE["50mb"] = (len(xml), gzip.compress(xml, compresslevel=1))
    return CACHE["50mb"]


def attack_route(path, host):
    """攻撃的テスト用のルート。該当しなければ None。"""
    b = B()
    loc = L()
    xml_utf8 = '<?xml version="1.0" encoding="UTF-8"?>\n'
    ns = ' xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'

    if host.startswith("localhost") and path in ("/robots.txt", "/robots-real.txt", "/robots-loop"):
        return robots_for_localhost(path)

    # --- サイトマップ ---
    if path == "/sm/messy.xml":
        body = (xml_utf8 + "<urlset{ns}>\n"
                "<url><loc>\n   {b}/p/english \n\t</loc></url>\n"
                "<url><loc><![CDATA[{b}/p/two-h1]]></loc></url>\n"
                "<url><loc>{b}/h/entity-title?a=1&amp;b=2</loc></url>\n"
                "<url><loc>/p/no-desc</loc></url>\n"
                "<url><loc>//127.0.0.1:{port}/p/no-title</loc></url>\n"
                "<url><loc>mailto:someone@example.com</loc></url>\n"
                "<url><loc>javascript:alert(1)</loc></url>\n"
                "<url><loc>ftp://127.0.0.1/file.txt</loc></url>\n"
                "<url><loc></loc></url>\n"
                "<url><loc>   </loc></url>\n"
                "<url><lastmod>2026-01-01</lastmod></url>\n"
                "<url><loc>HTTP://127.0.0.1:{port}/p/english</loc></url>\n"
                "<url><loc>{b}/p/english#frag</loc></url>\n"
                "<url><loc>{b}/P/English</loc></url>\n"
                "<url><loc>{b}/p/ja-\tnormal</loc></url>\n"
                "</urlset>\n").format(ns=ns, b=b, port=STATE["port"])
        return 200, XML, body.encode("utf-8"), 0
    if path == "/sm/bom.xml":
        return 200, XML, b"\xef\xbb\xbf" + urlset([b + "/p/english"]), 0
    if path == "/sm/ws-bom.xml":
        return 200, XML, b"\n  \xef\xbb\xbf\n" + urlset([b + "/p/two-h1"]), 0
    if path == "/sm/utf16.xml":
        text = urlset([b + "/p/english"]).decode("utf-8").replace('encoding="UTF-8"', 'encoding="UTF-16"')
        return 200, XML, text.encode("utf-16"), 0
    if path == "/sm/utf16-dtd.xml":
        text = ('<?xml version="1.0" encoding="UTF-16"?>\n<!DOCTYPE lolz [<!ENTITY lol "lol">]>\n'
                '<urlset><url><loc>{}/p/english&lol;</loc></url></urlset>').format(b)
        return 200, XML, text.encode("utf-16"), 0
    if path == "/sm/sjis.xml":
        text = ('<?xml version="1.0" encoding="Shift_JIS"?>\n<urlset{}><url><loc>{}/p/日本語</loc></url>'
                '</urlset>').format(ns, b)
        return 200, XML, text.encode("cp932"), 0
    if path == "/sm/html-ct.xml":
        return 200, [("Content-Type", "text/html; charset=utf-8")], urlset([b + "/p/english"]), 0
    if path == "/sm/ce-gzip.xml":
        return 200, [("Content-Type", "application/xml"), ("Content-Encoding", "gzip")], \
            gzip.compress(urlset([b + "/p/english", b + "/p/two-h1"])), 0
    if path == "/sm/double.xml.gz":
        return 200, [("Content-Type", "application/x-gzip"), ("Content-Encoding", "gzip")], \
            gzip.compress(gzip.compress(urlset([b + "/p/no-title"]))), 0
    if path == "/sm/truncated.xml":
        full = urlset([b + "/p/english", b + "/p/two-h1", b + "/p/no-title"])
        cut = full.index(b"/p/no-title")
        return 200, XML, full[:cut], 0
    if path == "/sm/truncated.xml.gz":
        urls = [b + "/p/english"] + [b + "/p/gz/{}".format(i) for i in range(3000)]
        data = gzip.compress(urlset(urls))
        return 200, [("Content-Type", "application/x-gzip")], data[:int(len(data) * 0.6)], 0
    if path == "/sm/broken-early.xml":
        return 200, XML, b'<?xml version="1.0"?><urlset><url><lo', 0
    if path == "/sm/html-page.xml":
        return 200, [("Content-Type", HTML_UTF8)], html_page("<p>not found</p>", title="404"), 0
    if path == "/sm/big.xml":
        return 200, XML, big_sitemap(), 0
    if path == "/sm/redirect.xml":
        return 301, [("Location", "/sm/sub/rel.xml")], b"", 0
    if path == "/sm/sub/rel.xml":
        return 200, XML, urlset(["english-rel"]), 0
    if path == "/sm/sub/english-rel":
        return simple("相対解決", lang="ja") + (0,)
    if path == "/sm/index-mixed.xml":
        return 200, XML, sitemapindex(["mailto:x@example.com", "/f/rss.xml", "/f/atom.xml", "  "]), 0
    if path == "/sm/slow.xml":
        return 200, XML, urlset([b + "/p/english"]), 3.0
    if path == "/sm/robots-localhost.xml":
        return 200, XML, urlset([loc + p for p in [
            "/p/english", "/x/nolink.png", "/x/noindex.pdf", "/x/noindex.pdf?download=1", "/p/no-title",
            "/p/no-desc", "/p/日本語", "/p/two-h1", "/p/two-h1?x=1", "/p/ja-normal", "/p/ja-article"]]), 0
    if path == "/sm/robots-status.xml":
        return 200, XML, urlset([loc + "/p/english", loc + "/p/two-h1"]), 0
    if path == "/sm/non-html.xml":
        return 200, XML, urlset([b + p for p in [
            "/p/doc.pdf", "/x/noindex.pdf", "/x/googlebot-noindex.pdf", "/x/nolink.png", "/x/no-ct-binary",
            "/x/pdf-404", "/x/redirect-pdf", "/x/two-link.pdf", "/x/empty-200"]]), 0
    if path == "/sm/html-attack.xml":
        return 200, XML, urlset([b + p for p in [
            "/h/entity-title", "/h/tag-in-title", "/h/desc-upper", "/h/desc-property", "/h/desc-two",
            "/h/canonical-two-same", "/h/canonical-two-diff", "/h/canonical-ws", "/h/canonical-after-img",
            "/h/canonical-noclose-head", "/h/canonical-vs-header", "/h/xrobots-combo", "/h/xrobots-nofollow",
            "/h/no-ct", "/h/wrong-charset-header", "/h/wrong-charset-nometa", "/h/meta-wrong",
            "/h/long-title", "/h/unclosed-title", "/h/title-two"]]), 0
    if path == "/sm/http-attack.xml":
        return 200, XML, urlset([b + p for p in [
            "/r/cross-host", "/r/to-https", "/r/a/b/rel", "/r/no-location", "/r/empty-location",
            "/r/to-mailto", "/r/to-real-https"]]), 0

    # --- フィード ---
    if path == "/f/rss.xml":
        body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>\n'
                "<title>t</title><link>{b}/</link>\n"
                '<atom:link href="{b}/f/rss.xml" rel="self" type="application/rss+xml"/>\n'
                "<item><title>a</title><link>  {b}/p/english  </link><guid>x</guid></item>\n"
                "<item><title>b</title><link><![CDATA[{b}/p/two-h1]]></link></item>\n"
                '<item><title>c</title><atom:link href="{b}/wrong" rel="related"/><link>/p/no-desc</link></item>\n'
                '<item><title>d</title><guid isPermaLink="true">{b}/p/guid-only</guid></item>\n'
                "</channel></rss>\n").format(b=b)
        return 200, [("Content-Type", "application/rss+xml")], body.encode("utf-8"), 0
    if path == "/f/atom.xml":
        body = ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<feed xmlns="http://www.w3.org/2005/Atom" xml:base="{b}/f/">\n'
                '<title>t</title><link href="{b}/" rel="alternate"/>\n'
                '<entry><title>a</title><link rel="self" href="{b}/api/1"/>'
                '<link rel="alternate" type="text/html" href="{b}/p/english"/></entry>\n'
                '<entry><title>b</title><link href="../p/two-h1"/></entry>\n'
                '<entry xml:base="{b}/p/"><title>c</title><link href="no-desc"/></entry>\n'
                '<entry><title>d</title><link rel="edit" href="{b}/edit/4"/></entry>\n'
                '<entry><title>e</title><link rel="enclosure" href="{b}/x.mp3"/><link href=" {b}/p/no-title "/></entry>\n'
                "</feed>\n").format(b=b)
        return 200, [("Content-Type", "application/atom+xml")], body.encode("utf-8"), 0
    if path == "/f/rdf.xml":
        body = ('<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                'xmlns="http://purl.org/rss/1.0/"><channel rdf:about="{b}/"><title>t</title><link>{b}/</link>'
                '<items><rdf:Seq><rdf:li rdf:resource="{b}/p/english"/></rdf:Seq></items></channel>'
                '<item rdf:about="{b}/p/english"><title>a</title><link>{b}/p/english</link></item>'
                "</rdf:RDF>").format(b=b)
        return 200, [("Content-Type", "application/rdf+xml")], body.encode("utf-8"), 0
    if path == "/f/atom03.xml":
        body = ('<?xml version="1.0" encoding="utf-8"?>\n<feed version="0.3" xmlns="http://purl.org/atom/ns#">'
                '<title>t</title><entry><title>a</title>'
                '<link rel="alternate" type="text/html" href="{b}/p/two-h1"/></entry></feed>').format(b=b)
        return 200, [("Content-Type", "application/atom+xml")], body.encode("utf-8"), 0

    # --- HTML でないレスポンス ---
    pdf = b"%PDF-1.4\n%fake pdf\n"
    if path == "/x/noindex.pdf":
        return 200, [("Content-Type", "application/pdf"), ("X-Robots-Tag", "noindex, nofollow"),
                     ("Link", '<{}/p/doc.pdf>; rel="canonical"'.format(b))], pdf, 0
    if path == "/x/googlebot-noindex.pdf":
        return 200, [("Content-Type", "application/pdf"), ("X-Robots-Tag", "googlebot: noindex"),
                     ("Link", "</x/other.pdf>; rel=canonical")], pdf, 0
    if path == "/x/nolink.png":
        return 200, [("Content-Type", "image/png")], b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, 0
    if path == "/x/no-ct-binary":
        return 200, [("X-Robots-Tag", "otherbot: noindex")], b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, 0
    if path == "/x/pdf-404":
        return 404, [("Content-Type", "application/pdf"), ("X-Robots-Tag", "noindex"),
                     ("Link", '<{}/p/doc.pdf>; rel="canonical"'.format(b))], pdf, 0
    if path == "/x/redirect-pdf":
        return 301, [("Location", "/x/noindex.pdf")], b"", 0
    if path == "/x/two-link.pdf":
        return 200, [("Content-Type", "application/pdf"),
                     ("Link", '<{0}/x/two-link.pdf>; rel="canonical", <{0}/p/doc.pdf>; rel="canonical"'.format(b))], pdf, 0
    if path == "/x/empty-200":
        return 200, [], b"", 0

    # --- HTML ---
    if path == "/h/entity-title":
        return simple("A &amp; B &lt;C&gt; &#x3042;") + (0,)
    if path == "/h/tag-in-title":
        return simple("foo <b>bar</b>") + (0,)
    if path == "/h/desc-upper":
        return simple("大文字", desc=None, head_extra='<meta name="Description" content="大文字の説明">') + (0,)
    if path == "/h/desc-property":
        return simple("プロパティ", desc=None, head_extra=(
            '<meta property="description" content="プロパティ"><meta property="og:description" content="OG">')) + (0,)
    if path == "/h/desc-two":
        return simple("説明2個", desc=None, head_extra=(
            '<meta name="description" content="一つ目"><meta name="description" content="二つ目">')) + (0,)
    if path == "/h/canonical-two-same":
        tag = '<link rel="canonical" href="{}/h/canonical-two-same">'.format(b)
        return simple("同じ2個", head_extra=tag + tag) + (0,)
    if path == "/h/canonical-two-diff":
        return simple("異なる2個", head_extra=(
            '<link rel="canonical" href="{0}/h/canonical-two-diff"><link rel="canonical" href="{0}/p/other">'
            .format(b))) + (0,)
    if path == "/h/canonical-ws":
        return simple("空白", head_extra='<link rel="canonical" href="  \n {}/h/canonical-ws \t ">'.format(b)) + (0,)
    if path == "/h/canonical-after-img":
        return simple("画像の後", head_extra=(
            '<img src="/pixel.gif"><link rel="canonical" href="{}/p/other">'.format(b))) + (0,)
    if path == "/h/canonical-noclose-head":
        html = ('<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>閉じなし</title>'
                '<meta name="description" content="説明">'
                '<link rel="canonical" href="{}/h/canonical-noclose-head">'
                "<body>" + STD_MAIN + "</body></html>").format(b)
        return 200, [("Content-Type", HTML_UTF8)], html.encode("utf-8"), 0
    if path == "/h/canonical-vs-header":
        return simple("食い違い", head_extra='<link rel="canonical" href="{}/h/canonical-vs-header">'.format(b),
                      headers=[("Link", '<{}/p/other>; rel="canonical"'.format(b))]) + (0,)
    if path == "/h/xrobots-combo":
        return simple("組み合わせ", headers=[("X-Robots-Tag", "noindex, nofollow")]) + (0,)
    if path == "/h/xrobots-nofollow":
        return simple("nofollowのみ", headers=[("X-Robots-Tag", "nofollow")]) + (0,)
    if path == "/h/no-ct":
        return 200, [], html_page(STD_MAIN, title="ヘッダーなし", desc="説明"), 0
    if path == "/h/wrong-charset-header":
        html = ('<html lang="ja"><head><meta charset="Shift_JIS"><title>シフトJIS①</title>'
                '<meta name="description" content="説明"></head><body>' + STD_MAIN + "</body></html>")
        return 200, [("Content-Type", "text/html; charset=utf-8")], html.encode("cp932"), 0
    if path == "/h/wrong-charset-nometa":
        html = ('<html lang="ja"><head><title>EUCのページ</title>'
                '<meta name="description" content="説明"></head><body>' + STD_MAIN + "</body></html>")
        return 200, [("Content-Type", "text/html; charset=utf-8")], html.encode("euc_jp"), 0
    if path == "/h/meta-wrong":
        html = ('<html lang="ja"><head><meta charset="utf-8"><title>メタが誤り</title>'
                '<meta name="description" content="説明"></head><body>' + STD_MAIN + "</body></html>")
        return 200, [("Content-Type", "text/html")], html.encode("cp932"), 0
    if path == "/h/long-title":
        return simple("あ" * 40000) + (0,)
    if path == "/h/unclosed-title":
        html = ('<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>閉じていない'
                '</head><body>' + STD_MAIN + "</body></html>")
        return 200, [("Content-Type", HTML_UTF8)], html.encode("utf-8"), 0

    if path == "/h/title-two":
        return simple("一つ目のtitle", head_extra="<title>二つ目</title>") + (0,)

    # --- HTTP ---
    if path == "/r/cross-host":
        return 301, [("Location", loc + "/p/english")], b"", 0
    if path == "/r/to-https":
        return 301, [("Location", "https://127.0.0.1:{}/p/x".format(STATE["ssl_port"]))], b"", 0
    if path == "/r/a/b/rel":
        return 302, [("Location", "../../../p/english")], b"", 0
    if path == "/r/no-location":
        return 301, [], b"", 0
    if path == "/r/empty-location":
        return 302, [("Location", "")], b"", 0
    if path == "/r/to-real-https":
        return 301, [("Location", "https://localhost:{}/p/english".format(STATE["https_port"]))], b"", 0
    if path == "/r/to-mailto":
        return 302, [("Location", "mailto:x@example.com")], b"", 0

    # --- 2026-09-26 追加: CSV インジェクション対策と入れ子のサイトマップインデックス ---
    if path == "/sm/formula.xml":
        return 200, XML, urlset([b + p for p in [
            "/h/formula-eq", "/h/formula-minus", "/h/formula-at", "/h/formula-mid", "/h/formula-long"]]), 0
    if path == "/h/formula-eq":
        return simple('=HYPERLINK("http://evil.example/","クリック")', desc="=1+1 の説明") + (0,)
    if path == "/h/formula-minus":
        return simple("-50%オフ セール", desc="+81 から始まる電話番号") + (0,)
    if path == "/h/formula-at":
        return simple("@SUM(A1)", desc="通常の説明") + (0,)
    if path == "/h/formula-mid":
        return simple("価格 = 1,000円", desc="a-b の説明") + (0,)
    if path == "/h/formula-long":
        return simple("=" + "あ" * 40000) + (0,)
    if path == "/sm/idx-flat.xml":
        return 200, XML, sitemapindex([b + "/sitemaps/small.xml"]), 0
    if path == "/sm/idx-top.xml":
        return 200, XML, sitemapindex([b + "/sm/idx-mid.xml", b + "/sm/idx-urls.xml"]), 0
    if path == "/sm/idx-mid.xml":
        return 200, XML, sitemapindex([b + "/sm/idx-leaf.xml", b + "/sm/idx-mid2.xml"]), 0
    if path == "/sm/idx-mid2.xml":
        return 200, XML, sitemapindex([b + "/sm/idx-leaf2.xml"]), 0
    if path == "/sm/idx-leaf.xml":
        return 200, XML, urlset([b + "/p/english"]), 0
    if path == "/sm/idx-leaf2.xml":
        return 200, XML, urlset([b + "/p/no-title"]), 0
    if path == "/sm/idx-urls.xml":
        return 200, XML, urlset([b + "/p/two-h1"]), 0

    # --- 2026-09-26 追加 2: 内部アドレス・別のホスト・429 / 503・サイトマップの大きさ ---
    port = STATE["port"]
    if path.startswith("/t/429/"):
        return 429, [("Content-Type", HTML_UTF8)], b"too many requests", 0
    if path.startswith("/t/503/"):
        return 503, [("Content-Type", HTML_UTF8)], b"service unavailable", 0
    if path == "/t/ra-secs":
        return 503, [("Retry-After", "2")], b"", 0
    if path == "/t/ra-date":  # 1 秒単位の HTTP 日付なので、待つ時間は 2〜3 秒
        return 429, [("Retry-After", email.utils.formatdate(int(time.time()) + 3, usegmt=True))], b"", 0
    if path == "/t/ra-big":
        return 503, [("Retry-After", "100000")], b"", 0
    if path == "/t/ra-far-date":
        return 429, [("Retry-After", email.utils.formatdate(time.time() + 86400, usegmt=True))], b"", 0
    if path == "/t/ra-bad":
        return 503, [("Retry-After", "soon")], b"", 0
    if path == "/sm/throttle-abort.xml":
        return 200, XML, urlset([b + p for p in [
            "/p/english", "/t/429/1", "/t/503/2", "/t/429/3", "/t/503/4", "/t/429/5", "/p/two-h1", "/p/no-title"]]), 0
    if path == "/sm/throttle-reset.xml":
        return 200, XML, urlset([b + p for p in [
            "/t/429/a", "/t/503/b", "/p/english", "/t/429/c", "/t/429/d", "/t/503/e", "/t/429/f", "/p/two-h1"]]), 0
    if path == "/sm/retry-after.xml":
        return 200, XML, urlset([b + p for p in [
            "/t/ra-secs", "/p/english", "/t/ra-date", "/p/two-h1", "/t/ra-bad", "/p/no-title"]]), 0
    if path == "/sm/throttle-index.xml":
        return 200, XML, sitemapindex([b + "/t/503/s{}".format(i) for i in range(1, 6)]
                                      + [b + "/sitemaps/small.xml"]), 0
    if path == "/sm/mixed-hosts.xml":
        return 200, XML, urlset([b + "/p/english", loc + "/p/two-h1", b + "/p/no-title", loc + "/p/no-desc"]), 0
    if path == "/sm/mixed-index.xml":
        return 200, XML, sitemapindex([b + "/sm/idx-leaf.xml", loc + "/sm/idx-leaf2.xml"]), 0
    if path == "/sm/redirect-to-localhost.xml":
        return 301, [("Location", loc + "/sm/mixed-hosts.xml")], b"", 0
    if path == "/sm/redirect-to-v6.xml":
        return 301, [("Location", "http://[::1]:{}/sitemaps/small.xml".format(port))], b"", 0
    if path == "/sm/to-internal.xml":
        return 200, XML, urlset([b + p for p in ["/r/to-localhost", "/r/to-ipv6-loopback", "/r/to-mapped",
                                                 "/p/english"]]), 0
    if path == "/r/to-localhost":
        return 301, [("Location", loc + "/p/english")], b"", 0
    if path == "/r/to-ipv6-loopback":
        return 302, [("Location", "http://[::1]:{}/p/english".format(port))], b"", 0
    if path == "/r/to-mapped":
        return 301, [("Location", "http://[::ffff:127.0.0.1]:{}/p/english".format(port))], b"", 0
    if path == "/sm/idx-internal-child.xml":  # 子サイトマップの1本が内部アドレス（[::1]）
        return 200, XML, sitemapindex([b + "/sm/idx-leaf.xml", "http://[::1]:{}/sm/idx-leaf2.xml".format(port)]), 0
    if path == "/sm/over50k-index.xml":  # loc が 50,001 件のサイトマップインデックス（最初の子だけが実在）
        if "50k-index" not in CACHE:
            CACHE["50k-index"] = sitemapindex([b + "/sm/idx-leaf.xml"]
                                              + [b + "/sm/none/{}.xml".format(i) for i in range(50000)])
        return 200, XML, CACHE["50k-index"], 0
    if path == "/sm/over50k.xml":
        return 200, XML, over50k_sitemap(), 0
    if path == "/sm/over50mb.xml.gz":
        return 200, [("Content-Type", "application/x-gzip")], over50mb_gz()[1], 0

    # --- 2026-09-26 追加 3: URL の認証情報（userinfo） ---
    auth = "http://{}@127.0.0.1:" + str(port)
    if path == "/sm/cred-pages.xml":  # loc に userinfo（パスワード付き・ユーザー名だけ・空・別のホスト・%XX・スキーム省略）
        return 200, XML, urlset([
            auth.format("pageUser:pagePass") + "/p/english",
            auth.format("pageOnlyUser") + "/p/english?only",
            auth.format("") + "/p/english?empty",
            "http://otherUser:otherPass@localhost:{}/p/english".format(port),
            "HTTP://enc%40User:p%3Ass@127.0.0.1:{}/p/english?pct".format(port),
            "//relUser:relPass@127.0.0.1:{}/p/english?rel".format(port),
            b + "/p/two-h1"]), 0
    if path == "/sm/cred-redirects.xml":
        return 200, XML, urlset([b + p for p in ["/r/to-cred", "/r/to-cred-user", "/r/to-cred-empty",
                                                 "/r/to-cred-schemeless", "/r/chain-to-cred", "/p/two-h1"]]), 0
    if path == "/r/to-cred":
        return 301, [("Location", auth.format("redirUser:redirPass") + "/p/english")], b"", 0
    if path == "/r/to-cred-user":
        return 302, [("Location", auth.format("redirOnlyUser") + "/p/english?user")], b"", 0
    if path == "/r/to-cred-empty":
        return 307, [("Location", auth.format("") + "/p/english?empty")], b"", 0
    if path == "/r/to-cred-schemeless":  # スキーム省略の //user:pass@host/（リダイレクト元のスキームで補う）
        return 308, [("Location", "//slUser:slPass@127.0.0.1:{}/p/english?schemeless".format(port))], b"", 0
    if path == "/r/chain-to-cred":
        return 302, [("Location", "/r/to-cred")], b"", 0
    if path == "/sm/redirect-to-cred.xml":  # 最初のサイトマップのリダイレクト先に userinfo
        return 301, [("Location", auth.format("smUser:smPass") + "/sitemaps/small.xml")], b"", 0
    if path == "/sm/idx-cred-child.xml":  # 子サイトマップに userinfo（直接 2 本、リダイレクト先に 1 本）
        return 200, XML, sitemapindex([b + "/sm/idx-leaf.xml", auth.format("childUser:childPass") + "/sm/idx-leaf2.xml",
                                       auth.format("") + "/sm/idx-urls.xml", b + "/sm/child-redirect-cred.xml"]), 0
    if path == "/sm/child-redirect-cred.xml":
        return 301, [("Location", auth.format("crUser:crPass") + "/sm/idx-leaf2.xml")], b"", 0
    return None


def route(path, host=""):
    """(status, headers, body, sleep 秒) を返す。"""
    attacked = attack_route(path, host)
    if attacked is not None:
        return attacked
    b = B()
    closed = "http://127.0.0.1:{}".format(STATE["closed_port"])
    ssl_url = "https://127.0.0.1:{}".format(STATE["ssl_port"])

    # --- robots.txt / サイトマップ ---
    if path == "/robots.txt":
        return 200, [("Content-Type", "text/plain")], b"User-agent: *\nDisallow: /private/\n", 0
    if path == "/sitemap_index.xml":
        return 200, XML, sitemapindex([
            b + "/sitemap_index.xml",            # 自分自身（ループ）
            b + "/sitemaps/nested_index.xml",    # 入れ子のインデックス
            b + "/sitemaps/pages.xml.gz",        # gzip
            b + "/sitemaps/urls.txt",            # テキスト
            b + "/sitemaps/missing.xml",         # 404（失敗を記録して続行）
        ]), 0
    if path == "/sitemaps/nested_index.xml":
        body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<sm:sitemapindex xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">'
                '<sm:sitemap><sm:loc>{0}/sitemaps/pages1.xml</sm:loc></sm:sitemap>'
                '<sm:sitemap><sm:loc>{0}/sitemap_index.xml</sm:loc></sm:sitemap>'
                '</sm:sitemapindex>').format(b)
        return 200, XML, body.encode("utf-8"), 0
    if path == "/sitemaps/pages1.xml":
        urls = [b + p for p in [
            "/p/ja-normal", "/p/no-title", "/p/no-desc", "/p/two-h1", "/p/noindex-meta",
            "/p/noindex-header", "/p/xrobots-otherbot", "/p/none-googlebot", "/p/canonical-mismatch",
            "/p/canonical-relative", "/p/canonical-link-header", "/p/canonical-body",
            "/p/canonical-normalize", "/p/canonical-base", "/p/canonical-slash",
            "/p/%E6%97%A5%E6%9C%AC%E8%AA%9E",
        ]]
        urls[1] = "  " + urls[1] + "\n  "  # loc 前後の空白
        return 200, XML, urlset(urls, ns=False), 0
    if path == "/sitemaps/pages.xml.gz":
        urls = [b + "/redirect/301", b + "/redirect/chain", b + "/redirect/loop-a", b + "/p/not-found",
                b + "/p/server-error", b + "/p/slow", closed + "/p/refused", ssl_url + "/p/ssl",
                b + "/p/ja-normal",  # 重複
                b + "/p/sjis", b + "/p/eucjp"]
        return 200, [("Content-Type", "application/gzip")], gzip.compress(urlset(urls)), 0
    if path == "/sitemaps/urls.txt":
        lines = [b + "/p/english", "", b + "/p/doc.pdf", b + "/private/secret", b + "/redirect/to-private",
                 b + "/p/ja-nolang", b + "/p/mixed", b + "/p/ja-article", b + "/p/ja-body",
                 b + "/p/no-title",  # 重複
                 "# コメント行（無視される）"]
        return 200, [("Content-Type", "text/plain; charset=utf-8")], "\n".join(lines).encode("utf-8"), 0
    if path == "/sitemaps/small.xml":
        return 200, XML, urlset([b + "/p/english", b + "/p/two-h1"]), 0
    if path == "/sitemaps/robots-test.xml":
        return 200, XML, urlset([b + "/private/secret", b + "/redirect/to-private"]), 0
    if path == "/sitemaps/countmode.xml":
        return 200, XML, urlset([b + "/p/english", b + "/p/ja-normal"]), 0
    if path == "/sitemaps/interrupt.xml":
        return 200, XML, urlset([b + p for p in [
            "/p/ja-normal", "/p/no-title", "/p/no-desc", "/p/two-h1", "/p/english", "/p/mixed",
            "/p/ja-article", "/p/ja-body", "/p/ja-nolang", "/p/target-a"]]), 0
    if path == "/sitemaps/dtd.xml":
        body = ('<?xml version="1.0"?>\n<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>\n'
                '<urlset><url><loc>{}/p/english&lol2;</loc></url></urlset>').format(b)
        return 200, XML, body.encode("utf-8"), 0
    if path == "/deep/level1.xml":
        return 200, XML, sitemapindex([b + "/deep/level2.xml"]), 0
    if path == "/deep/level2.xml":
        return 200, XML, sitemapindex([b + "/deep/level3.xml"]), 0
    if path == "/deep/level3.xml":
        return 200, XML, urlset([b + "/p/english"]), 0

    # --- ページ ---
    if path == "/p/ja-normal":
        body = ("<header><nav>メニュー ホーム 会社概要</nav></header>\n"
                "<main>\n<h1>見出し</h1>\n<p>あいうえお　かきくけこ</p>\n<p>ABC def</p>\n"
                '<script>var x = "無視する";</script>\n<style>.a{color:red}</style>\n</main>\n'
                "<footer>フッター</footer>")
        return 200, [("Content-Type", HTML_UTF8)], html_page(
            body, title="日本語の正常なページ｜サンプル",
            desc="これは監査スクリプトのテスト用に作った日本語のページです。",
            head_extra='<link rel="canonical" href="{}/p/ja-normal">'.format(b)), 0
    if path == "/p/no-title":
        return 200, [("Content-Type", HTML_UTF8)], html_page(
            "<svg><title>SVGのタイトル</title></svg>" + STD_MAIN, title=None, desc="説明文あり"), 0
    if path == "/p/no-desc":
        return 200, [("Content-Type", HTML_UTF8)], html_page(
            STD_MAIN, title="  複数の   空白\n  を含む　タイトル  ", desc=None), 0
    if path == "/p/two-h1":
        return simple("h1が2個", body="<main><h1>一</h1><h1>二</h1><p>本文</p></main>") + (0,)
    if path == "/p/noindex-meta":
        return simple("メタ除外", head_extra='<meta name="ROBOTS" content="NoIndex, follow">') + (0,)
    if path == "/p/noindex-header":
        return simple("ヘッダー除外", headers=[("X-Robots-Tag", "googlebot: noindex"),
                                          ("X-Robots-Tag", "max-snippet: 50")]) + (0,)
    if path == "/p/xrobots-otherbot":
        return simple("他社向け", headers=[("X-Robots-Tag", "otherbot: noindex, nofollow"),
                                       ("X-Robots-Tag", "unavailable_after: 25 Jun 2030 15:00:00 PST")]) + (0,)
    if path == "/p/none-googlebot":
        return simple("全拒否", head_extra='<meta name="googlebot" content="none">') + (0,)
    if path == "/p/canonical-mismatch":
        return simple("不一致", head_extra='<link rel="canonical" href="{}/p/other">'.format(b)) + (0,)
    if path == "/p/canonical-relative":
        return simple("相対パス", head_extra='<link rel="Canonical" href="/p/canonical-relative">') + (0,)
    if path == "/p/canonical-link-header":
        link = '<{0}/style.css>; rel="preload"; as="style", <{0}/p/canonical-link-header>; rel="canonical"'.format(b)
        return simple("リンク見出し", headers=[("Link", link)]) + (0,)
    if path == "/p/canonical-body":
        return simple("本文内", body='<link rel="canonical" href="{}/p/elsewhere">'.format(b) + STD_MAIN) + (0,)
    if path == "/p/canonical-normalize":
        return simple("正規化", head_extra='<link rel="canonical x-test" href="HTTP://127.0.0.1:{}/p/canonical-normalize#section">'.format(STATE["port"])) + (0,)
    if path == "/p/canonical-base":
        return simple("基準URL", head_extra='<base href="{}/p/sub/"><link rel="canonical" href="../canonical-base">'.format(b)) + (0,)
    if path == "/p/canonical-slash":
        return simple("末尾スラッシュ", head_extra='<link rel="canonical" href="{}/p/canonical-slash/">'.format(b)) + (0,)
    if path == "/p/日本語":
        return simple("日本語URL", head_extra='<link rel="canonical" href="{}/p/日本語">'.format(b)) + (0,)
    if path == "/redirect/301":
        return 301, [("Location", "/p/target-a")], b"", 0
    if path == "/p/target-a":
        return simple("転送先A", head_extra='<link rel="canonical" href="{}/p/target-a">'.format(b)) + (0,)
    if path == "/redirect/chain":
        return 302, [("Location", b + "/redirect/chain2")], b"", 0
    if path == "/redirect/chain2":
        return 301, [("Location", "/p/target-b")], b"", 0
    if path == "/p/target-b":
        return simple("転送先B", head_extra='<link rel="canonical" href="{}/p/target-b">'.format(b)) + (0,)
    if path == "/redirect/loop-a":
        return 302, [("Location", "/redirect/loop-b")], b"", 0
    if path == "/redirect/loop-b":
        return 302, [("Location", "/redirect/loop-a")], b"", 0
    if path == "/p/server-error":
        return 500, [("Content-Type", HTML_UTF8)], html_page(STD_MAIN, title="サーバーエラー"), 0
    if path == "/p/slow":
        return simple("遅いページ") + (3.0,)
    if path == "/p/sjis":
        html = ('<html lang="ja"><head><meta http-equiv="Content-Type" content="text/html; charset=Shift_JIS">'
                "<title>シフトJISのページ①髙</title>"
                '<meta name="description" content="機種依存文字①と髙を含む説明"></head>'
                "<body><main><h1>見出し</h1><p>本文①</p></main></body></html>")
        return 200, [("Content-Type", "text/html")], html.encode("cp932"), 0
    if path == "/p/eucjp":
        html = ('<html lang="ja"><head><title>EUC-JPのページ①</title>'
                '<meta name="description" content="日本語EUCの説明"></head>'
                "<body><main><h1>見出し</h1><p>本文です</p></main></body></html>")
        return 200, [("Content-Type", "text/html; charset=EUC-JP")], html.encode("euc_jis_2004"), 0
    if path == "/p/english":
        return simple("English Page", desc="An English description.", lang="en",
                      body="<main><h1>Hello World</h1><p>This is a simple English page used for testing the audit script.</p></main>") + (0,)
    if path == "/p/doc.pdf":
        return 200, [("Content-Type", "application/pdf"),
                     ("Link", '<{}/p/doc.pdf>; rel="canonical"'.format(b))], b"%PDF-1.4\n%fake pdf\n", 0
    if path == "/private/secret":
        return simple("秘密") + (0,)
    if path == "/redirect/to-private":
        return 301, [("Location", "/private/landing")], b"", 0
    if path == "/private/landing":
        return simple("非公開の着地") + (0,)
    if path == "/p/ja-nolang":
        return simple("言語指定なし", lang=None,
                      body="<main><h1>見出し</h1><p>日本語の文章です。English words here.</p></main>") + (0,)
    if path == "/p/mixed":
        return simple("Mixed", lang="en",
                      body="<main><h1>Title</h1><p>Mostly English text with a little 日本語 inside the paragraph.</p></main>") + (0,)
    if path == "/p/ja-article":
        return simple("記事ページ", body=("<header>ヘッダー</header><article><h1>記事</h1><p>記事の本文</p>"
                                         "<noscript>ノースクリプト</noscript></article><aside>サイド</aside>")) + (0,)
    if path == "/p/ja-body":
        return simple("本文の抽出", body=("<header>ヘッダー</header><nav>ナビ</nav><div><h1>本体</h1>"
                                         "<p>本文テキスト</p><template>テンプレ</template><svg><text>図</text></svg>"
                                         "<iframe>フレーム</iframe></div><aside>サイド</aside>"
                                         "<footer>フッター</footer><script>x</script>")) + (0,)
    return 404, [("Content-Type", HTML_UTF8)], html_page(STD_MAIN, title="見つかりません"), 0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        pass

    def _log(self, method, path):
        with LOCK:
            STATE["log"].write(json.dumps({"t": time.time(), "method": method, "path": path, "raw": self.path,
                                           "host": self.headers.get("Host", ""),
                                           "ua": self.headers.get("User-Agent", ""),
                                           "auth": self.headers.get("Authorization", ""),
                                           "cookie": self.headers.get("Cookie", "")},
                                          ensure_ascii=False) + "\n")
            STATE["log"].flush()

    def do_HEAD(self):
        self._log("HEAD", urllib.parse.unquote(urllib.parse.urlsplit(self.path).path))
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        split = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(split.path)
        if path == "/__admin/robots":
            STATE["robots_mode"] = urllib.parse.parse_qs(split.query).get("mode", ["complex"])[0]
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self._log("GET", path)
        status, headers, body, sleep = route(path, self.headers.get("Host", ""))
        if sleep:
            time.sleep(sleep)
        try:
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def fake_tls_server(sock):
    """TLS のハンドシェイクに平文の HTTP で即答し、SSL エラーを起こさせる。"""
    while True:
        try:
            conn, _ = sock.accept()
        except OSError:
            return
        try:
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except OSError:
            pass
        finally:
            conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--closed-port", type=int, required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--cert", help="本物の HTTPS サーバー用の証明書（PEM）")
    ap.add_argument("--key", help="同じく秘密鍵（PEM）")
    args = ap.parse_args()
    STATE["closed_port"] = args.closed_port
    STATE["log"] = open(args.log, "a", encoding="utf-8")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    STATE["port"] = httpd.server_address[1]

    tls_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tls_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tls_sock.bind(("127.0.0.1", 0))
    tls_sock.listen(8)
    STATE["ssl_port"] = tls_sock.getsockname()[1]
    threading.Thread(target=fake_tls_server, args=(tls_sock,), daemon=True).start()

    httpsd = None
    if args.cert and args.key:
        import ssl
        httpsd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        httpsd.daemon_threads = True
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(args.cert, args.key)
        httpsd.socket = ctx.wrap_socket(httpsd.socket, server_side=True)
        STATE["https_port"] = httpsd.server_address[1]
        threading.Thread(target=httpsd.serve_forever, daemon=True).start()

    print("PORT {} {} {}".format(STATE["port"], STATE["ssl_port"], STATE["https_port"]), flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        tls_sock.close()


if __name__ == "__main__":
    sys.exit(main())
