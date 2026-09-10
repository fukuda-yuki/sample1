-- claim: C01_condition_statistics
WITH population AS (
  SELECT batch AS stratum, * FROM runs
  UNION ALL SELECT 'cumulative' AS stratum, * FROM runs
)
SELECT stratum, condition, COUNT(*) AS planned, COUNT(run_id) AS started,
       COUNT(passed_ids) AS scored, SUM(recorded_total_tokens) AS recorded_tokens,
       AVG(recorded_total_tokens) AS mean_recorded_tokens,
       AVG(passed_ids) AS mean_passed_ids, 100.0*AVG(passed_ids)/57 AS mean_pass_rate
FROM population WHERE model_id='muse-spark-1.2-contributor'
GROUP BY stratum, condition ORDER BY stratum, condition;

-- claim: C02_population_and_validity
SELECT batch, condition, model_id, evaluation_validity, COUNT(*) AS planned,
       COUNT(run_id) AS started, COUNT(passed_ids) AS scored,
       SUM(json_extract(row_json,'$.effective_quality') IS NOT NULL) AS effective_quality_available,
       SUM(json_extract(row_json,'$.source_usage_complete')=0) AS usage_incomplete
FROM runs GROUP BY batch, condition, model_id, evaluation_validity
ORDER BY batch, condition, model_id, evaluation_validity;

-- claim: C03_dependency_groups
WITH population AS (
 SELECT r.batch AS stratum, r.condition, i.* FROM id_results i JOIN runs r USING(run_id)
 WHERE r.model_id='muse-spark-1.2-contributor'
 UNION ALL
 SELECT 'cumulative', r.condition, i.* FROM id_results i JOIN runs r USING(run_id)
 WHERE r.model_id='muse-spark-1.2-contributor'
)
SELECT stratum, condition, dependency_group, COUNT(DISTINCT run_id) AS runs,
       COUNT(*) AS ids, SUM(passed) AS passed_ids,
       1.0*SUM(passed)/COUNT(DISTINCT run_id) AS mean_passed_ids
FROM population WHERE passed IS NOT NULL GROUP BY stratum, condition, dependency_group
ORDER BY stratum, dependency_group, condition;

-- claim: C04_recorded_and_static_thresholds
SELECT batch, condition,
       json_extract(row_json,'$.static_threshold_yen') AS static_threshold_yen,
       json_extract(row_json,'$.recorded_threshold_yen') AS recorded_threshold_yen,
       json_extract(row_json,'$.explicit_conflict_recorded') AS explicit_conflict_recorded,
       json_extract(row_json,'$.saved_500k_pattern_matches') AS saved_500k_pattern_matches,
       COUNT(*) AS runs
FROM runs WHERE model_id='muse-spark-1.2-contributor'
GROUP BY batch, condition, static_threshold_yen, recorded_threshold_yen,
         explicit_conflict_recorded, saved_500k_pattern_matches
ORDER BY batch, condition, static_threshold_yen;

-- claim: C05_reachability
SELECT batch, condition, COUNT(passed_ids) AS scored_runs,
       SUM(json_extract(row_json,'$.business_assertion_reached')) AS reached_cases,
       SUM(json_extract(row_json,'$.prerequisite_blocked')) AS prerequisite_blocked_cases,
       SUM(json_extract(row_json,'$.evaluation_unresolved')) AS unresolved_cases,
       SUM(json_extract(row_json,'$.reachability_unknown')) AS unknown_cases
FROM runs WHERE model_id='muse-spark-1.2-contributor'
GROUP BY batch, condition ORDER BY batch, condition;

-- claim: C06_responses_and_tokens
SELECT batch, condition, COUNT(recorded_total_tokens) AS token_runs,
       SUM(json_extract(row_json,'$.http_200')) AS successful_http_responses,
       SUM(recorded_total_tokens) AS recorded_tokens,
       1.0*SUM(recorded_total_tokens)/NULLIF(SUM(json_extract(row_json,'$.http_200')),0) AS tokens_per_successful_response,
       SUM(json_extract(row_json,'$.http_400')) AS http_400,
       SUM(json_extract(row_json,'$.http_429')) AS http_429,
       SUM(json_extract(row_json,'$.http_503')) AS http_503
FROM runs WHERE model_id='muse-spark-1.2-contributor'
GROUP BY batch, condition ORDER BY batch, condition;

-- claim: C07_termination
SELECT batch, condition, json_extract(row_json,'$.raw_end_reason') AS end_reason,
         json_extract(row_json,'$.stop_trigger') AS stop_trigger,
         json_extract(row_json,'$.stop_method') AS stop_method,
       json_extract(row_json,'$.exit_code') AS cli_exit_code,
       json_extract(row_json,'$.completion_declaration_captured') AS declaration,
       COUNT(*) AS runs, AVG(recorded_total_tokens) AS mean_tokens,
       AVG(passed_ids) AS mean_passed_ids
FROM runs GROUP BY batch, condition, end_reason, stop_trigger, stop_method, cli_exit_code, declaration
ORDER BY batch, condition, end_reason;

-- claim: C08_pairs
SELECT n.batch, json_extract(n.row_json,'$.pair_id') AS pair_id,
       n.slot_key AS normal_slot, a.slot_key AS anti_slot,
       a.recorded_total_tokens-n.recorded_total_tokens AS token_difference,
       a.passed_ids-n.passed_ids AS passed_difference,
       100.0*(a.passed_ids-n.passed_ids)/57 AS pass_rate_difference_pp
FROM runs n JOIN runs a ON n.batch=a.batch
 AND json_extract(n.row_json,'$.pair_id')=json_extract(a.row_json,'$.pair_id')
 AND n.condition='normal' AND a.condition='anti'
WHERE n.model_id='muse-spark-1.2-contributor' AND a.model_id='muse-spark-1.2-contributor'
ORDER BY n.batch, pair_id;

-- claim: C09_extremes_and_efficiency
SELECT slot_key, condition, batch, recorded_total_tokens, passed_ids,
       1.0*recorded_total_tokens/NULLIF(passed_ids,0) AS tokens_per_passed_id,
       json_extract(row_json,'$.elapsed_seconds') AS elapsed_seconds,
       json_extract(row_json,'$.raw_end_reason') AS end_reason
FROM runs WHERE model_id='muse-spark-1.2-contributor'
ORDER BY recorded_total_tokens DESC, slot_key;

-- claim: C10_order_sensitivity
SELECT batch, condition,
       CASE WHEN json_extract(row_json,'$.pair_id')<=(CASE batch WHEN 'previous' THEN 5 ELSE 10 END)
       THEN 'first_half' ELSE 'second_half' END AS schedule_half,
       COUNT(*) AS planned, COUNT(recorded_total_tokens) AS token_runs,
       AVG(recorded_total_tokens) AS mean_tokens, AVG(passed_ids) AS mean_passed_ids
FROM runs WHERE model_id='muse-spark-1.2-contributor'
GROUP BY batch, condition, schedule_half ORDER BY batch, schedule_half, condition;

-- claim: C11_case_count
SELECT batch, COUNT(DISTINCT run_id) AS output_runs, COUNT(*) AS saved_case_records,
       COUNT(DISTINCT CASE WHEN score_available THEN run_id END) AS available_score_runs,
       SUM(score_available) AS case_records_in_available_outputs,
       SUM(status='pass') AS pass_cases, SUM(status='fail') AS fail_cases,
       SUM(status='blocked') AS blocked_cases, SUM(status='error') AS error_cases
FROM case_results GROUP BY batch ORDER BY batch;

-- claim: C12_item_gap
SELECT i.test_id, i.feature_id, i.dependency_group,
       COUNT(CASE r.condition WHEN 'normal' THEN i.passed END) AS normal_available_runs,
       COUNT(CASE r.condition WHEN 'anti' THEN i.passed END) AS anti_available_runs,
       AVG(CASE r.condition WHEN 'normal' THEN i.passed END) AS normal_pass_fraction,
       AVG(CASE r.condition WHEN 'anti' THEN i.passed END) AS anti_pass_fraction,
       AVG(CASE r.condition WHEN 'normal' THEN i.passed END)-AVG(CASE r.condition WHEN 'anti' THEN i.passed END) AS mean_normal_minus_anti,
       SUM(CASE r.condition WHEN 'normal' THEN i.passed ELSE 0 END) AS normal_passed,
       SUM(CASE r.condition WHEN 'anti' THEN i.passed ELSE 0 END) AS anti_passed,
       SUM(CASE r.condition WHEN 'normal' THEN i.passed ELSE -i.passed END) AS normal_minus_anti
FROM id_results i JOIN runs r USING(run_id)
WHERE r.model_id='muse-spark-1.2-contributor' AND i.passed IS NOT NULL
GROUP BY i.test_id ORDER BY normal_minus_anti DESC, i.test_id;

-- claim: C13_medians
WITH population AS (
 SELECT batch AS stratum, * FROM runs
 UNION ALL SELECT 'cumulative', * FROM runs
), values_long AS (
 SELECT stratum,condition,'tokens' AS metric,recorded_total_tokens AS value
 FROM population WHERE model_id='muse-spark-1.2-contributor' AND recorded_total_tokens IS NOT NULL
 UNION ALL
 SELECT stratum,condition,'passed_ids',passed_ids
 FROM population WHERE model_id='muse-spark-1.2-contributor' AND passed_ids IS NOT NULL
), ordered AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY stratum,condition,metric ORDER BY value) AS rn,
          COUNT(*) OVER(PARTITION BY stratum,condition,metric) AS n
 FROM values_long
)
SELECT stratum,condition,metric,AVG(value) AS median_value,MAX(n) AS n
FROM ordered WHERE rn IN ((n+1)/2,(n+2)/2)
GROUP BY stratum,condition,metric ORDER BY stratum,condition,metric;

-- claim: C14_unavailable_evaluations
SELECT slot_key,run_id,evaluation_uuid,recorded_total_tokens,
       json_extract(row_json,'$.evaluation_outcome') AS evaluation_outcome,
       json_extract(row_json,'$.source_passed_ids') AS source_passed_ids,
       passed_ids AS analysis_passed_ids
FROM runs WHERE passed_ids IS NULL ORDER BY batch,slot_key;

-- claim: C15_token_components_post_hoc
SELECT batch,condition,COUNT(json_extract(row_json,'$.recorded_input_tokens')) AS observed_runs,
       SUM(json_extract(row_json,'$.recorded_input_tokens')) AS input_tokens,
       SUM(json_extract(row_json,'$.recorded_output_tokens')) AS output_tokens,
       SUM(json_extract(row_json,'$.recorded_cached_input_tokens')) AS cached_input_tokens,
       COUNT(json_extract(row_json,'$.recorded_cached_input_tokens')) AS complete_cache_detail_runs,
       SUM(json_extract(row_json,'$.usage_requests')) AS observed_requests
FROM runs WHERE model_id='muse-spark-1.2-contributor'
GROUP BY batch,condition ORDER BY batch,condition;
