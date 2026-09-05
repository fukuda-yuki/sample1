# トークン計測

主指標は対象Runのinput_tokens + output_tokens。金額へ置換しない。
OpenAI Responses の cached_tokens は入力内訳、reasoning_tokens は出力内訳なので再加算しない。
公式根拠: https://developers.openai.com/api/reference/typescript/resources/beta/subresources/responses/methods/create
他providerへこの包含関係を流用しない。provider adapterの実測照合が必要。

`python scripts/normalize_usage.py input.json output.json` は標準化済みの数値イベントだけを集計する。
入力は `events`、全対象の `expected_sessions`、観測完全性の `inventory_complete` を持つJSON。
各イベントは run_id、session_id、event_id、request_id、mode（request/cumulative）、usage を持つ。
収集側は parent_session_id、timestamp、model_id、source、provider を追加して原本を保存する。
usageはinput_tokens/output_tokensとcache/reasoning数値内訳だけを取り出す。
APIキー、HTTP header、プロンプト、内部思考、セッション全文を公開しない。

request modeはrequest IDで重複を除き、失敗/再試行でusageがある呼出しも含める。
cumulative modeはゼロから開始したsessionの累計差分だけを加える。途中から観測したsessionを
完全と宣言しない。累計リセット、順序逆転、同一sessionのmode混在はエラーにする。
親子込み累計は拒否し、各sessionの自己消費分へ分離してから投入する。
重複event IDの異なる内容もエラーにする。

計画・実装・自主テスト・修正・レビュー・子agentを対象とし、提出後採点と研究者の準備は除外する。
未取得usageは欠測、未観測sessionは欠測、呼出し/session一覧を保証できなければ欠測。
この場合total_tokens=null、usage_complete=falseを出し、observed_tokensを参考値として別に保存する。
主図で確定値扱いしない。累計値だけでは呼出し数を復元できず、observed_request_countはrequest
modeで観測した数だけなのでcumulative_sessionsと合わせて解釈する。

合成テストは単一・累計・重複・子agent・失敗再試行・欠測を検証する。
`model_gateway.py` は全upstream開始をstarted.jsonl、完了をevents.jsonlに記録し、
Responses SSEのusageだけを数値原本として保存する。`gateway_usage.py` が両方を照合し、
途中停止した呼出しは欠測にする。実装Run内の子agentは無効だが、gatewayを経た再試行も全て対象。
runnerはCLI stdoutのturn.completed.usage数値だけをnative-usage.jsonへ保存する。
この値との小Run照合ができるまでsource互換性の検証済みとはしない。
API credentialsはgatewayにのみmountし、プロンプト/CLI全文を成果物に保存しない。

2026-09-05の実モデルsmoke（`model-smoke-integration.json`）では、指定のgpt-5.6-luna / xhighで
1呼出しが完了し、gatewayのinput 7,228 + output 5 = 7,233とCLI native usageが一致した。
cached_input_tokens 5,888は入力内訳として再加算しない。reasoning出力はこの小Runでは0だった。
これは接続・基本集計の校正であり、実装Runの成績や長時間Runの完全性の代用ではない。
