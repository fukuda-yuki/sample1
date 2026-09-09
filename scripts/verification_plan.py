"""Select checks by their actual input hashes; never turn smoke into E2E evidence."""
import argparse
import json
from pathlib import Path
from preserve import digest,read

COMPONENTS={
 'execution':('scripts/run_copilot.py','scripts/copilot_scope.py','scripts/run_experiment.py','scripts/prepare_workspace.py','scripts/run_codex.py','evaluation/prepare-app-container.py','scripts/evaluation_receipt.py'),
 'provider':('scripts/model_gateway.py','scripts/run_copilot.py'),
 'usage':('scripts/gateway_usage.py','scripts/normalize_usage.py','scripts/telemetry_link.py'),
 'parallel':('scripts/copilot_parallel.py','scripts/copilot_batch_worker.py','scripts/copilot_recovery.py','scripts/copilot_batch.py','scripts/run_cleanup.py'),
 'scoring':('evaluation/case-manifest.json','evaluation/requirements-ledger.json','analysis/aggregate.py','analysis/measurement.py'),
 'export':('scripts/copilot_batch.py','analysis/collect_runs.py','analysis/aggregate.py','analysis/measurement.py','analysis/validity.py','analysis/plot.py'),
 'preservation':('scripts/preserve.py','scripts/copilot_analysis_archive.py','scripts/check_copilot_analysis_restore.py'),
}
CHECKS={
 'execution':['contract-negative-controls','isolated-cli-lifecycle'],
 'provider':['native-cli-tool-continuation','503-header-stop','bounded-unscored-smoke'],
 'usage':['raw-native-reconciliation','missing-usage-negative-controls','monitor-readback'],
 'parallel':['real-subprocess-concurrency','docker-isolation-and-cleanup','interruption-recovery'],
 'scoring':['requirements-mapping','exact-id-calibration','same-submission-rescore'],
 'export':['valid-invalid-pending-coverage','csv-sqlite-consistency'],
 'preservation':['real-run-allowlist-restore','restored-only-reaggregation'],
 'evaluator':['ui-positive-negative-controls','exact-id-calibration','same-submission-rescore'],
}


def plan(root,receipts,*,evaluator=None,environment=None):
    groups=dict(COMPONENTS)
    if evaluator:
        groups['evaluator']=tuple('private:'+p for p in ('run.mjs','playwright.config.ts','package-lock.json',
            'requirements-ledger.json','case-manifest.json','tests/ui.ts','tests/application.spec.ts','tests/observation.ts','evidence-index.mjs'))
    rows=[]
    required_environment={'worker_image','evaluator_image','browser_version','node_version','python_version','contract_sha256','execution_config_sha256'}
    environment_complete=bool(environment) and all(environment.get(k) for k in required_environment)
    def evidence_verified(receipt):
        refs=receipt.get('evidence_refs',[])
        if not refs:return False
        try:return all(digest(root/ref['path'])==ref['sha256'] for ref in refs)
        except (OSError,KeyError,TypeError):return False
    for component,names in groups.items():
        hashes={name:digest(evaluator/name[8:] if name.startswith('private:') else root/name) for name in names}
        fingerprints={'files':hashes,'environment':environment or {}}
        valid=next((r for r in receipts if environment_complete and evidence_verified(r) and r.get('component')==component and r.get('fingerprints')==fingerprints
                    and r.get('passed') is True and set(CHECKS[component]).issubset(r.get('checks',[]))),None)
        rows.append(dict(component=component,required_checks=CHECKS[component],fingerprints=fingerprints,
            action='reuse' if valid else 'run',evidence=valid.get('evidence') if valid else None,
            elapsed_seconds=valid.get('elapsed_seconds') if valid else None,
            estimate_seconds=[600,3600] if component in ('scoring','evaluator') else [5,300],
            waiting_reason=None if valid else 'required checks have no verified reusable receipt',
            reason='identical dependencies and complete checks' if valid else 'changed or unobserved dependencies'))
    return {'schema_version':1,'model_called':False,'checks':rows,
        'environment_complete':environment_complete,'smoke_limit_seconds':300,'smoke_grants_scoring_acceptance':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--receipts',type=Path);p.add_argument('--evaluator',type=Path)
    p.add_argument('--environment',type=Path);a=p.parse_args()
    print(json.dumps(plan(Path(__file__).resolve().parents[1],read(a.receipts) if a.receipts else [],
        evaluator=a.evaluator,environment=read(a.environment) if a.environment else None),indent=2))
