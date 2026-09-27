---
# Primary outcome grader (weight 1): the proposals are usable as they are. It checks what the
# user asked for (3 titles, 3 descriptions), that the target query leads the titles, and that the
# descriptions improve on the current one (a concrete fact, no keyword stuffing; 07 steps 3-4).
# Baseline Opus normally passes, so this guards regressions rather than adding uplift.
# Character counts are graded separately by per-proposal-counts (0.5): the user did not ask for
# them and the rule is a SKILL.md literal, so it must not sit inside the primary grader.
# Ends with a PASS default (FAIL only with a quotable broken check): calibrated against the
# runner's one-word judge, which otherwise leaned FAIL on long answers in 07's output format.
type: llm
focus: last_message
weight: 1
---
Context (you cannot see the user's message): a Japanese blog owner asked for 3 improved titles and 3 improved meta descriptions for one article. Target query: 電気ケトル おすすめ. Facts about the article: 20 kettles (20機種) in 3 price bands (3,000円未満, 3,000〜8,000円, 8,000円以上); a buying guide (選び方) with 3 points (容量, 温度調節, 安全機能); a comparison table (比較表) of all 20 models with columns price, capacity, time to boil, temperature control, keep-warm (保温). The current description 「電気ケトルのおすすめを紹介します。安いモデルから高級モデルまで人気の電気ケトルを徹底比較しました。電気ケトル選びに迷っている方はぜひ参考にしてください。」 repeats 電気ケトル 3 times and names no concrete fact.

Candidates: a candidate is a title or meta description that the answer offers the user to use now. Not candidates: quotes of the current title or description; texts marked as examples to avoid (NG, 避ける, 悪い例); variants explicitly conditional on something the article does not have yet (「実機レビューを追記するなら」「毎年更新するなら」); h1, OGP, JSON-LD. Ignore everything outside the candidates: explanations, counts, scores, tables of measures, measurement advice.

Checks:
1. Quantity: at least 3 distinct title candidates and at least 3 distinct meta description candidates (more is fine). Two candidates that differ only in punctuation, bracket type or position, or particles are one candidate.
2. Query in the titles: every title candidate contains 電気ケトル with at most 10 characters before it (a leading 【…】 label does not count). The recommended title (the first title if none is marked) contains おすすめ (オススメ, お勧め also count), and at most one title candidate omits おすすめ.
3. Concrete descriptions: every meta description candidate names at least one article fact: 20機種 or 20選, 価格帯別 or a price band, 比較表 or one of its columns, 選び方 or one of its three points. Pure promotion with no fact (「おすすめを紹介します」「ぜひ参考にしてください」) breaks this check.
4. No keyword stuffing: no candidate contains 電気ケトル 3 or more times.

Answer FAIL only if you can name a check that is broken and quote the candidate that breaks it (for check 1, say which list is short). If you cannot, answer PASS. Explanations, a recommended pick, tables, [要追加: …] placeholders, a closing question, extra candidates, and missing or wrong character counts never break a check.
