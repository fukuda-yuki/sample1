-- query: runs
-- Grain: one acquired Run; total_tokens uses the approved observed-sum policy.
SELECT * FROM report_runs ORDER BY execution_order;

-- query: pairs
-- Fixed original blocks, not pairs chosen after seeing outcomes.
SELECT n.pair_id, n.first_condition,
 n.planned_run normal_run, a.planned_run anti_run,
 n.run_id normal_run_id, a.run_id anti_run_id,
 n.total_tokens normal_tokens, a.total_tokens anti_tokens,
 a.total_tokens-n.total_tokens token_difference,
 n.passed normal_passed, a.passed anti_passed,
 a.passed-n.passed passed_difference,
 a.raw_score-n.raw_score score_difference_pp
FROM report_runs n JOIN report_runs a USING(pair_id)
WHERE n.condition='normal' AND a.condition='anti' ORDER BY n.pair_id;

-- query: groups
-- Counts are ID-passes, not independent experimental replicates.
SELECT i.dependency_group, r.condition, COUNT(*) requested_ids,
 SUM(i.passed) passed_ids, 100.0*SUM(i.passed)/COUNT(*) pass_percent
FROM report_id_results i JOIN report_runs r USING(run_id)
GROUP BY i.dependency_group,r.condition ORDER BY i.dependency_group,r.condition;

-- query: features
SELECT i.feature_id,d.feature_title,r.condition,COUNT(*) requested_ids,
 SUM(i.passed) passed_ids,100.0*SUM(i.passed)/COUNT(*) pass_percent
FROM report_id_results i JOIN report_runs r USING(run_id)
JOIN report_dimensions d ON i.test_id=d.test_id
GROUP BY i.feature_id,d.feature_title,r.condition ORDER BY i.feature_id,r.condition;

-- query: feature_runs
SELECT r.planned_run,r.run_id,r.condition,i.feature_id,
 COUNT(*) requested_ids,SUM(i.passed) passed_ids,
 100.0*SUM(i.passed)/COUNT(*) pass_percent
FROM report_id_results i JOIN report_runs r USING(run_id)
GROUP BY r.run_id,i.feature_id ORDER BY r.planned_run,i.feature_id;

-- query: categories
SELECT i.category,r.condition,COUNT(*) requested_ids,
 SUM(i.passed) passed_ids,100.0*SUM(i.passed)/COUNT(*) pass_percent
FROM report_id_results i JOIN report_runs r USING(run_id)
GROUP BY i.category,r.condition ORDER BY i.category,r.condition;

-- query: ids
SELECT i.test_id,d.title,i.feature_id,i.category,i.dependency_group,
 r.condition,COUNT(*) runs,SUM(i.passed) passed_runs
FROM report_id_results i JOIN report_runs r USING(run_id)
JOIN report_dimensions d ON d.test_id=i.test_id
GROUP BY i.test_id,r.condition ORDER BY i.test_id,r.condition;

-- query: raw_case_status
SELECT r.condition,c.status,COUNT(*) cases
FROM case_results c JOIN report_runs r USING(run_id)
GROUP BY r.condition,c.status ORDER BY r.condition,c.status;

-- query: coverage
-- These dimensions overlap. Do not stack or force them to sum to a whole.
SELECT r.condition,SUM(f.cases) requested_cases,
 SUM(f.reached) business_assertions_reached,
 SUM(f.prerequisite_blocked) prerequisite_blocked,
 SUM(f.evaluation_unresolved) evaluation_unresolved,
 SUM(f.raw_pass_cases) raw_pass_cases
FROM report_feature_coverage f JOIN report_runs r USING(run_id)
GROUP BY r.condition ORDER BY r.condition;

-- query: classifications
SELECT r.condition,c.axis,c.label,SUM(c.cases) cases
FROM report_classifications c JOIN report_runs r USING(run_id)
GROUP BY r.condition,c.axis,c.label ORDER BY r.condition,c.axis,c.label;

-- query: process
SELECT condition,COUNT(*) runs,SUM(total_tokens) total_tokens,
 SUM(http_200) http_200,SUM(http_400) http_400,
 1.0*SUM(total_tokens)/SUM(http_200) tokens_per_200,
 AVG(elapsed_seconds) mean_elapsed_seconds
FROM report_runs GROUP BY condition ORDER BY condition;

-- query: http_groups
SELECT condition,(http_400>0) has_http_400,COUNT(*) runs,
 AVG(total_tokens) mean_tokens,AVG(passed) mean_passed,
 SUM(http_400) http_400
FROM report_runs GROUP BY condition,(http_400>0) ORDER BY condition,has_http_400;

-- query: threshold_fingerprint
SELECT r.planned_run,r.run_id,r.condition,c.evaluation_id test_id,c.case_id,c.status
FROM case_results c JOIN report_runs r USING(run_id)
WHERE c.evaluation_id IN ('T-006-01','T-006-02','T-006-03','T-006-04','T-006-05')
ORDER BY r.planned_run,c.evaluation_id,c.case_id;

-- query: pareto
-- Descriptive observed frontier, not a claim about true production quality.
SELECT r.planned_run,r.condition,r.total_tokens,r.passed
FROM report_runs r WHERE NOT EXISTS (
 SELECT 1 FROM report_runs o
 WHERE o.total_tokens<=r.total_tokens AND o.passed>=r.passed
 AND (o.total_tokens<r.total_tokens OR o.passed>r.passed))
ORDER BY r.total_tokens;

-- query: interpretations
-- Recorded intent and static implementation are separate evidence layers.
SELECT condition,COUNT(*) runs,SUM(explicit_conflict) conflict_recorded,
 recorded_threshold_yen,static_threshold_yen
FROM report_interpretations
GROUP BY condition,recorded_threshold_yen,static_threshold_yen ORDER BY condition;

-- query: trace_examples
SELECT run_id,test_id,evidence_json FROM report_trace_evidence ORDER BY run_id,test_id;
