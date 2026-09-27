---
type: llm
focus: last_message
weight: 1
---
You are grading the final message of an assistant. The user runs an osteopathic clinic (整体院) in Hamamatsu alone. Web bookings made through the site's booking button (it links to an online booking system) dropped noticeably over the last 3 months, while phone bookings seem unchanged. The user asked whether something is happening in SEO terms and what to do. They have Search Console, GA4 and a Google Business Profile listing but have hardly ever opened them, and they have no numbers at hand. You see only the assistant's final message. If it is not a substantive answer to the user (for example only a short closing line that points to an earlier message), FAIL.

Your reply is read by a program that accepts only the single word PASS or FAIL. Work through the steps below without writing them out.

Question: can a non-technical owner carry out every data request in the answer without further help?

Definitions (apply exactly).

A data kind is one distinct report, export or record set that the owner is asked, in this round, to open a tool, a system or their own records for and take metrics or a listing from. It counts whether the owner is to send it, paste it, screenshot it, read out values or look at the trend themselves, and whether the owner or the web company (制作会社) does the fetching. Opening a report in Search Console, GA4 or Business Profile counts even when it is phrased as a check (「エラーが増えていないか見てください」「減っていないか確認してください」). Optional items asked now (「余裕があれば」「もしあれば」「できれば」) are counted.

Count by report, not by file, tab or date range:
- The same report with several date ranges, tabs or filters is one kind. Search Console 検索パフォーマンス for the last 3 months and for the same period a year earlier, with its クエリ and ページ files, is one kind.
- Different reports are different kinds, even inside one tool. Search Console 検索パフォーマンス and Search Console ページ（インデックス登録） are two kinds. GA4 ランディング ページ and GA4 トラフィック獲得 are two kinds.
- Everything taken from the booking system's admin screen or the clinic's own ledger (booking counts by month or by web and phone, and booking-page views if the system shows them) is one kind, the booking-records kind. A request for booking counts that names no source is this kind.
- GA4 key events and the booking system's own counts are two kinds, unless they are offered as either/or. An either/or offer for the same purpose (「GA4 か予約システムのどちらかで」) is one kind.
- Other kinds, for reference: Googleビジネスプロフィール パフォーマンス; a list or screenshots of the top Google or Maps results for a term; Google Trends or keyword-tool data; 生成 AI パフォーマンス レポート; server or form logs.
- Getting access (logging in, asking the web company for permission) is part of the kind it unlocks, not a kind of its own.

Not data kinds:
- Questions the owner answers from memory or by asking the web company: the site URL, when the drop began, whether anything changed, competitors.
- Self-checks with no metrics to read: a test booking; clicking the booking button or the listing's booking link to see that it works; reviewing the listing's own details (hours, URL, 予約 button); checking whether a 手動による対策 or セキュリティの問題 message exists; URL 検査 of one or a few specific URLs; searching the clinic name or any term (such as 浜松 整体) on Google or Google Maps to note whether and roughly where the clinic appears. Such a search becomes the search-results kind only when the owner is asked to send, paste, screenshot or list the results, the competitors or their positions.
- Verification methods: a source named only inside a hypothesis list or table (a 確かめ方 or 検証データ column, or 「〜で確かめられます」) is not counted, even if it is worded as an instruction. It is counted only when the answer also asks the owner to do it in this round: the same source appears in a request addressed to the owner now (〜してください, 送ってください, まず, 今日, 今週), or the answer tells the owner to carry out the table's checks now (「それぞれ確認してください」).
- Placeholders: a baseline or plan table with [要追加] cells counts only for the rows the owner is asked to fill in now.
- Deferred items: items the answer makes conditional on the first data or a later exchange (「届いたデータを見てから」「結果を見て、必要なら次に」「次回」). Items placed in a schedule (今日, 今週, 来週, Day 1, Day 3) without such a condition are asked now and are counted. Items asked in this round but made conditional only on the result of today's self-checks (「1で問題が見つからなければ」「原因を裏付けたい場合は」) are also asked now and are counted.

Step 1. Using the definitions above, identify the data kinds the answer asks the owner to collect in this round.

Step 2. For each kind, check all four:
a) Source: the tool or record is named (Search Console, GA4, Googleビジネスプロフィール, 予約システムの管理画面, 予約台帳, ...). For booking counts, the clinic's own booking records are implied and satisfy a).
b) Location: at least one screen, report or menu inside the tool, below its top level. Examples: 「検索パフォーマンス」「検索結果」; 「レポート」→「エンゲージメント」→「ランディング ページ」; 「レポート」→「集客」→「トラフィック獲得」; ビジネスプロフィールの「パフォーマンス」. For the clinic's own records, saying what to tally (for example 月別・ネット予約と電話予約別の件数) satisfies b). For a search-results request, naming the search term(s) and how to search (シークレットウィンドウ, ログアウトした状態, スマホ) satisfies b).
c) Period. The drop began about 3 months ago, so time-based data must reach back before it.
   - Search Console 検索パフォーマンス and Googleビジネスプロフィール パフォーマンス must name a period that does so: 前年同期, or the 3 months just before the last 3 months, as a second period (two exports or the 比較 view); one range of about 6 months or longer (過去6か月, 過去12か月, 16か月); or periods defined by the drop (「減る前の3か月と減ってからの3か月」); or the tool's longest available range (「期間を最長にして」「全期間」), which is 6 months or more in both tools. A pair in which both periods fall inside the last ~3 months (for example 「過去28日間と前の期間」) does not qualify, and naming no period does not qualify.
   - Other time-based kinds (GA4, booking counts, logs) pass with any stated period or granularity (月別, 過去6か月), unless the only period named is the last ~3 months or shorter.
d) Hand-over: how to get the data out and what to send or note. Any of these satisfies it: エクスポート or ダウンロード (CSV, Excel, Googleスプレッドシート), a screenshot, or copying specific named numbers. For a kind the owner is asked to read themselves, d) is met when the answer names the metric(s) and the comparison to note or report (for example 「クリック数と表示回数を前年同期と比べ、減っていたら数字を教えてください」); a bare 「推移を見てください」 or 「確認してください」 fails d).

For an either/or offer, the kind passes if at least one alternative meets a) to d).
Do not check whether UI labels are exactly current; any plausible path counts. Fail a check only if a step clearly belongs to another product (for example a GA4 menu given as a Search Console path).

Step 3. Decide.

PASS if every requested kind meets a) to d). PASS also if the answer asks for no data kind at all; another grader fails that case.
FAIL if any requested kind misses one of a) to d). Examples that fail: 「Search Consoleのデータを送ってください」 with no screen or export step; 「GA4の数字を教えてください」; a Search Console request covering only the last 3 months, or only 「過去28日間と前の期間」.

The number of kinds is graded elsewhere. Check every kind the answer asks for, however many there are.
