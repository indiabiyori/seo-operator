---
# Fact check on the tools the answer names (Google Trends is relative; Keyword Planner needs Google Ads;
# Search Console is not overall volume). Ends with a PASS default (FAIL only with a quotable trigger):
# the runner's one-word judge otherwise leaned FAIL on long, correct answers (pilot_with).
# Invented numbers, step detail and the article pick are judged by other graders.
type: llm
focus: last_message
weight: 1
---
Question: does the answer state a key fact about Google トレンド, Google キーワードプランナー or Search Console wrongly, or leave it out?

Context (you cannot see the user's message): a small shop owner asked for the monthly search volume of 「キーケース 本革」「キーケース メンズ 人気」「キーケース 名入れ」 and has no SEO tools. Judge only the tools the answer mentions. A tool the answer does not mention can never cause FAIL.

FAIL triggers:
1. Trends without the relative fact: the answer mentions Google トレンド (Googleトレンド, Google Trends), and no sentence anywhere in the answer says its values are relative, not counts. Relative statements: 相対値, 0〜100, 最大（いちばん多い時点）を100とした値, 回数ではない, 検索回数ではありません, 絶対数ではない. Saying Trends shows which keyword is searched more, or the seasons, is not a relative statement. Example FAIL: 「Googleトレンドなら、それぞれのキーワードがどのくらい検索されているかがわかります」 with no relative statement anywhere.
2. Trends as counts: the answer calls Trends values a number of searches or the monthly volume, e.g. 「Googleトレンドで月間検索数がわかります」.
3. Keyword Planner without Google Ads: the answer mentions キーワードプランナー and never ties it to Google 広告. Ties: a Google 広告 account is needed, it is opened from the Google 広告 screen, or it is a tool for people who run ads (広告を出す人向け). Example FAIL: 「Google キーワードプランナー（無料）で月間平均検索ボリュームを調べられます」 with no mention of Google 広告 anywhere. Also FAIL if it says an ordinary Google account is enough.
4. Search Console as volume: the answer presents Search Console impressions (表示回数) or clicks as the keywords' overall search volume, e.g. 「Search Consoleの表示回数で月間検索数がわかります」.

These count as PASS:
- 「グラフの値は回数ではなく、いちばん多い時点を100とした相対値です。それでも3語のうちどれが多いか、何倍くらい違うかはわかります」 (comparing the three keywords with Trends is fine once the relative fact is stated).
- 「Google 広告のアカウント（無料で作れます）が必要です」 (a free account, but a Google Ads account, so the tie is there).
- 「キーワードプランナーは広告を出す人向けのツールなので、今回は使わなくて大丈夫です」.
- An answer that names none of these tools, for example one that only asks setup questions.

Ignore everything else. Estimated or illustrative numbers (「月に100回しか検索されない言葉でも」), guesses about which keyword is searched more, headings such as 「無料で数字を確かめる方法」, other tools (ラッコキーワード, Ahrefs, Semrush, Ubersuggest), step detail and the article recommendation are graded elsewhere and never cause FAIL here.

Answer FAIL only if you can quote a passage that matches a trigger: for trigger 1 or 3, the passage that mentions the tool, after confirming the required fact appears nowhere in the answer; for trigger 2 or 4, the wrong statement itself. Otherwise answer PASS.
