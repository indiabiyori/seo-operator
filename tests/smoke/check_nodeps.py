#!/usr/bin/env python3
"""依存パッケージがない環境での挙動の確認（数秒）。

- --help は、requests / beautifulsoup4 / pandas がなくても表示できる
- 引数を付けて実行すると、足りないパッケージ名と用意の方法（uv run の実行例と requirements.txt の場所）を
  表示して、終了コード 2 で終わる
- requirements.txt と、各スクリプトの PEP 723 のメタデータ（uv run が読む依存の宣言）が一致している

パッケージがない環境は python -S（site-packages を読み込まない）で再現する。

使い方: python3 check_nodeps.py [--python PATH]
  対象のスキルは環境変数 SEO_OPERATOR_DIR で切り替える（既定はこのリポジトリの skills/seo-operator）。
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile

# 既定の対象は、このリポジトリの skills/seo-operator（環境変数 SEO_OPERATOR_DIR で切り替える）
REPO_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "skills", "seo-operator")
SKILL = os.path.abspath(os.environ.get("SEO_OPERATOR_DIR", REPO_SKILL))
SCRIPTS = os.path.join(SKILL, "scripts")
REQUIREMENTS = os.path.join(SKILL, "requirements.txt")
REQUIRES_PYTHON = ">=3.9"

# スクリプト名 → (動かすのに必要なパッケージ（pip の名前）, 引数付きで実行するときの引数)
TARGETS = {
    "audit.py": (("requests", "beautifulsoup4"), ["https://example.com/sitemap.xml"]),
    "striking_distance.py": (("pandas",), ["クエリ.csv"]),
    "low_ctr.py": (("pandas",), ["クエリ.csv"]),
    "decay.py": (("pandas",), ["--current", "a.csv", "--previous", "b.csv"]),
}
IMPORT_NAMES = {"requests": "requests", "beautifulsoup4": "bs4", "pandas": "pandas"}

ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
ENV.pop("PYTHONPATH", None)


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, env=ENV)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def command_in(text, prefix):
    """text の中で prefix から始まる行を、シェルと同じ規則で語に分ける（そのまま実行できるかの確認）。"""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(prefix + " "):
            if os.name == "nt":
                words = shlex.split(line, posix=False)
                return [w[1:-1] if len(w) >= 2 and w[0] == w[-1] == '"' else w for w in words]
            return shlex.split(line)
    return None


def packages_hidden(python):
    """python -S で、必要なパッケージがどれも import できないこと（このテストの前提）。"""
    for module in IMPORT_NAMES.values():
        code, _, _ = run([python, "-S", "-c", "import " + module])
        if code == 0:
            return module
    return None


def parse_requirements():
    specs = {}
    with open(REQUIREMENTS, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip().replace(" ", "")
            if line:
                name = re.match(r"[A-Za-z0-9_.-]+", line).group(0).lower()
                specs[name] = line
    return specs


def parse_pep723(path):
    """スクリプト先頭の「# /// script」〜「# ///」を読み、requires-python と dependencies を返す。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"(?m)^# /// script\n((?:#(?: .*)?\n)*?)# ///$", text)
    if not m:
        return None
    body = "\n".join(line[2:] for line in m.group(1).splitlines())
    rp = re.search(r'requires-python\s*=\s*"([^"]+)"', body)
    deps_m = re.search(r"dependencies\s*=\s*\[(.*?)\]", body, re.S)
    deps = [d.replace(" ", "") for d in re.findall(r'"([^"]+)"', deps_m.group(1))] if deps_m else []
    return {"requires-python": rp.group(1) if rp else None, "dependencies": deps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable, help="スクリプトを実行する Python（既定: このテストを動かす Python）")
    python = ap.parse_args().python

    print("対象: {}".format(SCRIPTS))
    visible = packages_hidden(python)
    if visible:
        print("[FAIL] 前提: python -S でも {} を import できるため、パッケージがない環境を再現できない".format(visible))
        print("0/1 passed")
        return 1

    results = []

    for name, (packages, args) in TARGETS.items():
        script = os.path.join(SCRIPTS, name)
        code, out, err = run([python, "-S", script, "--help"])
        ok = code == 0 and out.lstrip().startswith("usage:")
        results.append((ok, "{} --help（パッケージなし）".format(name),
                        "" if ok else "終了コード {}、stderr: {}".format(code, err.strip()[-300:])))

    for name, (packages, args) in TARGETS.items():
        script = os.path.join(SCRIPTS, name)
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run([python, "-S", script] + args, cwd=tmp)
        problems = []
        if code != 2:
            problems.append("終了コードが {}（2 であるべき）".format(code))
        missing = [p for p in packages if p not in err]
        if missing:
            problems.append("足りないパッケージ名がない: {}".format(", ".join(missing)))
        if command_in(err, "uv run") != ["uv", "run", script] + args:
            problems.append("uv run の実行例（スクリプトのパスと元の引数付き）がない、またはそのまま実行できない")
        if command_in(err, "pip install") != ["pip", "install", "-r", REQUIREMENTS]:
            problems.append("requirements.txt を使う pip の実行例がない、またはそのまま実行できない")
        results.append((not problems, "{} 引数付き（パッケージなし）: 用意の方法を表示して終了コード 2".format(name),
                        "; ".join(problems) + ("\n      stderr: " + err.strip()[-300:] if problems else "")))

    if os.path.isfile(REQUIREMENTS):
        reqs = parse_requirements()
        want = sorted({p for packages, _ in TARGETS.values() for p in packages})
        ok = sorted(reqs) == want
        results.append((ok, "requirements.txt に {} がそろっている".format(" / ".join(want)),
                        "" if ok else "実際: {}".format(sorted(reqs))))
    else:
        reqs = {}
        results.append((False, "requirements.txt がある", "見つからない: {}".format(REQUIREMENTS)))

    for name, (packages, _) in TARGETS.items():
        meta = parse_pep723(os.path.join(SCRIPTS, name))
        if meta is None:
            results.append((False, "{} の PEP 723 メタデータ".format(name), "「# /// script」のブロックがない"))
            continue
        problems = []
        if meta["requires-python"] != REQUIRES_PYTHON:
            problems.append("requires-python が {}（{} であるべき）".format(meta["requires-python"], REQUIRES_PYTHON))
        names = sorted(re.match(r"[A-Za-z0-9_.-]+", d).group(0).lower() for d in meta["dependencies"])
        if names != sorted(packages):
            problems.append("dependencies のパッケージが {}（{} であるべき）".format(names, sorted(packages)))
        for dep in meta["dependencies"]:
            key = re.match(r"[A-Za-z0-9_.-]+", dep).group(0).lower()
            if key in reqs and reqs[key] != dep:
                problems.append("{} が requirements.txt（{}）と一致しない".format(dep, reqs[key]))
        results.append((not problems, "{} の PEP 723 メタデータが requirements.txt と一致".format(name), "; ".join(problems)))

    leftovers = [os.path.join(d, x) for d, subdirs, _ in os.walk(SKILL) for x in subdirs if x == "__pycache__"]
    results.append((not leftovers, "スキルのフォルダに __pycache__ が残っていない", ", ".join(leftovers)))

    failed = 0
    for ok, label, detail in results:
        failed += not ok
        print("[{}] {}".format("PASS" if ok else "FAIL", label))
        if not ok and detail:
            print("      " + detail)
    print("{}/{} passed".format(len(results) - failed, len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
