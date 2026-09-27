#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""LLM グレーダーの判定が、ラベル付きの見本の回答どおりに出るかを確かめる。

判定は `claude plugin eval` の採点役そのものに取らせる。一時フォルダに「見本の回答をファイルとして置き、
グレーダーごとにそのファイルを採点させる」評価スイートを組み立てて実行し、結果を expected.json と照合する。
回答役は OK と返すだけで、採点役の呼び出し方（thinking なし、システムプロンプト、3票）は本番と同じになる。
本番と違うのは、採点役に渡る文面で回答の見出しが `Agent output (last_message):` ではなく
`Agent output (file answer-001.txt):` になる点だけ。claude -p で採点役をまねると thinking が入るなどして
本番と判定がずれるため、この方式にしている。

使い方（リポジトリのルートで）:
  uv run evals/calibration/check.py                      # 全ケース
  uv run evals/calibration/check.py --case 07-reads-needed-reference-only --grader year-not-stale
  uv run evals/calibration/check.py --judge-model claude-sonnet-5 -j 7

見本は calibration/<ケース>/samples/<id>.txt、期待する判定は calibration/<ケース>/expected.json
（{"<id>": {"<グレーダー名>": "PASS" | "FAIL"}}）。見本は連番のファイル名で置くので、id は採点役に見えない。
判定のたびに Claude の利用枠を使う（1件につき3票）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

EVALS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
PROBE_MODEL = "claude-haiku-4-5-20251001"  # 回答役。OK と返すだけ


def load_criteria(case):
    """ケースの llm グレーダーの本文を {名前: 本文} で返す。"""
    case_dir = os.path.join(EVALS, case)
    out = {}
    case_yaml = os.path.join(case_dir, "case.yaml")
    if os.path.exists(case_yaml):
        with open(case_yaml, encoding="utf-8") as f:
            for g in yaml.safe_load(f)["graders"]:
                if g["type"] == "llm":
                    out[g["name"]] = g["criteria"]
        return out
    gdir = os.path.join(case_dir, "graders")
    for name in sorted(os.listdir(gdir)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(gdir, name), encoding="utf-8-sig") as f:  # ランナーと同じく BOM を外す
            text = f.read()
        m = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n?", text)
        if not m:
            continue
        front = yaml.safe_load(m.group(1)) or {}
        if front.get("type") == "llm":
            # ランナーと同じく、frontmatter の name と criteria を本文とファイル名より優先する
            out[front.get("name", name[:-3])] = front.get("criteria") or text[m.end():].strip()
    return out


def build_probe(root, cases, grader_filter):
    """採点だけを行う評価スイートを root に組み立て、{(ケース, 採点名): (見本id, グレーダー, 期待)} を返す。"""
    os.makedirs(os.path.join(root, ".claude-plugin"))
    with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "seo-operator-calibration-probe", "version": "0.0.0"}, f)
    index = {}
    for case in cases:
        criteria = load_criteria(case)
        with open(os.path.join(HERE, case, "expected.json"), encoding="utf-8") as f:
            expected = json.load(f)
        cdir = os.path.join(root, "evals", case)
        os.makedirs(os.path.join(cdir, "fixtures"))
        graders = []
        for n, (sid, labels) in enumerate(sorted(expected.items()), 1):
            fname = "answer-{:03d}.txt".format(n)
            shutil.copy(os.path.join(HERE, case, "samples", sid + ".txt"), os.path.join(cdir, "fixtures", fname))
            for grader, want in sorted(labels.items()):
                if grader_filter and grader != grader_filter:
                    continue
                if grader not in criteria:
                    sys.exit("{}: グレーダー {} が見つかりません（expected.json の {}）".format(case, grader, sid))
                gname = "a{:03d}--{}".format(n, grader)
                graders.append({"type": "llm", "name": gname, "criteria": criteria[grader],
                                "focus": {"source": "file", "path": fname}})
                index[(case, gname)] = (sid, grader, want)
        if not graders:
            shutil.rmtree(cdir)
            continue
        with open(os.path.join(cdir, "scaffold.sh"), "w", encoding="utf-8") as f:
            f.write('#!/usr/bin/env bash\nset -euo pipefail\ncp "$(dirname "$0")"/fixtures/*.txt .\n')
        case_yaml = {"schema_version": "1.1", "name": case, "context": {"scaffold_script": "scaffold.sh"},
                     "execution": {"prompt": "Reply with the single word OK.", "max_turns": 2,
                                   "timeout_seconds": 120, "allowed_tools": []},
                     "runs": 1, "graders": graders}
        with open(os.path.join(cdir, "case.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(case_yaml, f, allow_unicode=True, sort_keys=False, width=100000)
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", help="ケースのフォルダ名（省略時は全ケース）")
    ap.add_argument("--grader", help="グレーダー名（省略時は全グレーダー）")
    ap.add_argument("--judge-model", default="claude-sonnet-5", help="採点役のモデル（既定: claude-sonnet-5）")
    ap.add_argument("-j", "--jobs", type=int, default=7, help="同時に走らせるケースの数（1〜8、既定: 7）")
    ap.add_argument("--keep", action="store_true", help="組み立てた一時フォルダを残す（中身の確認用）")
    args = ap.parse_args()

    cases = [args.case] if args.case else sorted(
        d for d in os.listdir(HERE) if os.path.exists(os.path.join(HERE, d, "expected.json")))
    root = tempfile.mkdtemp(prefix="seo-operator-calibration-")
    try:
        index = build_probe(root, cases, args.grader)
        out = os.path.join(root, "out")
        print("採点 {} 件（1件につき3票）、採点役 {}".format(len(index), args.judge_model), flush=True)
        proc = subprocess.run(["claude", "plugin", "eval", root, "--ablation", "none", "--scaffold", "--trust-plugin",
                               "--model", PROBE_MODEL, "--judge-model", args.judge_model, "--runs", "1",
                               "-j", str(args.jobs), "--no-publish", "--output-dir", out],
                              capture_output=True, text=True)
        result = os.path.join(out, "aggregate-result.json")
        if not os.path.exists(result):
            sys.exit("claude plugin eval が結果を出しませんでした:\n" + (proc.stdout + proc.stderr)[-2000:])
        with open(result, encoding="utf-8") as f:
            agg = json.load(f)
        failed = split = seen = 0
        for c in agg["cases"]:
            runs = c["arms"]["with"]
            if not runs or runs[0].get("error"):
                print("エラー {}: {}".format(c["name"], runs[0].get("error") if runs else "実行なし"))
                continue
            for g in runs[0]["graders"]:
                key = (c["name"], g["name"])
                if key not in index:
                    continue
                seen += 1
                sid, grader, want = index[key]
                got = "PASS" if g["passed"] else "FAIL"
                votes = "".join("P" if v else "F" for v in (g.get("judgeVotes") or []))
                if "judge votes" not in g.get("explanation", ""):
                    print("エラー {} / {} / {}: {}".format(c["name"], grader, sid, g.get("explanation")))
                    failed += 1
                elif got != want:
                    failed += 1
                    print("NG  {} / {} / {}: 期待 {}、判定 {}（{}）".format(c["name"], grader, sid, want, got, votes))
                elif len(set(votes)) > 1:
                    split += 1
                    print("揺れ {} / {} / {}: {}（{}）".format(c["name"], grader, sid, got, votes))
        if seen < len(index):
            print("結果に出なかった採点が {} 件ある（理由: {}）".format(
                len(index) - seen, agg.get("partialReason") or "下のランナーの出力を参照"))
            for line in (proc.stdout + proc.stderr).splitlines():
                if line.startswith(("✗", "⚠", "Error", "error")):
                    print("  " + line)
            failed += len(index) - seen
        print("{}/{} passed（票が割れたもの {} 件）、費用 ${:.2f}".format(len(index) - failed, len(index), split,
                                                            agg.get("costUsd", 0)))
        sys.exit(1 if failed else 0)
    finally:
        if args.keep:
            print("一時フォルダ: " + root)
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
