---
# Display-only (arm: with-only): SKILL.md / 07 literal, counts written as （全角換算 29字）
# (half-width characters count as 0.5). Not scored: the baseline fails it only because it does
# not know the house label, which would inflate the delta. per-proposal-counts (scored, 0.5)
# judges the user-visible part with any counting method. This stays as a regression indicator
# for the 07 counting rule in the with-arm.
# Matches 全角換算 followed within 3 non-digit characters by a number and 字 (not 字前後 / 字程度 /
# 字以内 and similar), or a Markdown table row that contains 全角換算 (a column header). A prose
# mention alone, such as 「目安は全角換算30字前後です」, does not match.
type: regex
target: last_message
match: contains
flags: m
weight: 0.5
arm: with-only
---
全角換算[^0-9０-９\n]{0,3}[0-9０-９]{1,3}[ 　]*字(?!前後|程度|以内|以下|以上|まで|くらい|ほど)|^\|[^\n]*全角換算[^\n]*\|[ \t]*$
