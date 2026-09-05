# 申請管理システム

## 起動方法

バックエンド:

```powershell
cd backend
dotnet restore
$env:ASPNETCORE_ENVIRONMENT="Development"
dotnet run
```

`http://localhost:5080` でAPIを待ち受けます。フロントエンド:

```powershell
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

`http://localhost:5173` を開きます。初期アカウントのパスワードはすべて `Password1` です。開発環境では `POST /api/dev/reset` でDBとmaildropを初期化できます。

## 自主検証

.NET 8 SDKで `dotnet restore` と `dotnet build --no-restore`、Node.js 24で `npm install` と `npm run build` を実行しました。APIの実ブラウザ検証は未実施です。npm auditでは既存依存の脆弱性報告が5件ありました。

## 制約

ローカル検証はHTTPです。SMTPは実送信せず `backend/maildrop` にJSONを書き出します。添付ファイル、全管理画面の編集フォーム、パスワード変更、CSV画面操作など一部UIは未実装ですが、主要APIと申請作成・承認フローを実装しています。
