# v3の検証記録

本フォルダは再分析と文章・図表の検証であり、研究アプリや評価器を再実行した記録ではない。

- `verification.json`: 60 Run、57 ID/58ケース、SQLとの一致、欠測、原裁定、本文の主要数値、証拠参照。
- `originals-unchanged.json`: 既存レポート390ファイルと固定入力13ファイルのhash。
- `browser-render.json` と `screenshots/`: 日本語本文・6図・表の実表示、画像読み込み、複数画面幅でのはみ出し。
- `replay.json`: 独立保管から復元した入力とコードだけを、元の作業場所にアクセスできないネットワーク遮断Dockerで再計算。33成果物との照合。
- `secret-scan.json`: v3成果物への鍵混入検査。鍵自体やhashは保存しない。
- [`../reviews/independent-review.md`](../reviews/independent-review.md) と [`../reviews/response.md`](../reviews/response.md): 執筆履歴を共有しない完成稿レビューと修正対応。
- `acceptance.json`: 最終本文・HTML・図・再計算・レビューを同じ版へ結び付けた受入記録。

これらの検証が完了しても、元のv6評価のinvalid/pendingは変わらない。製品品質の裁定と、分析成果物の再現性は区別する。
