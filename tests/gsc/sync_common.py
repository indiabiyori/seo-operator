#!/usr/bin/env python3
"""common_block.py の内容を 3 本のスクリプトの「共通部分」に差し込む（テスト用の補助。スキルには含めない）。

使い方: python sync_common.py [--check]
  --check: 差し込まずに、3 本の共通部分が common_block.py と一致するかだけを調べる（不一致なら終了コード 1）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 既定の対象は、このリポジトリの skills/seo-operator（環境変数 SEO_OPERATOR_DIR で切り替える）
REPO_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "skills", "seo-operator")
SCRIPTS = os.path.join(os.environ.get("SEO_OPERATOR_DIR", REPO_SKILL), "scripts")
NAMES = ("striking_distance.py", "low_ctr.py", "decay.py")
RULE = "# " + "-" * 75


def split(text, name):
    lines = text.split("\n")
    start = end = None
    for i, line in enumerate(lines):
        if line.startswith("# 共通部分") and lines[i - 1] == RULE:
            start = i - 1
        if line.startswith(f"# {name} 固有の処理") and lines[i - 1] == RULE:
            end = i - 1
    if start is None or end is None or end <= start:
        raise SystemExit(f"{name}: 共通部分の境界が見つかりません")
    return "\n".join(lines[:start]) + "\n", "\n".join(lines[start:end]) + "\n", "\n".join(lines[end:])


def main():
    check = "--check" in sys.argv[1:]
    with open(os.path.join(HERE, "common_block.py"), encoding="utf-8") as f:
        block = f.read()
    if not block.endswith("\n\n\n"):
        block = block.rstrip("\n") + "\n\n\n"
    bad = []
    for name in NAMES:
        path = os.path.join(SCRIPTS, name)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        head, middle, tail = split(text, name)
        if check:
            if middle != block:
                bad.append(name)
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(head + block + tail)
        print(f"updated {name}")
    if check:
        print("一致しないファイル: " + (", ".join(bad) if bad else "なし"))
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
