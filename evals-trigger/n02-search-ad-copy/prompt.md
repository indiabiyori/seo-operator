---
description: >-
  SEO 目的でない検索広告の見出しの依頼で、seo-operator が発火しないか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-not-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Google 広告で検索広告を出します。家事代行サービスの広告見出しを10個と、説明文を4つ考えてください。見出しは全角15字以内、説明文は全角45字以内でお願いします。
