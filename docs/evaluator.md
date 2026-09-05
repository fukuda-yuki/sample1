# 独立評価器の実行契約

採点コード、Playwright設定、fixture、詳細結果は研究者専用の `<private-eval-root>` に保存する。公開Gitへケースのコード・失敗内容・画面・traceを追加しない。比較実装の `e2e/`、設定、自己報告、skip指定は読み込まない。

固定採点単位は [case-manifest.json](../evaluation/case-manifest.json) の57 ID・58ケース。T-006-05だけはlowerとupperの両方が必要。その他はmain 1件。ID内の必須ケース全成功で合格、部分点なし。別の診断結果は `diagnostics.jsonl` に出し、分母と57 IDの合否を変えない。

## 実行

研究者の独立環境で private root の `npm ci` と `npx playwright install chromium` を実行する。依存はlockfileで固定し、Playwright 1.58.2、Chromium 145.0.7632.6、workers 1、retries 0、Asia/Tokyo、アサーション・操作待ち6秒、画面遷移待ち10秒、テスト全体120秒、毎ケース新しいブラウザコンテキストと公開resetから開始する。

`node <private-eval-root>/run.mjs <researcher-config.json>` がアプリを外部から起動し、フロントエンドとAPIそれぞれ最大120秒の起動待ちを行い、固定設定で採点する。設定は研究者が作成し、提出物に含まれた実行スクリプトを評価器の権限で動かさない。

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

比較Runの実装プロセスを終了してsnapshotを固定した後、評価器が停止済み評価用コンテナを起動する。評価器はDockerから、非root、全capability除去、host namespace非共有、digest固定image、提出物のread-only mountを確認する。許可するhost mountは提出物とmaildropだけ。アプリにはprivate root・認証情報・Docker socket・親ディレクトリをmountしない。ネットワークは専用internal networkかnoneとし、外部インターネットへ接続させない。評価出力はprivate rootに限定する。

提出物はread-onlyの `/submission` 等からコンテナの作業領域へコピーして標準起動する。DB・依存ビルド生成物はコンテナ内に置き、maildropだけ専用外部出力先へ接続する。研究者用の実運用資格情報をコンテナへ渡さない。Docker bindのhostパスを同一ホストで解決できる環境を使う。Windowsの校正実行とLinux上の本評価を混同しない。

開始前・終了後に提出物全ファイルをsnapshotと照合する。snapshot.json自身のSHA-256をsubmission_hashとする。評価器コード・設定・lockfile・台帳・ケース一覧のハッシュを `version.json` へ保存し、その集合のSHA-256をscore_version/evaluator_hashとする。各Runのevaluator-snapshot/に同じ版のコード・設定・依存lock・台帳の実体を保存し、開始時と終了時に評価器自身の変更も検知する。アプリのソースコードは品質採点しない。

## 出力と障害分類

- `results.jsonl`: [result.schema.json](../evaluation/result.schema.json) に対応する58行。根拠・trace・スクリーンショットはprivateに保存。
- `diagnostics.jsonl`: 採点外の診断。集計器の入力に混ぜない。
- `summary.json`: 57 ID別判定、件数、ブラウザ版、各ハッシュ、開始・終了時刻、Runの状態。
- `raw.json`, `browser/`, `application.*.log`, `playwright.stderr.log`: 評価環境の根拠。

`server_unavailable` は起動不能で全IDをblocked、画面から観測した要件未達はfail。採点器の起動・出力・依存・snapshot検証障害はerrorで品質得点をnullとする。分離が確認できない場合はisolation_blockedで全ケースerror、得点null。前提用のreset・ログイン・データ一括準備が失敗した場合はPRECONDITION_BLOCKEDの根拠を残す。missing/skipは合格にしない。未実行IDを分母から落とさない。

校正は `kind: calibration` と研究者管理の `launch: {command,args,cwd,env}` を使う。このモードは隔離済みの比較実験を意味しない。校正fixtureは比較Runのnormal/anti提出物として扱わない。校正完了後の比較提出者へ失敗ケースを返さない。

校正の検証概要と版は [calibration-summary.json](../evaluation/calibration-summary.json) と [evaluator-version.json](../evaluation/evaluator-version.json) を参照する。これは実装条件間の実験結果ではなく、採点器そのものの校正記録である。

Linux研究者コンテナのブラウザ配置（PLAYWRIGHT_BROWSERS_PATH）とHOMEはテスト子プロセスへ引き継ぐ。アプリには研究者のfilesystemやDocker socketを渡さない。インフラ統合時の是正と版の経緯はprivate CHANGELOGに残し、比較Runは同じ最終版で評価する。

起動helper protocol 2では、setup前処理失敗だけが予約終了コード121を返す。評価器はDocker label `sample1.helper_protocol=2` と終了コード121の両方を確認した場合にevaluator_error/57件error/品質nullとする。アプリのrestore/build/start失敗はblockedのまま。アプリ自身の121はhelperが122へ変換するため前処理失敗と混同しない。labelなし121もアプリ停止として扱う。終了状態を起動待ち中に確認するため、既に停止したプロセスを待ち続けない。

校正概要schema 2はUI挙動の校正版と起動分類の校正版を個別に記録する。旧版の実測を新版の実行結果へ付け替えない。起動分類以外の採点ケース・設定・依存・台帳ハッシュは同一である。
