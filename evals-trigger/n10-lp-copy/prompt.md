---
description: >-
  SEO 目的でないLP の文案の依頼で、seo-operator が発火しないか。発火は最初のツール呼び出しで決まるので、ターン数を3に絞っている（打ち切られても判定は取れる）。
tags: [should-not-fire, trigger]
max_turns: 3
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
サービスのランディングページのキャッチコピーを、もっと申し込みたくなる言葉に直してください。今は「かんたん、はやい、あんしんの経費精算」です。
