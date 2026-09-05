# 実装結果

## 実装済み

- .NET 8 Web API、SQLite EF Core、bcrypt、Cookieセッション
- 開発用リセットと4件の初期ユーザー
- ログイン、ログアウト、ユーザー登録、パスワード変更
- 申請の下書き保存、提出、採番、承認者決定、一覧、検索（主要条件）、詳細権限
- 承認、差し戻し、取り消し、履歴、ダッシュボード
- 通知メールJSON出力、SMTPテスト送信、CSVエクスポート
- React + TypeScript + Vite の日本語UI、Vite API proxy

## 未実装・制限

- 添付ファイルのアップロード・ダウンロードUI/API
- 管理者の設定画面編集UI、ユーザー編集フォームUI（参照は実装）
- 一覧の画面ページネーションUI、詳細画面の専用編集・承認UI
- 仕様上のSMTPリトライキューはローカルファイル出力のため未実装

## 検証

環境確認（.NET SDK 10.0.300-preview、Node.js v24.15.0、npm 11.13.0）を実施しました。`dotnet build backend\backend.csproj` と `npm run build --prefix frontend` は成功しました。Development環境で `/api/dev/reset` とログインAPIのスモークテスト（HTTP 200、`/api/auth/me`確認）も成功しました。
