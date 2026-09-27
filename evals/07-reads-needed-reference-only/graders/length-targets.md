---
# Secondary (weight 0.5): SKILL.md literal targets (title 全角30字前後, meta description 全角80〜120字前後),
# graded with a tolerance band on the counts the answer states. Accuracy is not graded: a judge
# cannot count Japanese characters reliably, and this read-only run cannot execute 07's counter.
# The band depends on the counting method, so the same text gets the same verdict whether it is
# counted 全角換算 (half-width = 0.5) or plainly (half-width digits such as 20, 3,000円 or 2026 add
# 2-6 to a plain count). The current title (38 全角換算, 41 by len, checked with python) is an
# anchor the judge can compare against without counting.
type: llm
focus: last_message
weight: 0.5
---
Context (you cannot see the user's message): the current title is 「電気ケトルのおすすめ20選｜安いモデルから高級モデルまで徹底比較【2026年最新】」 (38 characters 全角換算, 41 by plain count). New titles should be around 30 全角換算 and meta descriptions around 80-120.

Candidates: a candidate is a title or meta description that the answer offers the user to use now. The candidate is only the proposed text itself: a character count, list numbering (1., 案1, 第1案) or score next to it is not part of it. Not candidates: quotes of the current title or description; texts the answer marks as examples to avoid (NG, 避ける, 悪い例, 使わない); h1, OGP (og:title, og:description) and JSON-LD. A variant the answer explicitly makes conditional on something the article does not have yet (「実機レビューを追記するなら」「毎年更新するなら」) is not a candidate either: it does not count toward the required number of proposals and it cannot fail any check.

Judge only the candidates and the character count stated for each. Ignore everything else in the answer, including any numbers in it: explanations and reasons, notes, priority or impact scores, tables of measures (施策), and measurement advice (for example 28日後に効果を測る or 現在の38字から29字に短縮).

Use the character count the answer states for each candidate. Do not recount. If a candidate has two counts, use the one labelled 全角換算.

Bands (inclusive):
- A count labelled 全角換算, or described as counting half-width characters as 0.5: title 15-36, meta description 70-130.
- Any other count (文字, 字 or 文字数 without 全角換算): title 15-40, meta description 70-135.

FAIL if the answer offers no title candidate and no meta description candidate at all (for example it only asks setup questions, or the final message is only a closing line).

Otherwise, PASS if every candidate's stated count is within its band and no title candidate is visibly longer than the current title quoted above.

FAIL if any stated count is outside its band, or if any title candidate is visibly longer than the current title, whatever count it states.

A candidate with no stated count: judge it by eye and FAIL only if it is clearly out of range, meaning a title visibly longer than the current title, or a meta description of more than about 150 or fewer than about 55 characters. Otherwise treat it as within the band.
