---
# Display-only diagnostic (arm: with-only), same wording in 01, 02, 03, 06 and 07 except the
# request paragraph (what the user asked for and what counts as work on it). SKILL.md step 1 sends
# strategy, prioritisation and writing requests to the initial setup when seo/site-brief.md is
# missing. When the with-arm score drops and this grader FAILs, the cause is that setup gate, not a
# regression of the case's own behaviour. Two steps on purpose: the one-word judge failed empty
# answers with no setup and answers that did part of the work before asking setup questions when
# both conditions sat in one sentence.
type: llm
focus: last_message
arm: with-only
---
You are grading the final answer of an assistant. You see only that answer, not the user's message. The user asked for 3 improved titles and 3 improved meta descriptions for one article. Work on the request means at least one proposed title or meta description. They did not ask for any initial setup.

Question: did the answer hold the requested work back until an initial setup is done, and deliver none of that work?

Setup means a site brief (for example seo/site-brief.md), a voice / style guide (for example seo/voice-guide.md), or questions about the business (business model, conversion (CV) definition, target customers, key pages, competitors, constraints, tone).

Step 1. Look for a setup gate: a passage that puts setup before the requested work. Examples: 「記入の方法を選んでください。A: ご自身で記入する / B: 私が質問して埋める」, 「回答をいただいたら、案をお出しします」, 「分析に入る前に、まず初回のセットアップをさせてください」.
If there is no setup gate, answer PASS, even if the answer is empty or unhelpful, for example 「以上です。ほかにも気になる点があればお知らせください。」. These are not setup gates: a note that the site brief is missing so priorities are provisional (「seo/site-brief.md がまだないため、影響度はすべて暫定です」); asking for data, files or facts (a Search Console export, keyword volumes, prices to put on a page); an offer to do more (「原稿は続けて私のほうで書けます」).

Step 2. If there is a setup gate, look for work on the request as defined above. A promise to do it later is not work. If the answer contains any of the work, answer PASS, even when setup questions follow it (for example, some of the work comes first, then 「先に初回のセットアップをさせてください。次の3つを教えていただければ、残りをお出しします」).

Answer FAIL only if you can quote a setup gate and the answer contains none of the work on the request. Otherwise answer PASS.
