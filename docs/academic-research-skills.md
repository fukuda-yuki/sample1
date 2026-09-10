# ARS-Codex（研究管理用）

配布元: https://github.com/Imbad0202/academic-research-skills-codex

Codexプラグイン名は `ars-codex`。本チェックアウトでは、同じ配布元の
`academic-research-suite` をリポジトリローカルの `.agents/skills/` に直接導入する。
ユーザー全体のプラグイン設定は変更しない。

- バージョン: 0.1.28
- 固定コミット: `925975e933a20893b81681d925a3404e3b7f73b7`
- 配布パス: `skills/academic-research-suite`
- ライセンス: CC BY-NC 4.0（非商用条件あり。配布元LICENSEを参照）

## 利用

このリポジトリを開いたCodexで、次のように明示する。表示されない場合は新しい会話を開く。

```text
$academic-research-suite を使い、本リポジトリの研究設計をレビューしてください。
AGENTS.mdと現在のGitHub Issueを正本にし、事実・推論・未確認を区別してください。
```

文献調査、論文執筆、査読、研究から論文化までの手順、実験計画に対応する。
研究管理用として使用し、実装Runへの配布許可リストに追加しない。
導入だけで新規Run・条件変更・外部モデル送信を許可したことにはならない。
適用するルールはルートAGENTS.mdとdocs/agent-roles.mdを参照する。

## 再導入

Codex同梱の `skill-installer/scripts/install-skill-from-github.py` に次を渡す。
既存の導入先がある場合は上書きせず停止するため、更新は別途判断する。

```text
--repo Imbad0202/academic-research-skills-codex
--ref 925975e933a20893b81681d925a3404e3b7f73b7
--path skills/academic-research-suite
--dest <このリポジトリの絶対パス>/.agents/skills
--method git
```

Windowsでは長いパスへの対応が必要になる場合がある。
導入した外部ファイルはローカルGit除外に置き、研究成果物とまとめて公開しない。
この手順書と固定コミットを使って別チェックアウトでも再導入できる。
