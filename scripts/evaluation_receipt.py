"""Researcher-side startup and application evidence; never a scoring assertion."""
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from preserve import digest,read
from telemetry_link import atomic


def seeded_login_observations(events):
    """The logged helper's final logout-visibility assertion confirms authentication.

    Discovery visibility and a completed submit click alone do not establish login.
    The evaluator snapshot and event sequence retain the assertion's source binding.
    """
    observed=[]
    for e in events:
        if e.get('outcome')!='completed' or e.get('intent')!='toBeVisible' or e.get('stage') not in ('business_assertion','operation'):
            continue
        for account in ('admin','ippan','kacho','bucho'):
            if 'ログイン '+account in e.get('prerequisites',[]):
                observed.append({'sequence':e['sequence'],'account':account})
    return observed


def capture(resources,run):
    directory=Path(resources['output']).parent/'management-evidence'
    directory.mkdir(exist_ok=True)
    captures={}
    for kind in ('app','researcher'):
        identity=resources[kind+'_container']
        for operation,args in [('inspect',['inspect',identity]),('logs',['logs',identity])]:
            completed=subprocess.run(['docker',*args],capture_output=True,timeout=30)
            paths=[]
            for stream in ('stdout','stderr'):
                path=directory/(kind+'-'+operation+'.'+stream+'.log')
                data=getattr(completed,stream)
                path.write_bytes(data.encode('utf-8') if isinstance(data,str) else data)
                paths.append({'path':path.name,'sha256':digest(path)})
            captures[kind+'_'+operation]={'container_id':identity,'exit_code':completed.returncode,'files':paths,
                'state':'acquired' if completed.returncode==0 else 'not_acquired'}
    config=read(Path(resources['config']))
    raw=Path(resources['output'])/'results.jsonl'
    cases=[]
    if raw.exists():
        for line in raw.read_text(encoding='utf-8').splitlines():
            row=json.loads(line);measurement=row.get('evidence',{}).get('measurement') or {}
            events=measurement.get('events',[])
            reset=[e for e in events if e.get('stage')=='initialization']
            seed=seeded_login_observations(events)
            reset_failure='Public reset HTTP' in (row.get('evidence',{}).get('message') or '')
            cases.append({'evaluation_id':row['evaluation_id'],'case_id':row['case_id'],
                'reset':'failed' if reset_failure else 'completed' if any(e['outcome']=='completed' for e in reset) else 'not_acquired',
                'seed':'observed_via_ui_login' if seed else 'not_independently_verified',
                'seed_events':seed,
                'observation_source':'result/results.jsonl','reset_events':[e['sequence'] for e in reset]})
    receipt={'schema_version':2,'recorded_at':datetime.now(timezone.utc).isoformat(),
        'evaluation_id':resources['evaluation_id'],'run_id':read(run/'manifest.json')['run_id'],
        'submission_hash':digest(run/'snapshot.json'),'resources':resources,'capture':captures,
        'contract_hashes':{name:digest(run/'frozen'/name) for name in ('spec.md','RUN_CONTRACT.md') if (run/'frozen'/name).is_file()},
        'preparation':{'ui_entry':config.get('app_url'),'api_entry':config.get('api_url'),
            'maildrop_exists':Path(config['maildrop']).is_dir(),'maildrop':config['maildrop'],
            'seed_check':'per-case UI login evidence; no internal business API bypass','cases':cases},
        'validity':'pending','note':'Preparation and captured logs do not establish valid scoring.'}
    atomic(directory/'receipt.json',receipt)
    return directory
