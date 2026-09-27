---
# Secondary (weight 0.5): SKILL.md literal 「title と meta description の案には、必ず文字数を併記する」
# (07 steps 3-5). The user did not ask for counts, so this is kept out of the primary grader.
# Any counting method passes, so the baseline is judged on the same observable outcome; the
# house label 全角換算 is only reported, by zenkaku-count-label (display-only).
type: llm
focus: last_message
weight: 0.5
---
Context (you cannot see the user's message): a Japanese blog owner asked for 3 improved titles and 3 improved meta descriptions for one article about electric kettles (電気ケトル).

Candidates: a candidate is a title or meta description that the answer offers the user to use now. Not candidates: quotes of the current title or description; texts marked as examples to avoid (NG, 避ける, 悪い例); variants explicitly conditional on something the article does not have yet (「実機レビューを追記するなら」「毎年更新するなら」); h1, OGP, JSON-LD.

Check the title candidates and the meta description candidates separately; answers often give counts for the titles (for example in a table column) but none for the descriptions. Every candidate in both lists needs its own character count, tied to that one candidate: on the same line, in the same table row, or in a separate list that names each candidate (「案1: 31字、案2: 29字…」). Any form counts: （全角換算 29字）, (32文字), 32字, 約30字. Do not recount or judge accuracy.

Answer FAIL if the answer offers no title candidate and no meta description candidate at all (for example it only asks setup questions, or the final message is only a closing line). Otherwise, answer FAIL only if you can quote a candidate that has no count of its own, or if the answer gives only a shared statement (「どれも30字前後」「すべて80〜120字に収めています」) instead of a count per candidate. Otherwise answer PASS. Missing counts on texts that are not candidates never matter.
