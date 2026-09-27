#!/usr/bin/env python3
"""GSC 系スクリプトの手早い確認（数秒）。EXPECTED.md の手計算の値と出力を照合する。

使い方: python3 check_gsc.py
  対象のスキルは環境変数 SEO_OPERATOR_DIR で切り替える（既定はこのリポジトリの skills/seo-operator）。
"""
import csv
import io
import os
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gsc")
# 既定の対象は、このリポジトリの skills/seo-operator（環境変数 SEO_OPERATOR_DIR で切り替える）
REPO_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "skills", "seo-operator")
SKILL = os.environ.get("SEO_OPERATOR_DIR", REPO_SKILL)
SCRIPTS = os.path.join(SKILL, "scripts")
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def run(script, args):
    proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                          cwd=HERE, capture_output=True, env=ENV)
    if proc.returncode != 0:
        raise SystemExit("{} が終了コード {} で終わりました:\n{}".format(
            script, proc.returncode, proc.stderr.decode("utf-8", "replace")[-800:]))
    return list(csv.DictReader(io.StringIO(proc.stdout.decode("utf-8"))))


def rows(recs, key, *cols):
    return [tuple([r[key]] + [r[c] for c in cols]) for r in recs]


CASES = [
    ("striking 既定（日本語・% 付き CTR）", "striking_distance.py", ["クエリ.csv"], "query", ("est_extra_clicks",),
     [("焙煎 豆 通販", "36.3"), ("業務用 コーヒー 安い", "12.1")]),
    ("striking 英語の列名・比率の CTR", "striking_distance.py", ["Queries_en_ratio.csv"], "query", ("est_extra_clicks",),
     [("焙煎 豆 通販", "36.3"), ("業務用 コーヒー 安い", "12.1")]),
    ("striking cp932", "striking_distance.py", ["クエリ_cp932.csv"], "query", ("est_extra_clicks",),
     [("焙煎 豆 通販", "36.3"), ("業務用 コーヒー 安い", "12.1")]),
    ("striking ブランド名を除外", "striking_distance.py", ["クエリ.csv", "--exclude-regex", "テスト株式会社"], "query",
     ("est_extra_clicks",), [("焙煎 豆 通販", "8.0"), ("業務用 コーヒー 安い", "1.5")]),
    ("low_ctr --min-bucket-rows 2", "low_ctr.py", ["クエリ.csv", "--min-bucket-rows", "2"], "query",
     ("bucket", "expected_ctr", "lost_clicks"), [("コーヒー豆 業務用 価格", "[2,3)", "0.03", "15.0")]),
    ("decay 既定（前年同期比）", "decay.py", ["--current", "ページ_直近3か月.csv", "--previous", "ページ_前年同期.csv"], "page",
     ("clicks_diff", "diagnosis"),
     [("https://example.jp/p1", "-60", "CTR低下（順位・表示回数は維持）"),
      ("https://example.jp/p2", "-60", "順位低下"),
      ("https://example.jp/p3", "-60", "消失（今期のデータなし）"),
      ("https://example.jp/p6", "-30", "複合要因"),
      ("https://example.jp/p4", "-20", "需要減（表示回数が減少・順位は維持）")]),
]


def zip_cases(tmp):
    """gsc/ の CSV を Search Console の zip と同じ名前（クエリ.csv / ページ.csv）で詰め、zip のまま読むケースを返す。"""
    def pack(name, members):
        path = os.path.join(tmp, name)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for arcname, src in members:
                with open(os.path.join(HERE, src), "rb") as f:
                    z.writestr(arcname, f.read())
        return path
    cur = pack("example.jp-Performance-on-Search-2026-09-27.zip",
               [("クエリ.csv", "クエリ.csv"), ("ページ.csv", "ページ_直近3か月.csv")])
    prev = pack("gsc_前年同期.zip", [("クエリ.csv", "クエリ.csv"), ("ページ.csv", "ページ_前年同期.csv")])
    return [
        ("striking zip のまま（auto はクエリ.csv）",) + CASES[0][1:2] + ([cur],) + CASES[0][3:],
        ("decay zip を 2 つ（--key page）",) + CASES[5][1:2]
        + (["--current", cur, "--previous", prev, "--key", "page"],) + CASES[5][3:],
    ]


def main():
    print("対象: {}".format(SCRIPTS))
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        cases = CASES + zip_cases(tmp)
        for name, script, args, key, cols, expected in cases:
            got = rows(run(script, args), key, *cols)
            ok = got == expected
            failed += not ok
            print("[{}] {}".format("PASS" if ok else "FAIL", name))
            if not ok:
                print("  期待: {}\n  実際: {}".format(expected, got))
    print("{}/{} passed".format(len(cases) - failed, len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
