# seo-operator のテスト

`seo-operator` スキルのスクリプト4本（audit.py、striking_distance.py、low_ctr.py、decay.py）の回帰テスト。スキル本体（`skills/seo-operator`）とは別に置いてある。claude.ai 用の zip には入らない。プラグインで入れるとリポジトリ全体がコピーされるが、スキルとして読み込まれるのは `skills/seo-operator` だけ。スクリプトを直したら、ここのテストを全件通してから使う。

## 前提

- requests / beautifulsoup4 / pandas が入った Python（仮想環境の中で `pip install -r ../skills/seo-operator/requirements.txt`）
- `openssl`（audit.py の HTTPS のテストで自己署名証明書を作る）
- macOS で `/usr/bin/python3`（Python 3.9。コマンドライン・デベロッパ・ツールに含まれる）があれば、audit.py の構文を 3.9 でも確かめる。なくてもテストは進む

## 実行

このフォルダ（`tests/`）で実行する。

```bash
python3 smoke/check_gsc.py      # 手早い確認。8件・数秒
python3 smoke/check_nodeps.py   # パッケージがない環境での挙動。14件・数秒
python3 gsc/run_tests.py        # GSC 系3本の全テスト。178件・40秒ほど
python3 audit/verify_audit.py   # audit.py の全テスト。43件・1分ほど
python3 meta/check_repo.py      # リポジトリの整合（manifest・版・依存の範囲・鉄則の写し・相対リンク）。12件・数秒
```

最後の行が `8/8 passed`、`14/14 passed`、`合計 178 件、失敗 0 件`、`43/43 passed`、`12/12 passed` なら合格。audit.py のテストは 127.0.0.1 にテスト用のサーバーを立てるため、中で `--allow-private` を付けて実行している。

## パッケージがない環境の確認

`smoke/check_nodeps.py` は、`python -S`（site-packages を読み込まない）でスクリプトを動かし、パッケージが入っていない環境を再現する。確かめるのは次の3点。

- `--help` は、パッケージがなくても表示できる
- 引数を付けて実行すると、足りないパッケージ名と、そのまま実行できる `uv run` と `pip install -r requirements.txt` のコマンドを表示し、終了コード 2 で終わる
- スキルの `requirements.txt` と、各スクリプトの先頭にある PEP 723 の宣言（`uv run` が読む依存の一覧）が一致している

`--python` で別の Python を指定できる。`uv run` で実際にパッケージが入って動くかは、ネットワークが要るためテストに入れていない。スクリプトを直したときは手で確かめる。

```bash
cd smoke/gsc
uv run ../../../skills/seo-operator/scripts/striking_distance.py クエリ.csv   # 2行目の est_extra_clicks が 36.3 なら正常
```

## テストする対象の切り替え

既定では、このリポジトリの `skills/seo-operator` をテストする。インストール済みのスキルなど、別のフォルダを試すときは環境変数で指定する。

```bash
SEO_OPERATOR_DIR=~/.claude/skills/seo-operator python3 gsc/run_tests.py
```

- gsc/run_tests.py は `--scripts <scripts のフォルダ>` でも指定できる。
- audit/verify_audit.py は `AUDIT_PATH=<audit.py のパス>` でも指定できる。
- smoke/check_nodeps.py、gsc/run_tests.py、audit/verify_audit.py は、対象のスキルのフォルダに `__pycache__` が残っていないかまで確かめる。

## Python 3.9 / pandas 2 での確認

スクリプトは Python 3.9 以上、pandas 2.3 以上の 2.x と 3.x の両方で動くように書いてある。古い環境での動作は、別の仮想環境を作って確かめる。

```bash
/usr/bin/python3 -m venv ~/.venvs/seo39
~/.venvs/seo39/bin/pip install "pandas<3" requests beautifulsoup4
~/.venvs/seo39/bin/python gsc/run_tests.py --python ~/.venvs/seo39/bin/python
~/.venvs/seo39/bin/python audit/verify_audit.py --python ~/.venvs/seo39/bin/python
```

## GSC 系3本の共通部分

striking_distance.py、low_ctr.py、decay.py は、CSV の読み込み・列名の対応・CTR の解析などの「共通部分」を同じコードで持っている（スキルの構成上、共通モジュールにできないため）。正本は `gsc/common_block.py`。

```bash
python3 gsc/sync_common.py --check   # 3本の共通部分が正本と一致するかだけを見る
python3 gsc/sync_common.py           # 正本の内容を3本に書き込む
```

`--check` を付けないと、`SEO_OPERATOR_DIR` の先（既定はこのリポジトリの `skills/seo-operator`）のスクリプトを書き換える。共通部分を直すときは、1本だけを直さずに正本を直してから同期する。gsc/run_tests.py は `--check` をテストの1件として実行する。

## 実行すると作られるもの

`audit/out/`、`gsc/data/`、`gsc/results_*.json` は実行のたびに作り直される。消してかまわない（`.gitignore` で除外済み）。

## 未確認のこと

- Windows では実行していない。audit.py のテストは POSIX のシグナル（Ctrl+C の中断の再現）と `openssl` を前提にしている部分がある。
- 最後に全件合格を確かめた環境: macOS の Python 3.13.13 / pandas 3.0.6、Python 3.9.6 と 3.9.25 / pandas 2.3.3（すべて 2026-09-28）。3.9 の仮想環境は `uv venv --python 3.9` でも作れる。GitHub Actions では、main への push と pull request のたびに、Ubuntu の Python 3.9 と 3.13 で全件を回す。Python 3.9 では、requirements.txt の下限の版（`uv pip install --resolution lowest-direct`）でも回す。
