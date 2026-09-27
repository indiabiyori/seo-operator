---
description: >-
  多言語サイトの日本語ページの依頼で、seo-operator が発火するか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
英語と日本語の両方のページがある旅行会社のサイトです。日本語ページの検索順位だけが伸び悩んでいます。日本語ページのSEOで何を見直せばいいですか。
