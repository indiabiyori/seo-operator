---
description: >-
  インデックスの問題の依頼で、seo-operator が発火するか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
先月サイトをリニューアルしてから、Google にインデックスされないページが増えています。Search Console の「ページ」に「クロール済み - インデックス未登録」がたくさん出ていて困っています。
