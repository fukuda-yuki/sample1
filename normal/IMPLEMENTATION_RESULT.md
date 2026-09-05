# 実装結果

## 実装済み

- ASP.NET Core .NET 8 Web API、SQLite/EF Core、自動DB作成
- Cookieセッション認証、ログイン・ログアウト・ロック、bcrypt
- 開発用リセットと指定初期4アカウント
- 自己登録、申請種別、下書き・提出、申請番号、承認者決定
- 申請一覧・詳細API、承認・差し戻し・取消、承認履歴
- ダッシュボード集計、ユーザー一覧API、設定取得、SMTPテストmaildrop出力
- React + TypeScript + Viteのログイン、ダッシュボード、申請一覧、新規申請UI

## 未実装・未解決

添付ファイルの保存・ダウンロード、検索条件の全項目とURL反映、ページネーション、CSVエクスポートUI/実装、ユーザー編集UI、パスワード変更UI、設定編集UI、承認確認ダイアログ、厳密な同時採番制御は未実装です。実SMTP、HTTPS、本番運用設定も対象外です。

## 検証

- `backend`: `dotnet restore` 成功、`dotnet build --no-restore` 成功。
- `frontend`: `npm install` 成功、`npm run build` 成功。
- ブラウザ操作、実サーバー起動、API結合テストは未実施です。
