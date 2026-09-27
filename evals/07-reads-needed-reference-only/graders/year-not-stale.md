---
# Secondary (weight 0.5): 07-on-page.md 「年は毎年内容を更新する運用がある場合だけ入れる」 and
# 「更新しない『2025年版』は書き換えの原因」. The prompt gives the publish date (2026-02) but not the
# update policy, so a good answer drops the year / 最新, makes it conditional on annual updates, or
# asks. The user-visible failure is a freshness label kept with no word about maintaining it.
type: llm
focus: last_message
weight: 0.5
---
Context (you cannot see the user's message): the article was published in February 2026. The user did not say whether it is or will be updated. Its current title ends with 【2026年最新】.

Candidates: a candidate is a title or meta description that the answer offers the user to use now. The candidate is only the proposed text itself: a character count, list numbering (1., 案1, 第1案) or score next to it is not part of it. Not candidates: quotes of the current title or description; texts the answer marks as examples to avoid (NG, 避ける, 悪い例, 使わない); h1, OGP (og:title, og:description) and JSON-LD. A variant the answer explicitly makes conditional on something the article does not have yet (「実機レビューを追記するなら」「毎年更新するなら」) is not a candidate either: it does not count toward the required number of proposals and it cannot fail any check.

Judge the candidates; read the rest of the answer only to decide (b) below.

A freshness label is a year used as a label or claim (2026年版, 【2026年】, 2026年最新, 26年版 and so on) or one of 最新, 今年, 今年版, 新作, 新モデル. An as-of date that discloses when the specs were collected or the article was published (2026年2月時点, 2026年2月調べ, 2026年2月公開) is not a freshness label, as long as the same candidate does not also say 最新 or 年版.

FAIL if the answer offers no title candidate and no meta description candidate at all (for example it only asks setup questions, or the final message is only a closing line).

Otherwise, PASS if either holds:
(a) No candidate contains a freshness label.
(b) Some candidate contains one, and the answer makes it depend on updating the article: keep it only if the article is updated every year (or refreshed before the label goes stale), drop it if the article will not be updated, or ask the user whether they update the article every year.

FAIL if some candidate contains a freshness label and the answer never ties it to updating the article. An explanation that mentions updating but says the label is fine without it (「更新しなくても2026年中は最新のままで問題ありません」) does not count, and neither does a reason that ignores updating (「年号があるとクリックされやすい」). Dropping only 最新 while keeping the year (「最新は外して【2026年】にするほうが安全です」), with no condition on updating the article every year, does not count either. If the answer does state that condition anywhere (「年を入れるのは、毎年価格や機種を見直す場合だけにしてください」), (b) holds, even when it also says it dropped 最新.

Not failures: mentioning the February 2026 publish date in the explanation; quotes of the current title.
