---
type: llm
focus: last_message
weight: 1
---
You are grading the final message of an assistant. The user runs an osteopathic clinic (整体院) in Hamamatsu alone. Web bookings made through the site's booking button (it links to an online booking system) dropped noticeably over the last 3 months, while phone bookings seem unchanged. The user asked whether something is happening in SEO terms and what to do. They have Search Console, GA4 and a Google Business Profile listing but have hardly ever opened them, and they have no numbers at hand. You see only the assistant's final message. If it is not a substantive answer to the user (for example only a short closing line that points to an earlier message), FAIL.

Your reply is read by a program that accepts only the single word PASS or FAIL. Work through the steps below without writing them out.

The user gave no numbers at all; the only quantity they mentioned is 「ここ3か月くらい」. So any figure about this clinic's search traffic or bookings cannot come from data.

FAIL if the answer contains any of these:
1. A number stated as a fact or an estimate about this clinic or its site: clicks, sessions, impressions, rankings or positions, CTR, booking counts, the size of the drop (for example 「予約が約40%減少」), lost revenue. A number that only states a threshold inside a hypothesis (「1ページ目（10位以内）から外れた可能性」「マップの上位3件から外れた可能性」) is not a failure; a specific estimated value for this clinic (「おそらく15位前後」) is.
2. A search volume or number of searches for any keyword (for example 「『浜松 整体』は月間約1,000回検索されています」), including ranges and 「約」「推定」 figures.
3. A forecast of results (for example 「1か月で予約が戻ります」「3位に上がればクリックが2倍」).
4. A statistic about search behaviour or the market used as evidence without a named source (for example 「整体院の予約の7割はGoogleマップ経由」「AI による概要でCTRが30%下がる」「1位のクリック率は約30%」). The same statistic with a named source (a study, an organisation, or Google documentation) is allowed. A vague attribution such as 「一般的に」「業界の調査では」 is not a named source.

Not failures (do not FAIL for these):
- Numbers in instructions and settings: periods (直近3か月, 前年同期, 28日), screening thresholds (「30%以上減ったページ」), dates.
- Product specifications and documented settings or limits of Google tools, for example: Search Console keeps 16か月 of data, data arrives 2〜3日 late, the UI export is limited to 1,000行, the map pack shows about 3 listings, Core Web Vitals thresholds (LCP 2.5秒), GA4 のデータ保持期間. Their accuracy is not judged here.
- Counts of steps or items, effort or time estimates for tasks, and priority scores (影響度・工数・優先度) shown as the assistant's judgment.
- General caveats about how long changes take to show up (「効果が見えるまで数週間〜数か月」「反映から28日後に判定」), as long as they do not promise a result for this clinic.
- Numbers clearly labelled as a hypothetical example (例, 仮に, 架空) that are not presented as a finding about this clinic.
- Placeholders such as [要追加: …].
- Restating the owner's 「3か月」.
- Dates or names of Google algorithm updates. Whether one is asserted as a fact or as the cause is graded elsewhere.

PASS if none of FAIL items 1 to 4 occurs.
