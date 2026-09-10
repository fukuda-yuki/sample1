-- Q01_population
SELECT condition,COUNT(*) AS runs,COUNT(passed_ids) AS scored,
 SUM(NOT score_available) AS whole_unavailable,SUM(NOT source_usage_complete) AS incomplete_usage,
 SUM(recorded_total_tokens) AS tokens,SUM(evaluation_validity='invalid') AS invalid,
 SUM(evaluation_validity='pending') AS pending,SUM(effective_quality IS NOT NULL) AS effective_quality_available
FROM runs GROUP BY condition ORDER BY condition;

-- Q02_group_summary
SELECT condition,AVG(recorded_total_tokens) AS mean_tokens,MIN(recorded_total_tokens) AS min_tokens,
 MAX(recorded_total_tokens) AS max_tokens,AVG(passed_ids) AS mean_passed_ids,
 AVG(pass_rate) AS mean_pass_rate,MIN(passed_ids) AS min_passed,MAX(passed_ids) AS max_passed
FROM runs GROUP BY condition ORDER BY condition;

-- Q03_medians
WITH token_order AS (
 SELECT condition,recorded_total_tokens AS value,ROW_NUMBER() OVER(PARTITION BY condition ORDER BY recorded_total_tokens) AS rn,
 COUNT(*) OVER(PARTITION BY condition) AS n FROM runs
), score_order AS (
 SELECT condition,passed_ids AS value,ROW_NUMBER() OVER(PARTITION BY condition ORDER BY passed_ids) AS rn,
 COUNT(*) OVER(PARTITION BY condition) AS n FROM runs WHERE passed_ids IS NOT NULL
)
SELECT 'tokens' AS metric,condition,AVG(value) AS median FROM token_order WHERE rn IN ((n+1)/2,(n+2)/2) GROUP BY condition
UNION ALL SELECT 'passed_ids',condition,AVG(value) FROM score_order WHERE rn IN ((n+1)/2,(n+2)/2) GROUP BY condition;

-- Q04_function_results
SELECT i.feature_id,f.title,i.condition,COUNT(DISTINCT i.run_id) AS runs,COUNT(DISTINCT i.test_id) AS item_count,
 SUM(i.passed) AS passed,100.0*AVG(i.passed) AS pass_rate,
 SUM(i.raw_status='fail') AS failed,SUM(i.raw_status='blocked') AS blocked
FROM id_results i JOIN features f USING(feature_id) WHERE i.passed IS NOT NULL
GROUP BY i.feature_id,i.condition ORDER BY i.feature_id,i.condition;

-- Q05_all_item_results
SELECT test_id,MAX(title) AS title,condition,COUNT(*) AS runs,SUM(passed) AS passed,
 SUM(raw_status='fail') AS failed,SUM(raw_status='blocked') AS blocked,
 SUM(raw_status='error') AS error
FROM id_results WHERE passed IS NOT NULL GROUP BY test_id,condition ORDER BY test_id,condition;

-- Q06_identical_status_vectors
WITH ordered AS (
 SELECT test_id,condition,run_id,raw_status FROM id_results WHERE passed IS NOT NULL ORDER BY condition,test_id,run_id
), signatures AS (
 SELECT condition,test_id,GROUP_CONCAT(raw_status,',') AS status_vector FROM ordered GROUP BY condition,test_id
)
SELECT condition,COUNT(*) AS number_of_ids,GROUP_CONCAT(test_id,',') AS evaluation_ids,status_vector
FROM signatures GROUP BY condition,status_vector HAVING COUNT(*)>1 ORDER BY condition,number_of_ids DESC;

-- Q07_threshold_decisions
SELECT condition,static_threshold_yen,recorded_threshold_yen,explicit_conflict_recorded,COUNT(*) AS runs
FROM runs GROUP BY condition,static_threshold_yen,recorded_threshold_yen,explicit_conflict_recorded
ORDER BY condition,recorded_threshold_yen;

-- Q08_token_components
SELECT condition,COUNT(*) AS runs,SUM(recorded_total_tokens) AS total_tokens,
 SUM(recorded_input_tokens) AS input_tokens,SUM(recorded_output_tokens) AS output_tokens,
 SUM(recorded_cached_input_tokens) AS cached_input_tokens,SUM(usage_requests) AS usage_requests,
 AVG(usage_requests) AS mean_requests,
 1.0*SUM(recorded_total_tokens)/SUM(usage_requests) AS weighted_tokens_per_request
FROM runs GROUP BY condition ORDER BY condition;

-- Q09_extreme_and_low_scores
SELECT label,run_id,condition,recorded_total_tokens,passed_ids,usage_requests,tokens_per_recorded_request,
 elapsed_seconds,evaluation_outcome,business_assertion_reached,source_failed_cases,source_blocked_cases
FROM runs WHERE recorded_total_tokens>10000000 OR passed_ids<20 OR NOT score_available
ORDER BY recorded_total_tokens DESC;

-- Q10_score_histogram
SELECT condition,passed_ids,COUNT(*) AS runs FROM runs GROUP BY condition,passed_ids ORDER BY condition,passed_ids;

-- Q11_coverage_by_score_range
SELECT condition,CASE WHEN passed_ids IS NULL THEN 'unavailable' WHEN passed_ids<20 THEN '0_to_19'
 WHEN passed_ids<40 THEN '20_to_39' ELSE '40_to_57' END AS score_band,COUNT(*) AS runs,
 AVG(business_assertion_reached) AS mean_reached_cases,AVG(source_blocked_cases) AS mean_blocked_cases,
 SUM(recorded_total_tokens) AS tokens
FROM runs GROUP BY condition,score_band ORDER BY condition,score_band;

-- Q12_termination
SELECT condition,raw_end_reason,exit_code,completion_declaration_captured,COUNT(*) AS runs,
 COUNT(passed_ids) AS scored,AVG(passed_ids) AS mean_passed_ids
FROM runs GROUP BY condition,raw_end_reason,exit_code,completion_declaration_captured
ORDER BY condition,raw_end_reason,exit_code;

-- Q13_unavailable_cost
SELECT condition,score_available,COUNT(*) AS runs,SUM(recorded_total_tokens) AS tokens,
 AVG(recorded_total_tokens) AS mean_tokens
FROM runs GROUP BY condition,score_available ORDER BY condition,score_available;

-- Q14_other_direction
WITH per_item AS (
 SELECT test_id,MAX(title) AS title,
 AVG(CASE WHEN condition='normal' THEN passed END) AS normal_rate,
 AVG(CASE WHEN condition='anti' THEN passed END) AS anti_rate
 FROM id_results GROUP BY test_id
)
SELECT test_id,title,normal_rate,anti_rate,normal_rate-anti_rate AS mean_ID_gap
FROM per_item WHERE anti_rate>=normal_rate ORDER BY mean_ID_gap,test_id;

-- Q15_category_results
SELECT condition,category,COUNT(DISTINCT test_id) AS item_count,COUNT(*) AS observations,
 100.0*AVG(passed) AS pass_rate
FROM id_results WHERE passed IS NOT NULL GROUP BY condition,category ORDER BY category,condition;

-- Q16_nine_workflow_items
SELECT condition,COUNT(DISTINCT run_id) AS runs,COUNT(DISTINCT test_id) AS item_count,
 SUM(passed) AS passed,SUM(raw_status='fail') AS failed,SUM(raw_status='blocked') AS blocked,
 1.0*SUM(passed)/COUNT(DISTINCT run_id) AS mean_passed_ids
FROM id_results WHERE feature_id BETWEEN 'F-011' AND 'F-015' AND passed IS NOT NULL GROUP BY condition;
