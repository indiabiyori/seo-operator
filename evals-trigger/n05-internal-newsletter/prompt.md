---
description: >-
  SEO 目的でない社内報のコラムの依頼で、seo-operator が発火しないか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-not-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
社内報に載せるコラムを800字くらいで書いてください。テーマは「新入社員に伝えたい、仕事で大切にしていること」です。
