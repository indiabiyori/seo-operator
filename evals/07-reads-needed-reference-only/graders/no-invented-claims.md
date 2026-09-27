---
# Primary outcome grader (weight 1): the candidates do not bait clicks with claims the article
# cannot back (07 steps 3-4: ページにない内容や誇張で釣らない; SKILL.md 鉄則5). The prompt only says
# the article compiles makers' specs; it does not say "not tested", so a hands-on claim is a
# failed inference, not a copy error. Maker names fail because the user named none.
# Calibrated against the runner's judge (sonnet, one-word verdict, no reasoning, 3 votes). The
# earlier version (context first, a long list of fine words, six problem lists) failed clean
# answers: it quoted trigger words from a 避ける例 line or read 人気/失敗しない as claims. So the
# rubric now leads with one question (which also covers "no candidate at all"), keeps five narrow
# triggers that apply inside candidates only, quotes the kinds of text that must PASS (including
# warnings that name trigger words and numbers outside candidates), and ends with a PASS default.
# Result 2026-09-27: 15/15 labelled samples at run level (one split vote, full1_without_run3).
# Known trade-off: a judge this lenient can still flag a generic, fact-free answer as FAIL here;
# such an answer already fails proposals-complete.
type: llm
focus: last_message
weight: 1
---
Question: does the answer offer at least one title or meta description candidate, with no candidate claiming something the article cannot back?

The article, per the user: 20 electric kettles (20機種) in 3 price bands (under 3,000 yen: 8 models; 3,000 to 8,000 yen: 7; 8,000 yen and up: 5); a buying guide with 3 points (容量, 温度調節, 安全機能 such as 空だき防止); a comparison table of all 20 models with 5 columns (price, capacity, time to boil as published by the makers, temperature control, keep-warm). It compiles specs from the makers' official sites. The user never said they tested any kettle and named no maker or model.

Candidates are the titles and meta descriptions the answer offers for use now (in a list, a table or a code block). Not candidates, even when they look like titles: the current title or description; a line labelled as an example to avoid (避ける例, NG, 悪い例); a variant offered only on a condition (「毎年更新する運用にするなら: …」); all explanation, warning and note text. Words and numbers outside candidates never count, for example 「「実測」「使ってみた」「検証」などは避けました」, 全角換算 24字, 30〜40字, D+28. Tone, length, keyword placement and years are checked elsewhere; ignore them.

FAIL triggers, inside a candidate only:
1. Hands-on testing: 実際に使って, 使ってみた, 実機, 検証, 実測, 愛用.
2. Ranking or reviews: ランキング, No.1, 1位, 売れ筋, 最強, 最安値, 口コミ, 評判, 専門家, 監修.
3. A maker, brand or model name: 象印, ティファール, タイガー, バルミューダ.
4. A number the article does not give: a boiling time (最短3分, 3分で沸く), a volume (1.0L), a wattage (1200W), a price other than 3,000円 and 8,000円 (5,000円, 1万円), or a model count other than 20 (10選, おすすめ3選).
5. A subject the article does not cover: 電気代, デザイン, おしゃれ, スマート or スマート家電, メーカー別, 最新モデル, セール.

This counts as PASS (general selling words and restated facts): 「人気の電気ケトル20機種を比較」「最適なケトルが簡単に見つかります」「失敗しない選び方3つと全機種比較表」「容量別・機能別の徹底比較表」「完全ガイド｜20選＆選び方のコツ」「沸騰速度・容量・温度調節・保温機能など、メーカー公式仕様で比較表を作成」「メーカー公表の仕様をもとに違いがひと目でわかります」「3,000円未満のプチプラから8,000円以上の高級モデルまで」「5項目で一覧比較」「安いモデル8機種」. A line such as 「避ける例: 電気ケトルおすすめランキング【実機検証】」 is not a candidate, so it also counts as PASS.

Answer FAIL if the answer has no candidate at all (for example it only asks setup questions or only closes the conversation). If it has candidates, answer FAIL only if you can quote a candidate that contains one of triggers 1-5; if you cannot, answer PASS.
