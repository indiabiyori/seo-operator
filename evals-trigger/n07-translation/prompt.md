---
description: >-
  SEO 目的でない翻訳の依頼で、seo-operator が発火しないか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-not-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
次の商品説明を、自然な英語に訳してください。

職人が一つずつ手作業で仕上げた、本革のキーケースです。使い込むほどに色が深まり、手になじんでいきます。
