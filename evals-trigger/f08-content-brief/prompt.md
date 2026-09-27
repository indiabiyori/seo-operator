---
description: >-
  構成案の依頼で、seo-operator が発火するか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
「エアコン 掃除 自分で」で検索上位を狙う記事を書きたいです。見出しの構成案を作ってもらえますか。
