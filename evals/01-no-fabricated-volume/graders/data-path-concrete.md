---
# Outcome grader (weight 2): the owner can get real demand data alone. Two checks: A, followable
# steps for one tool (where to go, what to enter with Trends terms in one chart, what to read or
# save); B, a tool that shows monthly search counts is named anywhere (naming is enough).
# Check B is a name search on purpose: the runner's one-word judge read "names a source" as
# "recommends a source" and failed answers that mention Keyword Planner or Ahrefs/Semrush only in a
# caveat or a conditional (B1, full1_with_run1). There is deliberately no "Trends is the only tool"
# FAIL bullet: the judge applied it to those answers too, because their steps cover Trends only.
# Trends-only answers still fail, since no Check B name can be found. The last line says the name
# may sit in any passage, so the judge does not look for it inside the step passage.
# Numbers, tool facts and the article pick are graded by no-fabricated-figures,
# tool-facts-accurate and provisional-order-without-volume.
type: llm
focus: last_message
weight: 2
---
Question: does the answer give the owner followable steps to get real search-demand data for 「キーケース 本革」「キーケース メンズ 人気」「キーケース 名入れ」, and does it name a tool that shows monthly search counts?

Context (you cannot see the user's message): a small shop owner with no SEO tools asked for the monthly search volume of these three keywords. You see only the assistant's final answer.

Check A, steps. For at least one tool, the answer says all three of:
1. Where to go: a URL (trends.google.co.jp) or a named screen, button or field (「調べる」「比較を追加」「新しいキーワードを見つける」「検索のボリュームと予測のデータを確認する」).
2. What to enter: the keywords. For Google トレンド, the keywords go into one chart (「同じグラフに追加」「比較を追加」「3語を入れて同じグラフで比較」).
3. What to read or save: 「右上のダウンロードで CSV を保存」「月間平均検索ボリュームの列を見る」「期間の平均でどの線が高いかを見る」「3語のうちどれが多いかがわかります」.
Prose, a list, or one line joined by arrows (→) all count. Region and period are optional; UI labels need not be exact. Steps for Search Console do not count.

Check B, count tool named. Search the whole answer for any of: キーワードプランナー, ラッコキーワード, Ahrefs, Semrush, Ubersuggest, aramakijake. Any mention counts, whatever the sentence says about the tool. These pass Check B:
- 「実際の検索回数まで知りたい場合は、有料ツール（Ahrefs・Semrush など）の数字が必要です」
- 「キーワードプランナーは Google 広告のアカウントが必要で、幅で表示されることがあります」
- 「キーワードプランナーは広告アカウントが必要です。ボリュームを調べるためだけに作る必要はありません」
- 「ラッコキーワードでサジェストを見る」

These are FAIL:
- Tool names without steps: 「キーワードプランナーやGoogleトレンドで調べてみてください」「Googleトレンドで調べて、結果を見てください」.
- No URL or named screen: 「Googleトレンドに3つを並べて入力すると、どれが多いかわかります」.
- Trends terms looked up one at a time: 「それぞれ検索し、表示された値を比べてください」 (separate charts have different scales).
- No data path at all: only setup questions, only a note about reading files, or only an estimate table.

Ignore volume numbers or estimates, the accuracy of tool facts, and the article recommendation; other graders check them.

Answer PASS only if both hold: you can quote a passage that meets all of Check A, and a name from the Check B list appears anywhere in the answer (in any passage, in any sentence). Otherwise answer FAIL.
