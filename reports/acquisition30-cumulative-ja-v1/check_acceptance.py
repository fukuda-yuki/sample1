"""Bind final delivery checks to the exact report and analytical artifacts."""
from pathlib import Path
import hashlib
import json
from bind_replay_outputs import logical

BASE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    checks=BASE/'checks'
    numerical=read(checks/'verification.json')
    assert numerical['report_sha256']==sha(BASE/'report.md')
    assert (numerical['planned'],numerical['started'],numerical['scored'],numerical['run_ids'],numerical['cases'])==(60,60,57,3420,3480)
    assert numerical['legacy_original_files_verified']==320
    assert numerical['qualitative_source_bindings_verified']==40 and numerical['saved_evaluation_observations_bound']==7
    acquisition=read(checks/'acquisition-audit.json')
    assert acquisition['started']==40 and acquisition['conditions']=={'normal':20,'anti':20}
    assert acquisition['archived_and_restored_bytes_verified'] and acquisition['old_hashes_unchanged']
    assert acquisition['running_owned_containers']==[]
    raw=read(checks/'raw-restored-replay.json')
    assert raw['sqlite_logically_identical'] and raw['docker']['original_workspace_mounted'] is False
    assert raw['docker']['network']=='none' and raw['docker']['original_evaluation_paths_absent']==40
    candidates=sorted(checks.glob('cumulative-restored-replay-*.json'))
    assert candidates,'Finish the restored-only cumulative replay'
    reports=[(p,read(p)) for p in candidates]
    for p,r in reports:
        assert r['sqlite_logically_identical'] and r['docker']['only_restored_inputs_code_and_runtime_mounted']
        assert r['docker']['original_paths_absent'] and r['docker']['network']=='none'
        assert len(r['identical_outputs'])==34,(p,len(r['identical_outputs']))
    replay=read(checks/'replay-output-bindings.json')
    assert sha(BASE/replay['cumulative_proof'])==replay['cumulative_proof_sha256']
    assert sha(BASE/replay['raw_proof'])==replay['raw_proof_sha256']
    for name,binding in replay['cumulative_outputs'].items():
        fun=logical if name.endswith('.sqlite') else sha
        assert fun(BASE/name)==binding['sha256'],name
    browser=read(checks/'browser-render.json')
    assert browser['report_sha256']==sha(BASE/'report.md') and browser['preview_sha256']==sha(BASE/'report.html')
    assert len(browser['state']['images'])==6 and all(r['loaded'] for r in browser['state']['images'])
    assert not browser['state']['horizontalOverflow'] and not browser['narrow']['horizontalOverflow']
    assert browser['remoteRequests']==[]
    secrets=read(checks/'secret-scan.json')
    assert secrets['exact_credential_absent'] and not secrets['credential_value_or_hash_disclosed']
    publication=read(checks/'publication-secret-scan.json')
    assert publication['exact_credential_absent'] and publication['publication_only']
    assert not publication['credential_value_or_hash_disclosed']
    review=read(BASE/'reviews/review-resolution.json')
    assert review['independent_context'] and not review['drafting_history_shared']
    assert review['major_findings_resolved'] and review['reviewer_recheck_complete']
    scientific=(BASE/'report.md').read_bytes().split('## 6.'.encode(),1)[0]
    assert hashlib.sha256(scientific).hexdigest()==review['scientific_report_sha256']
    for field in ('review_file','response_file','recheck_file'):
        assert sha(BASE/review[field])==review[field+'_sha256']
    for name,binding in read(checks/'preflight/manifest.json').items():
        assert sha(checks/'preflight'/name)==binding['sha256']
    assert sha(BASE/'drill_pipeline_docker.py')==read(checks/'docker-drills/manifest.json')['proofs']['fallback']['result']['script_sha256']
    figures=read(BASE/'figures/figure-trace.json')
    assert len(figures['figures'])==6
    artifacts=[BASE/'report.md',BASE/'report.html',BASE/'supplement.md',BASE/'claim-evidence.json',
               BASE/'data/analysis.sqlite',BASE/'data/runs.csv',BASE/'data/runs.json',BASE/'data/results.json',
               BASE/'queries.sql',BASE/'source-manifest.json',checks/'verification.json',checks/'acquisition-audit.json',
               checks/'raw-restored-replay.json',checks/'browser-render.json',checks/'secret-scan.json',
               checks/'publication-secret-scan.json',
               checks/'replay-output-bindings.json',
               BASE/'reviews/review-resolution.json',*[p for p,_ in reports]]
    result={'kind':'local-final-acceptance','planned':60,'additional_starts':40,'available_scores':57,
        'whole_evaluation_unavailable':3,'new_run_id_rows':2280,'new_case_rows':2320,
        'cumulative_run_id_rows':3420,'cumulative_case_rows':3480,
        'old_files_unchanged':320,'acquisition_archived_and_restored':40,'restored_only_raw_and_cumulative_replay':True,
        'independent_review_and_recheck':True,'japanese_report_render_verified':True,'credential_scan_passed':True,
        'quality_adjudications_overwritten':False,'new_model_calls_by_acceptance':0,'new_evaluations_by_acceptance':0,
        'publication_scope':'Local acceptance only. Remote branch SHA and Issue closure are recorded separately after publication.',
        'artifacts':{str(p.relative_to(BASE)):sha(p) for p in artifacts}}
    (checks/'final-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='artifacts'},ensure_ascii=False))

if __name__=='__main__':main()
