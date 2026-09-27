---
description: >-
  初回セットアップを頼まれたら、作業フォルダに seo/site-brief.md を作って記入を始めるかを見る（v1.2.0 の「セットアップは頼まれたときだけ」の、頼まれた側）。書き込みを許可するので、実行時に --allow-tools Write Bash が要る。スキルなしのアームにはセットアップの考え方がないので、Δ はプラスになる。
tags: [should-fire, uplift, setup, needs-write]
expected_outcome: >-
  テンプレートを作業フォルダの seo/ にコピーして seo/site-brief.md を作り、記入の方法を選んでもらうか、必須項目の質問（1回5問まで）を始める。わかっている事実（会社の説明）は記入し、わからない欄は [要追加] のまま残す。
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
これからこのフォルダで、自社サイトのSEOを継続して進めていきたいです。まず、最初のセットアップをお願いします。

うちは世田谷で住宅リフォームをしている会社で、社員は12人です。キッチン・浴室・トイレの水回りのリフォームが中心で、お問い合わせフォームからの見積もり依頼が主な入口です。
