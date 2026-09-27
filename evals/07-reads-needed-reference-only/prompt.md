---
# Case 07 (the maintainer's trajectory case): a title / meta description request for one article.
# The routing table in SKILL.md sends it to references/07-on-page.md only.
# Scored (total 4.5): proposals-complete 1 and no-invented-claims 1 (outcome), the read guard
# no-unrelated-reference-reads 1 (arm: both; it passes trivially without the plugin, so it can
# only lower the with-arm score), and three secondary graders at 0.5 (year-not-stale,
# length-targets, per-proposal-counts). Display-only: trigger-seo-operator, reads-07-on-page,
# no-00-principles-read, no-10-gsc-read, no-unrelated-plugin-greps, zenkaku-count-label,
# setup-stall.
# Read-only on purpose: no Bash/Write/Edit, no scaffold, no --allow-tools. The runner puts the
# ungranted Bash in --disallowed-tools, so the with-arm cannot run 07's python counter and its
# （全角換算 n字） counts are estimates; no grader checks their accuracy.
# The product is an electric kettle, not a cosmetic, so no read of 06/01 for 薬機法 is needed.
# The prompt deliberately does not say "not tested" or "never updated": no-invented-claims and
# year-not-stale check that the answer infers both from the facts given (07: ページにない内容で
# 釣らない / 年は毎年内容を更新する運用がある場合だけ入れる).
# Calendar: written for runs in 2026 (article published 2026-02). From 2027 on, move the year in
# the current title, the publish date and every grader's context forward together.
# Calibration: the labelled answers are in calibration/07-reads-needed-reference-only/, including
# real Opus answers from the pilot and full runs. The llm rubrics are tuned against the runner's
# own judge (claude-sonnet-5, no thinking, one-word verdict, 3 votes). Keep each rubric's closing
# PASS-default sentence: without it the judge leaned FAIL on long answers in 07's output format.
# Re-run evals/calibration/check.py for a grader after any edit to it.
description: >-
  1記事の title と meta description の改善案を頼まれたとき、振り分け表どおり references/07-on-page.md だけを読み、そのまま使える案を出すかを見る（読み込みの範囲を測るケース）。スコアに入るのは、案の中身（proposals-complete、no-invented-claims）、07-on-page.md 以外の references と templates・scripts を読まないこと（no-unrelated-reference-reads、arm: both なのでスキルなしのアームは必ず通る）、副次の3本（year-not-stale、length-targets、per-proposal-counts、各0.5）。per-proposal-counts は SKILL.md の書式ルール（案に文字数を添える）なので、Δ の一部はこのルールを守ったかどうかの差になる。00-principles.md と 10-gsc-growth.md の読み込みも点に入る（どちらを読んだかは no-00-principles-read と no-10-gsc-read に表示だけで出る）。記事の公開年（2026年）を前提にしているので、2027年になったらプロンプトと各グレーダーの年をそろえて進める。
tags: [should-fire, uplift, setup-gating-sensitive, trajectory, on-page]
expected_outcome: >-
  Skill ツールで seo-operator を呼び、references/07-on-page.md を読む。ほかの references・templates・scripts は読まない。title 3案と meta description 3案を出し、各案に文字数を添える。title は「電気ケトル」を前半に置き、記事にない事実（実機での検証、ランキング、メーカー名、記事にない数字）を足さない。【2026年最新】のような年の表示は、毎年更新する運用があるときだけ残す。
max_turns: 20
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
家電の比較ブログを個人で運営しています。下の記事のタイトルとメタディスクリプションを、SEOを意識して見直したいです。今回はこの1記事のタイトルとディスクリプションだけで、本文は変えません。改善案をそれぞれ3つずつお願いします。

狙っているキーワード: 電気ケトル おすすめ

今のタイトル:
電気ケトルのおすすめ20選｜安いモデルから高級モデルまで徹底比較【2026年最新】

今のメタディスクリプション:
電気ケトルのおすすめを紹介します。安いモデルから高級モデルまで人気の電気ケトルを徹底比較しました。電気ケトル選びに迷っている方はぜひ参考にしてください。

記事の中身はこんな感じです。
- 紹介しているのは20機種で、価格帯で3つに分けています（3,000円未満が8機種、3,000〜8,000円が7機種、8,000円以上が5機種）。
- 最初に選び方として、容量・温度調節・安全機能（空だき防止、転倒時の湯もれ防止）の3つのポイントを説明しています。
- 20機種すべての比較表があります。項目は価格、容量、沸騰までの時間（メーカー公表値）、温度調節の有無、保温の有無の5つです。
- メーカーの公式サイトに載っている仕様をまとめた記事です。
- 公開は2026年2月です。
- サイト名はタイトルに付けない設定にしています。
