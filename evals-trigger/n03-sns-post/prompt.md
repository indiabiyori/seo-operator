---
description: >-
  SEO 目的でないSNS 投稿の依頼で、seo-operator が発火しないか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-not-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
来月発売する新作の焼き菓子の告知を、X（旧Twitter）に投稿したいです。140字以内の投稿文を3パターン作ってください。
