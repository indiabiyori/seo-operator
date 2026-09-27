# 第三者の著作物とライセンス

English follows the Japanese.

seo-operator 本体は MIT ライセンスで公開している（[LICENSE](LICENSE)）。このリポジトリには、次の第三者の著作物をもとにした部分がある。

## Google 検索セントラルのドキュメント

skills/seo-operator/references/ の手順書のうち、Google 検索の仕様やポリシーに関する記述の一部は、[Google 検索セントラルのドキュメント](https://developers.google.com/search/docs?hl=ja)を日本語で要約し、手順書の流れに合わせて書き直したものである。元の文書は Google が [Creative Commons Attribution 4.0 License（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.ja)で公開している。一部の箇所（スパムポリシー、生成 AI の利用、再クロールの依頼など）には、もとにした個別のページの URL を添えてある。

手順書に載せた構造化データ（JSON-LD）の例のうち、同じドキュメントのコードサンプルをもとにしたものには、[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) が適用される。

## スクリプトが使う Python パッケージ（同梱していない）

skills/seo-operator/scripts/ のスクリプトは、次のパッケージを使う。どれもこのリポジトリには含めておらず、利用者の環境に入れて使う（requirements.txt または各スクリプトの先頭の宣言）。

| パッケージ | ライセンス |
|---|---|
| requests | Apache License 2.0 |
| beautifulsoup4 | MIT License |
| pandas | BSD 3-Clause License |

---

## Third-party notices (English)

seo-operator itself is released under the MIT License. Parts of the procedure files in skills/seo-operator/references/ summarize and adapt the [Google Search Central documentation](https://developers.google.com/search/docs), which Google publishes under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Some passages (spam policies, generative AI content, recrawl requests and others) also link to the specific source pages. JSON-LD examples based on the documentation's code samples are covered by the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

The scripts depend on requests (Apache License 2.0), beautifulsoup4 (MIT License) and pandas (BSD 3-Clause License). These packages are not bundled; users install them in their own environment.
