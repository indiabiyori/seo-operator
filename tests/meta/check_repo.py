#!/usr/bin/env python3
"""リポジトリの整合を確かめる（数秒・パッケージ不要）。

- .claude-plugin/plugin.json と marketplace.json が JSON として読め、プラグイン名がそろっている
- plugin.json の version と、README.md・README.en.md の末尾に書いた版が一致する
- requirements.txt に、依存ごとの下限と、まだ試していないメジャー版を除く上限がある
- references/00-principles.md に写した鉄則が、SKILL.md の鉄則と同じ文面である
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
RULES = [("skills/seo-operator/SKILL.md", "## 鉄則"),
         ("skills/seo-operator/references/00-principles.md", "### 鉄則（SKILL.md と同文）")]


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def numbered_list_after(path, heading):
    """見出しの直後にある番号付きリスト（「1. 」で始まる行の並び）を返す。見出しがなければ None。"""
    lines = read(path).splitlines()
    if heading not in lines:
        return None
    items = []
    for line in lines[lines.index(heading) + 1:]:
        if re.match(r"^\d+\. ", line):
            items.append(line)
        elif items or line.startswith("#"):
            break
    return items


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

    (skill_path, skill_heading), (copy_path, copy_heading) = RULES
    rules = numbered_list_after(skill_path, skill_heading)
    copy = numbered_list_after(copy_path, copy_heading)
    if not rules or copy is None:
        check("00-principles.md の鉄則が SKILL.md と同文", False,
              "見出しが見つからない: {} / {}".format(skill_heading, copy_heading))
    else:
        diff = [str(n + 1) for n in range(max(len(rules), len(copy)))
                if n >= len(rules) or n >= len(copy) or rules[n] != copy[n]]
        check("00-principles.md の鉄則が SKILL.md と同文", not diff,
              "食い違う鉄則: {}（SKILL.md に合わせて写し直す）".format(", ".join(diff)))

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
