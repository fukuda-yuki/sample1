# PR #21後の実Copilot/Muse受入記録

判定は **提供元応答により停止**。実機受入は未完了。本比較40本・旧停止Runは開始していない。
進捗と後続判断の正本は [Issue #16](https://github.com/fukuda-yuki/sample1/issues/16) と #17〜#19。

## 対象と実施結果

実行ソースはPR #21のマージコミット `e6ee0b8eac8eaadec9c02537347f22118d0b8948`。
開始時のローカルmasterとremote masterは一致。未追跡の `normal/backend/` を保持した。
Issue #16の既存承認に基づき、管理側HTTP診断を新規IDで1回実行した。
これはCopilot経由の実装Runではない。

| 段階 | ID | 結果 | 応答・usage／採点 | 原本・復元証拠 |
|---|---|---|---|---|
| 推論診断 | `2f3549c5-2b57-445f-bb22-189f8cab354d` | 推論要求1回、拒否、exit 1 | 一覧200・exact ID掲載、推論429、usage null | 下記の診断パッケージと復元receipt |
| Copilot smoke | 未発行 | 未開始 | 未取得 | なし |
| normal実装受入 | 未発行 | 未開始 | 未取得／未採点 | なし |
| anti実装受入 | 未発行 | 未開始 | 未取得／未採点 | なし |
| 分析再生成 | 未発行 | 実受入データがなく未実施 | CSV・SQLite未生成 | 診断復元のhash一致とは区別 |
| 本比較 | ― | **未開始** | ― | 開始権限を変更していない |

指定モデルは `muse-spark-1.3-contributor-free` のまま。
開始前に有限枠を記録し、既存 `zen_diagnostic.py` を使用した。一覧1回・推論最大1回、
HTTP操作timeout 30秒・max_output_tokens 128、自動再試行なし。今回の経過は1.218秒。
HTTP 200・モデル一致・非空応答・整合usageの成功条件を変更していない。

## 提供元制限の切り分け

今回の保存済み応答は `code=rate_limit_exceeded`、`type=rate_limit_error`。
messageは上流のrate limitを示し、短い待機後の再試行を案内する。
取得できた識別子は推論応答の `cf-ray=a37e841d7e4f3c79-SJC`。
Retry-After・provider request ID・モデル応答テキスト・usageは返っていない。

- [Zen公式](https://dev.opencode.ai/docs/zen/)で指定ID、Responses endpoint、無料掲載、期間限定での提供、プロンプト／応答の学習利用条件を確認した。
- ログイン済みZen画面を読み取り、`Muse Spark 1.3 Free` が有効、自動チャージが無効、ワークスペース月間上限が未設定という表示を確認した。設定変更は行っていない。
- 画面の表示名とexact API ID、表示ワークスペースと環境変数のAPIキーの対応は独立には確認していない。画面に利用履歴がないことを、要求や消費がなかった証拠にしていない。
- [Goの外部クライアント説明](https://dev.opencode.ai/docs/go/#where-can-i-use-it)と上限値はGoについての情報であり、Zen Muse Contributor Freeの利用許可・上限の証拠へ転用していない。

**確定できること:** この管理側要求に対して提供元が429と上流rate limitの理由を返した。
Copilot・Docker・monitor・評価器が動く前の拒否であり、それらの不具合を今回の429の原因とは扱えない。
既存HTTP診断のendpoint・指定ID・有限要求・応答判定を点検した範囲では、修正を必要とするクライアント不具合の証拠は得られなかった。

**未確認:** 制限がキー／アカウント／モデル共有容量／地域／同時利用のどれに属するか、具体的な上限、解除時刻、Zen Freeでの外部クライアント適用条件。
認証成功やアカウント全体の正常性、単なる時間待ちでの解消までは証明していない。

次に必要なのは提供元側の適用条件・制限の説明または解消を示す証拠であり、現時点でgatewayやバッチを作り替える根拠はない。
UUID変更を解除策にしたり、キー／モデル／クライアントを切り替えたりせず停止した。

## 保全と事前確認

以下はローカルの実在する原本であり、GitHubに添付したファイルではない。

- 診断原本: `C:/Users/mwam0/Documents/ls/sample1/results/zen-live-diagnostics/2f3549c5-2b57-445f-bb22-189f8cab354d/`
- 事前確認・試験ログ: `C:/Users/mwam0/Documents/ls/sample1/results/post21-live-acceptance/`
- 独立保管: `C:/Users/mwam0/ResearchArchives/sample1/packages/zen-diagnostic-2f3549c5-2b57-445f-bb22-189f8cab354d/`
- 別復元先: `C:/Users/mwam0/Documents/ls/sample1/results/post21-live-acceptance/restored-diagnostic/`
- result SHA-256（原本・復元先一致）: `fa3bcd39ddc5e7ebc2f59bd9beebc2ec87aae0bb1fd66fd683937936ff2974a5`
- package SHA-256: `969c2ab946a1fc9915497eef75f6a2652fcba730c978e58b86f97a1b6ad1ee00`
- archive receipt: `receipts/d21401a5-fed4-413b-999b-ce97910f5434.json`、SHA-256 `d3bff183ccdf6896557c08c0587b45c294bacc8de2e246384615bcf50bca05b7`

パッケージには診断manifest/result、実行した診断ソース、事前確認、評価版照合、monitor所在確認、旧原本照合、今回の試験ログを明示的に保存した。
対象11ファイルで実キーの混入がないことを保存前に検査した。資格情報は既存のWindowsユーザー環境変数経路から診断プロセスだけが取得し、秘密ファイルは新設していない。
旧診断 `f19de258-6304-4c11-94e5-4d2a4a48b945` の原本hash、独立保管パッケージとreceiptも再検査し、不変を確認した。

Copilot image `sha256:d70dc026cbd41542004ed010b6f40650be8dd7f7531fd59fd6a3d05ef3e407cb` が存在する。
既存locatorのDBをread-onlyで開き、schemaを読み、importerのhashを記録した。今回の実Runの取り込みではない。
非公開評価器の現行7ファイルは既存校正版 `524ea076349b7d724e46763ff79dd9de95b2d6ce5ab3a60c79896c849b1e92fb` と全hashが一致し、公開58ケースとの一致も確認した。過去の57/57校正を今回の再実行・実提出物採点とは扱わない。

直接HTTP診断を先に行い、429で実装開始前に停止したため、現行Copilot用の完全なimage／評価器復元試験と開始ゲート作成は未実施。
今回の小さな診断パッケージの復元を、その代わりの合格証拠にしない。旧retiredゲートは変更していない。

## 試験と残件

今回実行したローカル回帰: scripts **72 tests**、analysis **25 tests**、要件監査 **57 ID／58ケース・AP-001保護**が成功。
実CLI＋合成provider、実monitor fixture、独立E2E校正は今回は再実行していない。実モデル要求は上記の直接診断1回だけ。
PR #21のGitHub status checks取得結果は空で、CI合格とは報告しない。

実機受入がないため、次の作業は未実施のまま残す。

1. 現行ソース・固定imageの完全復元ゲート、300秒smoke、3600秒ずつのvalidation 2枠。
2. 実Run・gateway・native・DB・提出物・独立評価のID/hash照合と、別復元先でのCSV／SQLite論理再生成。
3. validationとcomparisonの実験IDを保持した受入証拠の接続。現行 `settings_hash()` が実験ID・版を含む不整合は確認済みだが、実受入完了後という修正条件に未到達。
4. exportの評価ディレクトリ参照が復元先へ移せるかの実証。静的な絶対パス参照を確認しただけで、移設再生成の再現試験は未実施。

提出アプリ・runner・gateway・評価器・開始許可は変更していない。後続未実施を隠すための成功フラグやID書換えは行わない。

## 提供元への問い合わせ文案（未送信）

> We are validating GitHub Copilot CLI BYOK through OpenCode Zen with the exact model `muse-spark-1.3-contributor-free`, with no paid fallback. A bounded management HTTP diagnostic used an honest `sample1-research-diagnostic/1` User-Agent and one stable opaque session ID. Model listing returned 200 with the exact ID; the sole Responses request returned 429, `rate_limit_exceeded` / `rate_limit_error`. The response cf-ray was `a37e841d7e4f3c79-SJC`; no Retry-After or provider request ID was supplied. Could you clarify whether Zen Muse Contributor Free permits this external-client usage, which limit produced this rejection, and what supported recovery or reset condition applies? We understand that Go documentation alone does not establish the Zen Free policy. We have stopped inference attempts and have not changed billing, keys, or models.
