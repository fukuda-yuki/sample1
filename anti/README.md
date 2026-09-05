# 申請管理システム

## 起動

バックエンド:
```powershell
cd backend
dotnet restore
dotnet run
```
`http://localhost:5080` で待受します。初回起動時に `app.db` と `maildrop/` が生成されます。

フロントエンド:
```powershell
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```
`http://localhost:5173` を開きます。Vite が `/api` をバックエンドへ転送します。

初期アカウントは全てパスワード `Password1` です。Development 環境では `POST /api/dev/reset` で初期化できます。

## 自主検証

.NET SDK 10.0.300-preview、Node.js v24.15.0、npm 11.13.0 を確認し、`dotnet build` と `npm run build` を実行します。ブラウザの手動操作は未実施ですが、Development環境でreset/login/me APIのスモークテストを実施しました。

## 制約

ローカル検証はHTTPです。実SMTPは使用せず `backend/maildrop/` にJSONを書き出します。SQLite、bin/obj、node_modules、DBファイルはコミットしません。
