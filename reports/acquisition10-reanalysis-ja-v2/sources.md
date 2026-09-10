# 出典と主要主張の対応

本文は単独で読めるように執筆した。このファイルは数値・記録を追跡するための補助資料である。入力の由来とSHA256は[source-manifest.json](source-manifest.json)、派生値は[data/results.json](data/results.json)、集計定義は[analysis-policy.json](analysis-policy.json)に収録した。以下の資料番号は本文と対応する。

<a id="s1"></a>
## 資料1　研究目的と条件差

- 主張：同一アプリの承認閾値不整合を対象に、Runのトークンと元要件に対する評価結果を比較する。
- 根拠：[研究設計](source/experiment-design.md)の「問いと範囲」、[通常仕様](source/normal-spec.md)と[不整合仕様](source/anti-spec.md)の「承認ルール（全機能共通）」およびF-006。
- 注意：研究設計文書には過去のモデル構成も記載されている。今回の実モデルは実配布契約と取得記録で確認する。

<a id="s2"></a>
## 資料2　実配布契約と実行単位

- 根拠：[実配布した共通指示](source/run-contract.md)の§0、§1、§3、§6、[固定予定表](source/planned-runs.json)、[取得・保全記録](source/retention.json)。
- 共通指示§1は、矛盾に気づいた箇所・解釈・理由の記録と、無人での判断継続を要求する。全20配布ファイルが同じhashであることをmanifestに記録した。
- 取得経緯とseedの記録：[初回報告](../acquisition10-preserve-first-20260910/report.md)の「取得と検証の状態」。進捗の正本は[Issue #44](https://github.com/fukuda-yuki/sample1/issues/44)。この再分析ではIssueへ新たな書き込みをしていない。

<a id="s3"></a>
## 資料3　集計単位と旧状態

- 根拠：[固定SQLite](source/analysis.sqlite)のruns、case_results、evaluations、[57 IDの台帳](source/requirements-ledger.json)、[58ケースの対応表](source/case-manifest.json)。
- 新しい`recorded_total_tokens`は元の`observed_tokens`そのもの。元の`total_tokens`と`usage_complete`は[data/runs.csv](data/runs.csv)にも別列で残す。
- 元のinvalid 1件・pending 19件を維持。57 IDごとの全必須ケース合格を再構成し、元の合格数と照合する。[計算確認](data/calculation-verification.json)は算術・参照整合の確認であり、新しい評価妥当性の裁定ではない。

<a id="s4"></a>
## 資料4　条件別のトークンと合格率

- 主張：記録済みトークン合計134,321,987、条件別平均7,128,730.4／6,303,468.3、平均合格ID数40.2／25.8。
- 計算：[Run別値](data/runs.csv)を条件ごとに集計した[data/results.json](data/results.json)の`summary`と`metrics`。
- 補助比率：条件内の記録済みトークン合計÷合格ID数合計。Runごとの比の単純平均とは異なる。
- 制限：欠けたusageは補完しない。これらの比率を実消費総量や製品品質の確定値へ拡張しない。

<a id="s5"></a>
## 資料5　ペア差と感度分析

- 根拠：[10ペアの差](data/pairs.csv)、[1ペアずつ除外](data/leave_one_pair_out.csv)、[実行順の補助集計](data/sensitivity.csv)。
- 主張：不整合の合格ID数が少ない8ペア・同数1ペア・多い1ペア。1ペア除外後の平均合格ID差は全10通りで負。
- 制限：元の実行順ブロックを維持しており、結果を見て組み合わせ直していない。事後的な感度分析は時間帯の因果効果を特定しない。

<a id="s6"></a>
## 資料6　機能別の結果

- 根拠：[1,140 Run×IDの合否](data/ids.csv)、[機能別集計](data/features.csv)、[Run×機能の値](data/feature_runs.csv)。
- 分母：各機能のID数×条件内10 Run。20機能の割合を単純平均して正式な57 ID等配点を変更しない。

<a id="s7"></a>
## 資料7　ケース状態と到達範囲

- 根拠：[raw状態](data/raw_case_status.csv)、[到達範囲](data/coverage.csv)、[既存の責任・原因分類](data/classifications.csv)。
- 保存済みの状態は、通常412 pass・116 fail・52 blocked、不整合265 pass・188 fail・127 blocked。各580ケースでerrorは0。
- 業務判定への到達は486／352、前提未成立は50／127。状態列とは別軸で、重複するため合算しない。
- 責任未確定477はresponsibilityがunconfirmedの件数。未到達をすべて実装欠陥へ振り替えない。

<a id="s8"></a>
## 資料8　判断記録・固定コード・閾値パターン

- 根拠：[保存資料の読解記録](source/qualitative.json)、[20件の要約](data/interpretations.csv)。各Runの提出hash、評価UUID、引用元ファイル・行・hashを保持する。
- 記録と固定コード：通常10件は100万円、不整合10件は50万円。不整合10件に矛盾の記録がある。
- 7件のパターンは、T-006-01／03／05 lowerがfail、T-006-02／04／05 upperがpassという6ケースの組合せで機械的に確認する。T-006-06はこのパターンの条件に含めていない。
- 該当Run：anti-001、002、003、006、007、008、009。未該当はanti-004、005、010。
- 制限：提出された理由の記録は内部の認知過程の直接測定ではない。保存ソースを今回実行したとは扱わない。

<a id="s9"></a>
## 資料9　anti-009の二つの保存ケース

- 根拠：[保存通信・メールの索引](source/private-evidence-index.json)。実装Run UUIDは`dc4b4eaa-b0e8-4bf9-abbd-f777a2008ee6`、評価UUIDは`0d517b73-c4e5-46f0-899b-e72979026898`。
- T-011-01：申請58を50万円で提出し部長へ割当。その後の差し戻し要求は403、応答は権限不足を示す。
- T-014-01：別の申請64を50万円で提出し部長へ割当。保存されたメールは部長宛、評価側の期待は課長宛。
- 索引にはtrace ZIP・内部リソース・results JSONLのhashと位置がある。非公開trace、画面、評価コードの本体はこのフォルダに複製していない。
- 制限：この2ケースの記録は、他ケースの原因裁定や機能全体の受入を代替しない。

<a id="s10"></a>
## 資料10　依存関係による事後分類

- 根拠：[全57 IDの分類と保存評価コードへの参照](source/dependency-map.json)、[群別の合格数](data/groups.csv)、[差分](data/group_gaps.csv)。
- 直接3 ID：T-006-01、T-006-03、T-006-05。
- 後続10 ID：T-010-01、T-011-01/02、T-012-01/02、T-013-01/02、T-014-01/02、T-015-01。
- その他44 IDを含め、全57 IDを重複なく分類する。50万円の準備を使っていても、役職に依存しない拒否を調べるT-009-02、T-010-03は後続群へ入れない。
- 計算：直接群30＋後続群60＝90、全体差144、90÷144＝62.5%。これは差の所在であり、AP-001の因果寄与率ではない。

## ARSの適用範囲

academic-research-suite 0.1.28のacademic-paperワークフローから、構成設計、Claim–Evidence–Reasoning、draft_writer、visualizationの役割と執筆・図表の点検基準を使用した。著者が指定した既存資料と承認済み構成に基づく新規文書であり、文献探索、投稿先適合の認定、外部プロバイダーによる査読、プログラムによる引用存在検証は行っていない。レビュー対象はこの日本語研究報告と、その出典・集計の整合である。

完成稿の独立点検は[レビュー記録](reviews/independent-review.md)を参照する。算術の再現、図の表示確認、エージェントによる読解レビューは、それぞれ異なる検証である。
