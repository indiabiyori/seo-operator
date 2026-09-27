#!/usr/bin/env python3
"""リポジトリの整合を確かめる（数秒・パッケージ不要）。

- .claude-plugin/plugin.json と marketplace.json が JSON として読め、プラグイン名がそろっている
- plugin.json の version と、README.md・README.en.md の末尾に書いた版が一致する
- requirements.txt に、依存ごとの下限と、まだ試していないメジャー版を除く上限がある
- README.md・README.en.md・tests/README.md・evals/README.md の相対リンクの先が存在する

使い方: python3 tests/meta/check_repo.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = ["README.md", "README.en.md", "tests/README.md", "evals/README.md"]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def main():
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print("{} {}{}".format("ok  " if ok else "NG  ", name, "" if ok else ": " + detail))

    try:
        plugin = json.loads(read(".claude-plugin/plugin.json"))
        market = json.loads(read(".claude-plugin/marketplace.json"))
        check("manifest を JSON として読める", True)
    except (OSError, ValueError) as e:
        check("manifest を JSON として読める", False, str(e))
        return finish(results)

    names = [p.get("name") for p in market.get("plugins", [])]
    check("marketplace.json のプラグイン名が plugin.json と一致する", plugin.get("name") in names,
          "plugin.json={} marketplace={}".format(plugin.get("name"), names))

    version = plugin.get("version", "")
    m_ja = re.search(r"^版 (\S+?)（", read("README.md"), re.M)
    m_en = re.search(r"^Version (\S+) \(", read("README.en.md"), re.M)
    check("README.md の版が plugin.json と一致する", bool(m_ja) and m_ja.group(1) == version,
          "README.md={} plugin.json={}".format(m_ja.group(1) if m_ja else None, version))
    check("README.en.md の版が plugin.json と一致する", bool(m_en) and m_en.group(1) == version,
          "README.en.md={} plugin.json={}".format(m_en.group(1) if m_en else None, version))

    reqs = [ln.strip() for ln in read("skills/seo-operator/requirements.txt").splitlines()
            if ln.strip() and not ln.startswith("#")]
    for req in reqs:
        m = re.match(r"^([A-Za-z0-9_.-]+)>=([0-9.]+),<([0-9]+)$", req)
        ok = bool(m) and int(m.group(3)) > int(m.group(2).split(".")[0])
        check("requirements.txt の {} に下限と上限がある".format(req.split(">")[0].split("<")[0]),
              ok, "書き方の例: pandas>=2.3,<4（上限は、まだ試していないメジャー版）。実際: " + req)

    for doc in DOCS:
        base = os.path.dirname(os.path.join(ROOT, doc))
        missing = []
        for target in LINK.findall(read(doc)):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = target.split("#", 1)[0]
            if path and not os.path.exists(os.path.normpath(os.path.join(base, path))):
                missing.append(target)
        check("{} の相対リンクの先が存在する".format(doc), not missing, ", ".join(missing))

    return finish(results)


def finish(results):
    passed = sum(results)
    print("{}/{} passed".format(passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
