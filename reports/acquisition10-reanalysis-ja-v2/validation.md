# v2の作成・検証記録

主文書は[日本語レポート](report.md)。本文だけで目的・方法・結果・考察・結論を追える構成とし、6図・7表を配置した。[ブラウザ表示版](report-preview.html)も同じMarkdownから生成した。

本文の文章部分は8,400文字、Markdown全体は11,594文字。考察節は2,979文字で、文章部分の約35.5%を占める。文字数は見出し・表・画像行の除外等により変わるため、計数方法と実測値は[verify.py](verify.py)と[検証結果](checks/verification.json)に残した。

| 受入項目 | 実施結果 | 記録 |
| --- | --- | --- |
| 全件と評価単位 | normal 10・anti 10、1,140 Run×ID、1,160ケース。T-006-05の2ケースを含め、57 IDの合否を再構成して照合 | [計算確認](data/calculation-verification.json) |
| トークンと合格率 | 全20件の元observed_tokensを使用し、合計134,321,987。条件別・Run別・群別の本文表と元データの数値が一致 | [検証結果](checks/verification.json) |
| 原本保全 | 固定入力12、初回レポート・v1の118ファイル、実配布契約20、索引から参照した原本143ファイルのhashを照合。件数は重複を含む別々の確認単位で、合算しない | [入力manifest](source-manifest.json)、[検証結果](checks/verification.json) |
| 再生成 | 入力コピーと生成コードを別ディレクトリへ複製し、データ19ファイル・図とmanifest 13ファイルの計32生成物がバイト単位で一致 | [検証結果](checks/verification.json)のreplay_directory |
| 表示 | 日本語と全6図を目視。本文内の画像6枚・表7個・主要節5個を確認。1100pxと800px幅で横方向のはみ出しなし | [描画確認](checks/browser-render.json)、[目視確認](checks/visual-review.json) |
| 主要主張の追跡 | 本文の資料1〜10から集計・原本索引へ対応。判断記録とコードの引用範囲を照合し、ローカル参照先の存在を確認 | [出典対応表](sources.md)、[検証結果](checks/verification.json) |
| 完成稿の独立レビュー | 執筆履歴を渡さない別コンテキストで実施。Critical 0・Major 0、Minor 2件を反映して追確認 | [独立レビュー](reviews/independent-review.md)、[対応記録](reviews/revision-response.md) |

最終稿SHA256：`780b8c5a93d7c84f19d33ed0a7a386cc4230d8f3f73b11c3137fb377f3739e41`。

集計・表図を作り直す手順は[reproduce.md](reproduce.md)にまとめた。元のusage完全性、invalid 1件・pending 19件の裁定は維持している。今回の検証は報告の数値・保全・表示・論証を対象とし、研究対象アプリの再実行、再採点、品質の有効判定を行ったものではない。新規実装Run、アプリ修正、元データ・既存報告の変更、外部公開は行っていない。
