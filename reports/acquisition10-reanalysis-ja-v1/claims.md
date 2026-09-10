# 主張と証拠の対応表

各数表は分析用SQLiteに対するSQLから生成しています。C01・C02の読解は旧裁定とは別の解釈です。

## C01

**矛盾の見落としより、認識後の詳細仕様優先が記録に合う**

SQL: [threshold_fingerprint](queries.sql), [interpretations](queries.sql)

数表: [threshold_fingerprint](tables/threshold_fingerprint.csv), [interpretations](tables/interpretations.csv)

読解証拠: [qualitative.json](evidence/qualitative.json)

図: [06-dependency-path](figures/06-dependency-path.png)

**代替説明・限界:** 自己説明・固定コード・7件の既存挙動を区別。記録を内心の完全な説明としない。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C02

**閾値に直接・間接依存する13 IDに合格数差の62.5%が集中**

SQL: [groups](queries.sql), [ids](queries.sql), [trace_examples](queries.sql)

数表: [groups](tables/groups.csv), [ids](tables/ids.csv), [trace_examples](tables/trace_examples.csv)

読解証拠: [dependency-map.json](evidence/dependency-map.json), [private-evidence-index.json](evidence/private-evidence-index.json)

図: [05-gap-decomposition](figures/05-gap-decomposition.png), [06-dependency-path](figures/06-dependency-path.png)

**代替説明・限界:** 事後的な分類。62.5%を因果寄与率・修正後の回復率としない。群内の全失敗を同一原因にしない。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C03

**平均トークンは11.6%減るが合格IDあたり消費は37.8%増える**

SQL: [runs](queries.sql), [groups](queries.sql)

数表: [runs](tables/runs.csv), [groups](tables/groups.csv)

図: [01-distributions](figures/01-distributions.png)

**代替説明・限界:** 既存評価への適合効率。業務価値、真の品質、金銭費用に置換しない。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C04

**得点差は最悪の1ペアだけでは説明できず、低消費・同等以上の例外もある**

SQL: [pairs](queries.sql), [pareto](queries.sql), [runs](queries.sql)

数表: [pairs](tables/pairs.csv), [pareto](tables/pareto.csv), [runs](tables/runs.csv)

図: [02-pair-differences](figures/02-pair-differences.png)

**代替説明・限界:** 全10通りの1ペア除外を提示。主比較から悪いRunを削除しない。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C05

**条件を混ぜたトークンと得点の相関では成果の違いを十分説明できない**

SQL: [runs](queries.sql), [pareto](queries.sql)

数表: [runs](tables/runs.csv), [pareto](tables/pareto.csv)

図: [03-token-score](figures/03-token-score.png)

**代替説明・限界:** 小標本の相関。難航による追加消費という逆因果や実装方針の違いが残る。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C06

**残44 IDにも差があるが、不合格ケース数は独立した実装欠陥数ではない**

SQL: [features](queries.sql), [feature_runs](queries.sql), [categories](queries.sql), [coverage](queries.sql), [raw_case_status](queries.sql), [classifications](queries.sql), [groups](queries.sql)

数表: [features](tables/features.csv), [feature_runs](tables/feature_runs.csv), [categories](tables/categories.csv), [coverage](tables/coverage.csv), [raw_case_status](tables/raw_case_status.csv), [classifications](tables/classifications.csv), [groups](tables/groups.csv)

読解証拠: [dependency-map.json](evidence/dependency-map.json)

図: [04-feature-heatmap](figures/04-feature-heatmap.png)

**代替説明・限界:** 到達と前提未成立は重複。未裁定を実装原因へ変換しない。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C07

**総トークン差は応答回数と応答あたり量へ分解でき、時間短縮とは一致しない**

SQL: [process](queries.sql), [runs](queries.sql)

数表: [process](tables/process.csv), [runs](tables/runs.csv)

図: [07-process](figures/07-process.png)

**代替説明・限界:** 対称算術分解であって因果推定ではない。HTTP 200数を思考ステップ数としない。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C08

**得点差の方向と比べ、トークン差には前後半・Run構成への依存がある**

SQL: [pairs](queries.sql), [runs](queries.sql)

数表: [pairs](tables/pairs.csv), [runs](tables/runs.csv)

図: [08-sensitivity](figures/08-sensitivity.png)

**代替説明・限界:** 前後半分割は事後分析。bootstrapは評価器の系統的制約を補正しない。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。

## C09

**全20件への変更により旧14件抽出による比較対象の偏りが緩和された**

SQL: [http_groups](queries.sql), [runs](queries.sql)

数表: [http_groups](tables/http_groups.csv), [runs](tables/runs.csv)

図: [08-sensitivity](figures/08-sensitivity.png)

**代替説明・限界:** HTTP 400は無作為な処置ではない。発生と得点・消費の因果関係は未確認。

対象は全20 Runです。Run UUID・評価UUIDは[機械可読台帳](claims.json)から、Run別数値は[全Run表](tables/runs.csv)から追跡できます。
