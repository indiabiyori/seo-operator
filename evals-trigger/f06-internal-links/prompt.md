---
description: >-
  内部リンクの依頼で、seo-operator が発火するか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
自社のオウンドメディアに記事が80本ほどあります。記事どうしの内部リンクをどう張れば、検索での評価が上がりやすいですか。
