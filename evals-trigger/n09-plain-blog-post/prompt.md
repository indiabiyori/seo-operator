---
description: >-
  SEO 目的でないブログ記事の執筆の依頼で、seo-operator が発火しないか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-not-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
会社のブログに載せる、新年のあいさつの記事を書いてください。社員一同で今年も頑張ります、という内容で400字くらいです。
