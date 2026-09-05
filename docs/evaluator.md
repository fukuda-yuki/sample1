# 独立評価器の実行契約

採点コード、Playwright設定、fixture、詳細結果は研究者専用の `<private-eval-root>` に保存する。公開Gitへケースのコード・失敗内容・画面・traceを追加しない。比較実装の `e2e/`、設定、自己報告、skip指定は読み込まない。

固定採点単位は [case-manifest.json](../evaluation/case-manifest.json) の57 ID・58ケース。T-006-05だけはlowerとupperの両方が必要。その他はmain 1件。ID内の必須ケース全成功で合格、部分点なし。別の診断結果は `diagnostics.jsonl` に出し、分母と57 IDの合否を変えない。

## 実行

研究者の独立環境で private root の `npm ci` と `npx playwright install chromium` を実行する。依存はlockfileで固定し、Playwright 1.58.2、Chromium 145.0.7632.6、workers 1、retries 0、Asia/Tokyo、毎ケース新しいブラウザコンテキストと公開resetから開始する。

`node <private-eval-root>/run.mjs <researcher-config.json>` がアプリを外部から起動し、固定設定で採点する。設定は研究者が作成し、提出物に含まれた実行スクリプトを評価器の権限で動かさない。

```json
{
  "kind": "evaluation",
  "run_id": "run-001",
  "submission_root": "/research/runs/run-001/frozen",
  "snapshot_file": "/research/runs/run-001/snapshot.json",
  "container_id": "sample1-evaluation-run-001",
  "app_url": "http://127.0.0.1:5173",
  "api_url": "http://127.0.0.1:5080",
  "maildrop": "/research/maildrop/run-001",
  "output": "/research/private-eval/results/run-001"
}
```

`ui_map` は提出物の任意 `ui-map.json` のパス。公開したaccessible-name対応を適用する。CSS構造や内部APIを採点基準にしない。管理画面・詳細画面のURLは権限のあるユーザーのUIから取得する。テスト用reset以外の前提データは画面操作で作成する。メールだけは公開maildrop契約で確認する。

## 分離と提出固定

比較Runの実装プロセスを終了してsnapshotを固定した後、評価器が停止済み評価用コンテナを起動する。評価器はDockerから、非root、全capability除去、host namespace非共有、digest固定image、提出物のread-only mountを確認する。許可するhost mountは提出物とmaildropだけ。private root・認証情報・Docker socket・親ディレクトリをmountしない。評価出力はprivate rootに限定する。

提出物はread-onlyの `/submission` 等からコンテナの作業領域へコピーして標準起動する。DB・依存ビルド生成物はコンテナ内に置き、maildropだけ専用外部出力先へ接続する。研究者用の実運用資格情報をコンテナへ渡さない。Docker bindのhostパスを同一ホストで解決できる環境を使う。Windowsの校正実行とLinux上の本評価を混同しない。

開始前・終了後に提出物全ファイルをsnapshotと照合する。snapshot.json自身のSHA-256をsubmission_hashとする。評価器コード・設定・lockfile・台帳・ケース一覧のハッシュを `version.json` へ保存し、その集合のSHA-256をscore_version/evaluator_hashとする。アプリのソースコードは品質採点しない。

## 出力と障害分類

- `results.jsonl`: [result.schema.json](../evaluation/result.schema.json) に対応する58行。根拠・trace・スクリーンショットはprivateに保存。
- `diagnostics.jsonl`: 採点外の診断。集計器の入力に混ぜない。
- `summary.json`: 57 ID別判定、件数、ブラウザ版、各ハッシュ、開始・終了時刻、Runの状態。
- `raw.json`, `browser/`, `application.*.log`, `playwright.stderr.log`: 評価環境の根拠。

`server_unavailable` は起動不能で全IDをblocked、画面から観測した要件未達はfail。採点器の起動・出力・依存・snapshot検証障害はerrorで品質得点をnullとする。分離が確認できない場合はisolation_blockedで得点null。missing/skipは合格にしない。未実行IDを分母から落とさない。

校正は `kind: calibration` と研究者管理の `launch: {command,args,cwd,env}` を使う。このモードは隔離済みの比較実験を意味しない。校正fixtureは比較Runのnormal/anti提出物として扱わない。校正完了後の比較提出者へ失敗ケースを返さない。
