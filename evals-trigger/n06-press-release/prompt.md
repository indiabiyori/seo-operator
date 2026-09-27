---
description: >-
  SEO 目的でないプレスリリースの依頼で、seo-operator が発火しないか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-not-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
来月から始める法人向けの出張研修サービスについて、報道機関に配るプレスリリースの原稿を書いてください。
