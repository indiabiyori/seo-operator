---
description: >-
  セットアップを頼まれていない相談（1か月の計画）では、seo/ にファイルを作らず、暫定の計画をその場で出すかを見る（v1.2.0 の「セットアップは頼まれたときだけ」の、頼まれていない側）。書き込みを許可しないとファイルを作る振る舞いを測れないので、実行時に --allow-tools Write Bash が要る。setup-stall は表示だけ。
tags: [should-fire, regression-guard, setup, needs-write, setup-gating-sensitive]
expected_outcome: >-
  seo/ にファイルを作らない。1か月の計画を今回の回答で出し、CV の定義や主要ページがわからないので優先度は暫定だと書く。セットアップは、したほうがよい理由を添えて任意の次の一手として提案するにとどめる。
max_turns: 20
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
世田谷で住宅リフォームの会社をやっています。自社サイト（WordPress）からの見積もり依頼を増やしたいのですが、SEOで何から始めればいいでしょうか。1か月くらいの計画を立ててほしいです。
