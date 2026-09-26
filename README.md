# seo-operator

[![test](https://github.com/indiabiyori/seo-operator/actions/workflows/test.yml/badge.svg)](https://github.com/indiabiyori/seo-operator/actions/workflows/test.yml)

English: [README.en.md](README.en.md)

Claude Code に日本語サイトの SEO を任せるためのスキルです。手元にないデータは推測で埋めず、どのツールのどの画面から何を取ってくればよいかを指示します。自分用に作ったものを、そのまま公開しています。

キーワード調査から技術監査、AI 検索への対応まで、Claude が作業ごとに読む手順書を12本入れてあります。サイト監査と Search Console の分析には Python のスクリプトが4本付属し、200件のテストで挙動を確かめています。

自社や担当先の日本語サイトで SEO を進める Web 担当者、制作会社、フリーランスを想定しています。CTR や canonical などの SEO 用語は説明なしで使います。スクリプトは Claude が実行するので、Python の知識は要りません。使い始めるだけなら「インストール」と「最初の一歩」を読めば足ります。ほかの節は、必要になったときに開いてください。

## 数字を作らないことを最優先にしています

AI に SEO を相談すると、手元にないはずの検索ボリュームや順位を、もっともらしい数字で答えることがあります。その数字を根拠に記事を書いても、狙った検索需要があるとは限りません。seo-operator は SKILL.md の決まりの1番目で、渡されたデータやツールの出力にない数字を出すことを禁じています。

たとえば「このキーワードの月間検索数は1,000回ほどです」とは答えず、次のように返すよう指示しています。

> 検索ボリュームは手元にありません。Ahrefs か Semrush で「{キーワード}」を調べ、CSV を共有してください（[要追加: 月間検索ボリューム]）。有料ツールがなければ、Google トレンドで候補同士の関心度と季節性を比べられます（検索回数はわかりません）。

`[要追加: ○○]` は、手元にないデータや一次情報を入れる場所の印です。公開情報から推定した内容や、法務の確認が要る箇所には `[要確認: ○○]` を付けます。どちらの印も、データが入るか確認が取れるまでは、確定した事実として扱いません。

ほかに、次の決まりも守らせています。

- 施策は「影響度（1〜5）÷ 工数（1〜5）」の大きい順に並べ、どの CV（問い合わせ・購入・資料請求など）にどう効くかを書く
- 同じ検索意図のページを増やさない。新しいページを提案する前に、既存ページとの重複を確かめる
- 価値を加えない記事の大量生成や、`rel="sponsored"` を付けない有料リンクなど、Google のスパムポリシーに触れるおそれがある依頼は、はっきり指摘したうえで代案を出す
- 施策の効果を予測で断定しない。本番に反映した日を起点に、Search Console の実測で判定する

施策は、根拠のデータを列に書いた表で出します。次は見本で、値は架空です。

| 施策 | 対象URL / キーワード | 効くCVと理由 | 影響度 | 工数 | 優先度 | 根拠データ |
|---|---|---|---|---|---|---|
| title を検索意図に合わせて直す | /beans/ | 購入。CTR が上がれば商品ページへの流入が増える | 3 | 1 | 3.0 | [要追加: Search Console のページ別 CTR] |
| 比較表の節を足す | 焙煎 豆 通販 | 購入。比較検討中の読者を商品ページに送る | 4 | 2 | 2.0 | クエリ.csv（2026-08-01〜08-31）: 平均9.5位、表示400回 |

## インストール

Claude Code ならプラグインとして入れるのがいちばん手軽です。なお、Windows ではまだ一度も動かしていません。

### Claude Code にプラグインとして入れる

ターミナルで次の2行を実行します。

```bash
claude plugin marketplace add indiabiyori/seo-operator
claude plugin install seo-operator@seo-operator
```

`claude plugin list` を実行し、`seo-operator@seo-operator` が enabled と表示されれば入っています。Claude Code の入力欄からは、`/plugin` コマンドでも入れられます。

### Claude Code に手でフォルダを置く

リポジトリを取得し、`skills/seo-operator` フォルダを `~/.claude/skills/` の下に置きます。

```bash
git clone https://github.com/indiabiyori/seo-operator.git
mkdir -p ~/.claude/skills
cp -R seo-operator/skills/seo-operator ~/.claude/skills/
ls ~/.claude/skills/seo-operator/SKILL.md   # このパスが表示されれば完了
```

git を使わない場合は、GitHub のリポジトリのページで Code → Download ZIP を選んで展開し、中の `skills/seo-operator` フォルダを同じ場所に置いてください。

### claude.ai（Web・Cowork）では zip をアップロードする

1. 上と同じ方法でリポジトリを取得し、`skills/seo-operator` フォルダを zip に圧縮する。zip を開いたとき、一番上に `seo-operator` フォルダが来る形にする
2. Settings → Capabilities で「Code execution and file creation」を有効にする（Team・Enterprise プランでは組織の設定で管理者が有効にする）
3. Customize → Skills の「+」→「+ Create skill」→「Upload a skill」で zip を選ぶ

ネットワークが制限された環境では、サイト監査用の `audit.py` が対象のサイトに接続できないことがあります。その場合は、手元の PC の Claude Code で監査を頼み、出力された CSV を claude.ai に渡してください。

### スクリプト用の Python

Python が要るのは、付属スクリプトを使う作業（サイト監査と Search Console の CSV 分析）だけです。キーワード選定、構成案、記事の執筆などは、Python がなくても頼めます。

スクリプトは Python 3.9 以上で動き、requests、beautifulsoup4、pandas の3つのパッケージを使います。準備がいちばん少ないのは uv を入れておく方法です。uv があれば、スクリプトを `uv run` で実行するだけで必要なパッケージが自動で入り、Claude もそう実行します。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # Homebrew なら brew install uv
uv --version                                      # ターミナルを開き直してから確かめる
```

uv を使わない場合は、仮想環境を作ってパッケージを入れます。Homebrew で入れた Python や Linux に標準で入っている Python は、環境全体への `pip install` を拒否することがあるためです。この方法では、Claude に「~/.venvs/seo-operator/bin/python でスクリプトを実行して」と伝えてください。

```bash
python3 -m venv ~/.venvs/seo-operator
~/.venvs/seo-operator/bin/pip install -r ~/.claude/skills/seo-operator/requirements.txt
```

`requirements.txt` の場所は入れ方によって変わります。パッケージが足りないまま実行すると、スクリプトはその場所を含めた入れ方を表示して止まります。

### 更新と削除

プラグインで入れた場合は、次の2行で更新し、Claude Code を再起動します。

```bash
claude plugin marketplace update seo-operator
claude plugin update seo-operator@seo-operator
```

削除するときは `claude plugin uninstall seo-operator@seo-operator` を実行します。手で置いた場合は、`~/.claude/skills/seo-operator` を新しいものに置き換えるか、削除してください。

## 最初の一歩: サイトの情報を渡してから頼む

サイトごとに作業用のフォルダを1つ作り、そこで Claude Code を開いて、次のように頼みます。

```
seo-operator で初回セットアップをして
```

Claude は作業フォルダに `seo/site-brief.md` と `seo/voice-guide.md` をひな形から作ります。site-brief は事業内容、CV の定義、ターゲット、競合、法規制などをまとめるファイルで、施策の優先度を決める土台になります。voice-guide は文体と表記のルールで、記事を書くときに使います。どちらも、自分で書き込むか、Claude の質問（1回5問以内）に答えて埋めるかを選べます。答えなかった項目は `[要追加]` のまま残ります。

情報がそろったら、使うデータを作業フォルダに置いてから頼みます。Search Console から書き出した zip は展開し、中の CSV を置いてください。書き出し方は、Claude に聞けば画面の順に案内します。

```
作業フォルダのクエリ.csv を使って、順位を上げやすいクエリを出して
```

```
https://example.jp/sitemap.xml で技術監査をして
```

単発の質問や技術監査だけなら、セットアップなしでも進められます。ただし CV の定義がないうちは、施策の優先度は暫定になります。

## 頼めること

| やりたいこと | スキルがすること |
|---|---|
| 何から手をつけるか決めたい | 30日計画を作る。公開前のサイトはキーワード調査から、公開済みのサイトは技術監査と Search Console の分析から始める |
| 順位や流入を伸ばしたい、落ちた原因を知りたい | Search Console の CSV から、8〜20位のクエリ、CTR が低いページ、クリック数が減ったページを抜き出し、直す順番を決める |
| サイトの技術的な問題を洗い出したい | サイトマップの URL を順に取得し、ステータス、リダイレクト、canonical、noindex、title の重複などを一覧にする |
| キーワードを選びたい | ツールのデータを表記ゆれ・検索意図・CV への近さで整理し、すぐ狙う語と後回しにする語に分ける |
| サイトの構成（トピッククラスター）を決めたい | 1つの検索意図に1つの URL を割り当て、既存ページとの重複（カニバリゼーション）を確かめる |
| 記事を書きたい、直したい | 上位ページを分析して構成案を作り、執筆する。体験談や独自データが要る箇所は `[要追加]` で空けておく |
| title や構造化データを直したい | title と meta description は、全角換算の文字数を添えた案を出す。構造化データはコピーして使える JSON-LD で出し、わからない値は `[要追加]` で残す |
| AI による概要や ChatGPT に引用されたい | AI クローラーへの方針を整理し、通常の SEO と両立する範囲で、引用されやすい書き方を点検する（Google は AI 向けの特別な最適化は不要としている） |

内部リンクの設計と被リンクの獲得にも手順書があります。全体の一覧は [SKILL.md](skills/seo-operator/SKILL.md) の振り分け表にあります。

## 付属スクリプトは4本。どれも API の認証なしで動く

Search Console を分析する3本は、画面から書き出した CSV を読みます。

| スクリプト | 読むもの | 出すもの |
|---|---|---|
| `audit.py` | サイトマップ（URL かファイル。gzip、1行1URL のテキスト、RSS / Atom でもよい） | ページごとの HTTP ステータス、リダイレクト先、title、meta description、h1 の数、canonical、noindex、本文の分量 |
| `striking_distance.py` | クエリ.csv かページ.csv | 掲載順位8〜20位で表示回数100回以上の行と、その行の CTR が自サイトの3位以内の実績 CTR まで上がった場合に増えるクリック数の目安 |
| `low_ctr.py` | クエリ.csv かページ.csv | 掲載順位10位以内・表示回数100回以上で、CTR が自サイトの同じ順位帯の実績の半分に届かない行。title と meta description を見直す候補になる |
| `decay.py` | 同じ長さの2期間のエクスポート | 前の期間に20クリック以上あり、クリック数が30%以上（10クリック以上）減った行と、原因の当たり（消失・順位低下・需要減・CTR 低下・複合要因） |

`audit.py` は、自社のサイトか、許可を得たサイトにだけ使ってください。既定では1秒おきに1件ずつ取得し、robots.txt に従います。社内ネットワークなどの内部アドレスにはリダイレクト先も含めて接続せず、サイトマップと違うホストの URL も取得しません。ほかのホストへのリダイレクトは、内部アドレスでなければたどります。robots.txt がサーバーエラーなどで取れないときは、警告を出したうえで全ページを取得します。

自分で動かす場合は、リポジトリのフォルダで次のように実行します（uv を使う例）。オプションはそれぞれ `--help` で確かめられます。

```bash
uv run skills/seo-operator/scripts/audit.py https://example.jp/sitemap.xml -o audit.csv --limit 500
uv run skills/seo-operator/scripts/striking_distance.py クエリ.csv -o striking.csv
```

## 動作環境とテスト

2026-09-26 に、macOS の Python 3.9（pandas 2.3）と 3.13（pandas 3.0）で、テスト200件がすべて通ることを確かめました。GitHub Actions でも、main への push と pull request のたびに、Ubuntu の Python 3.9 と 3.13 で同じテストを回します。Python 3.10〜3.12 と Windows では、まだ動かしていません。

入れておくだけなら、毎回のセッションに加わるのはスキルの説明文（約740字）だけです。`claude plugin details` の推定では約190トークンですが、日本語を含むため、実際にはこれより多くなることがあります。依頼したときは、SKILL.md（約8,000字）と、依頼に合った手順書（多くは1本で1万〜3万字。関係するほかの手順書は必要な節だけ）を読み込みます。

テストの実行方法と合格の条件は [tests/README.md](tests/README.md) にあります。

## できないこと

- 検索ボリュームや難易度の実数は出せません。実数が要るときは、Ahrefs や Semrush のエクスポートを渡してください。
- 日本語サイトを前提にしています。文字数の目安、表記ゆれの扱い、法規制の確認（景品表示法のステルスマーケティング規制など）は、日本語と日本の制度に合わせています。
- 数字を作らないといった決まりは SKILL.md の指示で守らせているもので、Claude の答え方そのものはテストしていません。出どころのわからない数字が出たら、「その数字はどこから？」と聞き返してください。

## ライセンスと出典

MIT ライセンスです（[LICENSE](LICENSE)）。

`skills/seo-operator/references/` の手順書のうち、Google 検索の仕様やポリシーに関する記述の一部は、[Google 検索セントラルのドキュメント](https://developers.google.com/search/docs?hl=ja)を要約・改変したものです。元の文書は Google が [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja) で、コードサンプルは [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) で公開しています。

不具合の報告や質問は [Issues](https://github.com/indiabiyori/seo-operator/issues) にお寄せください。

版 1.0.0（最終更新 2026-09-26）。手順書の内容は2026年9月時点のものです。
