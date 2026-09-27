---
description: >-
  AI による概要の依頼で、seo-operator が発火するか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Google の検索結果に出る「AI による概要」で、うちの記事が引用されるようにしたいです。何をすればいいですか。
