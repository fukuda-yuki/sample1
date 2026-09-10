"""Additional non-model Docker failure drills; never dispatch a research model.

Uses the real controller, gateway, run lifecycle and preservation functions with
an internal HTTP fixture and a small HTTP client, plus Docker evaluation surrogates.
The preflight's five real Copilot CLIs separately verify native CLI integration.
"""
from pathlib import Path
import argparse,json,os,signal,subprocess,sys,time,uuid
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from copilot_parallel import make_plan,load
from parallel_acquisition import POLICY,MODELS,run_controller
from preserve import read,digest,pack,restore,verify_receipt,verify
from telemetry_link import atomic
from run_experiment import run,snapshot,write_json
from run_codex import GATEWAY_IMAGE,save_usage
from run_cleanup import cleanup

PROVIDER='''from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,os,time
from pathlib import Path
class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  with Path('/output/requests.jsonl').open('a') as f:f.write(json.dumps({'model':request['model']})+'\\n')
  code=int(os.environ['HTTP_CODE']);self.send_response(code);self.send_header('Content-Type','text/event-stream');self.end_headers()
  if code==200:self.wfile.write(('data: '+json.dumps({'type':'response.completed','response':{'id':'fixture','model':request['model'],'usage':{'input_tokens':9,'output_tokens':2}}})+'\\n\\n').encode())
  elif code==503:self.wfile.flush();time.sleep(30)
  else:self.wfile.write(b'fixture error')
ThreadingHTTPServer(('0.0.0.0',8080),H).serve_forever()
'''
GATEWAY="import sys,http.client\nsys.path.insert(0,'/code')\nimport model_gateway as g\ng.http.client.HTTPSConnection=lambda *a,**k:http.client.HTTPConnection('fake-provider',8080,timeout=10)\ng.ThreadingHTTPServer(('0.0.0.0',8080),g.Handler).serve_forever()\n"
def docker(*args):return subprocess.check_output(['docker',*args],text=True,stderr=subprocess.PIPE,timeout=90).strip()

def worker(assignment,scenario):
    a=read(assignment);d=assignment.parent;base=Path(a['root']).parent;rid=a['run_id'];eid=a['experiment_id']
    raw=d/'raw';raw.mkdir();spool=d/'upstream';spool.mkdir();dist=d/'distribution';(dist/'workspace').mkdir(parents=True)
    (dist/'workspace/spec.md').write_text('Synthetic fixture '+rid)
    write_json(dist/'distribution.json',{'condition':a['condition'],'files':{n:{'sha256':h} for n,h in snapshot(dist/'workspace').items()}})
    # A shared start barrier controls timing only; it is never mounted in a worker.
    write_json(d/'fixture-ready',{'run_id':rid,'pid':os.getpid(),'execution_order':a['execution_order']})
    if a['execution_order']<=5:
        deadline=time.monotonic()+30
        while len(list(Path(a['root']).glob('runs/*/fixture-ready')))<5:
            if time.monotonic()>deadline:raise TimeoutError('Five fixture reservations did not start')
            time.sleep(.05)
        time.sleep((6-a['execution_order'])*2)
    code=503 if scenario=='fallback' and a['execution_order']<=2 else 429 if scenario=='retention' and a['execution_order']==2 else 200
    net='sample1-private-'+rid;resources={};owned=[]
    try:
        resources[net]=docker('network','create','--internal','--opt','com.docker.network.bridge.gateway_mode_ipv4=isolated',
            '--label','sample1.run_id='+rid,'--label','sample1.drill_id='+eid,net)
        provider=docker('run','-d','--network',net,'--network-alias','fake-provider','--read-only','--cap-drop','ALL',
            '--user',f'{os.getuid()}:{os.getgid()}',
            '--env','HTTP_CODE='+str(code),'--mount',f'type=bind,source={base}/provider.py,target=/provider.py,readonly',
            '--mount',f'type=bind,source={spool},target=/output',GATEWAY_IMAGE,'python','/provider.py');owned.append(provider)
        name='sample1-gateway-'+rid
        gateway=docker('run','-d','--name',name,'--network',net,'--network-alias','model-gateway','--read-only','--cap-drop','ALL',
            '--label','sample1.run_id='+rid,'--user',f'{os.getuid()}:{os.getgid()}',
            '--env','PYTHONDONTWRITEBYTECODE=1','--env','RUN_ID='+rid,'--env','EXPERIMENT_ID='+eid,'--env','MODEL_ID='+a['model_id'],
            '--env','PROVIDER=opencode-go','--env','MODEL_HTTP_503_POLICY=stop_run_and_cleanup',
            '--mount',f'type=bind,source={ROOT}/scripts/model_gateway.py,target=/code/model_gateway.py,readonly',
            '--mount',f'type=bind,source={base}/gateway.py,target=/wrapper.py,readonly',
            '--mount',f'type=bind,source={base}/fixture-key,target=/secrets/zen-key,readonly',
            '--mount',f'type=bind,source={raw},target=/usage',GATEWAY_IMAGE,'python','/wrapper.py');owned.append(gateway);resources[name]=gateway
        client="import urllib.request,urllib.error,json,time;from pathlib import Path\ntime.sleep(1)\nfor i in range("+str(2 if code==429 else 1)+"):\n try:urllib.request.urlopen(urllib.request.Request('http://model-gateway:8080/responses',json.dumps({'model':'"+a['model_id']+"','stream':True}).encode())).read()\n except urllib.error.HTTPError:pass\nPath('marker').write_text('"+rid+"')\n"
        c=dict(batch_schema=2,agent='github-copilot-cli',phase='copilot-smoke',experiment_id=eid,experiment_version='synthetic-docker-drill',
            model_id=a['model_id'],effort=None,agent_version='synthetic-http-client',tool_versions={},subagent_policy='disabled',
            execution_order=a['execution_order'],environment={'image':GATEWAY_IMAGE},budget={'kind':'wall_clock_seconds','scope':'container','value':45},
            command=['python','-c',client],runtime_resources=resources,model_http_503_policy='stop_run_and_cleanup',usage_raw_directory=str(raw))
        with patch('run_experiment.check_start',return_value={'kind':'internal-synthetic-provider'}),patch('run_experiment.reserve_start'):
            result=run(dist,c,d/'attempt',network=net,run_id_override=rid)
        docker('stop','--time','1',gateway);docker('rm','-f',provider);save_usage(d/'attempt',raw,producer_stopped=True,error=None)
        if code==503:
            # A stalled error body need not produce a completed usage event.
            # The real gateway publishes its observed status at response headers.
            failure=read(raw/'provider-failure.json');assert failure['run_id']==rid
            codes=[failure['http_status']];code_source='provider-failure.json (response headers)'
        else:
            codes=[e['http_status'] for l in (raw/'events.jsonl').read_text().splitlines() if (e:=json.loads(l)).get('http_status') is not None]
            code_source='events.jsonl (completed responses)'
        assert len((spool/'requests.jsonl').read_text().splitlines())==(2 if code==429 else 1)
        assert codes==([429,429] if code==429 else [code]),codes
        if code==503:assert result['stop_trigger']=='model_http_503'
        original=pack(base/'archive','run-'+rid,{n:d/'attempt'/n for n in ('manifest.json','snapshot.json','frozen','raw-usage','usage.json','telemetry','agent.stdout.log','agent.stderr.log')},metadata={'run_id':rid})
        atomic(d/'archive-ref.json',original)
        cleaned=cleanup(d/'attempt',rid,base/'archive',original)
        assert cleaned['status']=='completed'
        atomic(d/'execution-result.json',dict(run_id=rid,experiment_id=eid,planned_run=a['planned_run'],producer_stopped=True,
            submission_hash=digest(d/'attempt/snapshot.json')))
        atomic(d/'fixture-proof.json',dict(http_codes=codes,http_code_source=code_source,model_calls=0,internal_provider=True,run_id=rid,cleanup=cleaned))
    finally:
        for identity in owned:subprocess.run(['docker','rm','-f',identity],capture_output=True,timeout=30)
        if resources.get(net):subprocess.run(['docker','network','rm',resources[net]],capture_output=True,timeout=30)
    # Make the first five real worker process exits strictly reverse their starts.
    # Timing coordination stays on the manager side and is never mounted into Docker.
    if a['execution_order']<5:
        peers=[read(p) for p in Path(a['root']).glob('runs/*/fixture-ready')]
        next_pid=next(p['pid'] for p in peers if p['execution_order']==a['execution_order']+1)
        deadline=time.monotonic()+90
        while True:
            try:os.kill(next_pid,0)
            except ProcessLookupError:break
            if time.monotonic()>deadline:raise TimeoutError('Reverse completion barrier did not release')
            time.sleep(.1)

def campaign(base,scenario):
    base.mkdir(parents=True);(base/'provider.py').write_text(PROVIDER);(base/'gateway.py').write_text(GATEWAY)
    (base/'fixture-key').write_text('synthetic-no-account');batch=base/'batch';validity=base/'validity.json';atomic(validity,{'attempts':[]})
    make_plan(batch,dict(batch_schema=2,phase='data-acquisition',acquisition_policy=POLICY,repetitions_per_condition=20,max_parallel=5,
        synthetic=True,model_id=MODELS[0],experiment_version='docker-failure-drill'),20260911)
    faults={'restore':scenario=='retention','registration':True};first_stage=True
    def command(root,c,row,a):return [sys.executable,str(Path(__file__).resolve()),'--worker',str(a),'--scenario',scenario]
    def collector(root,c,row,r):
        refpath=r.parent/'archive-ref.json'
        if refpath.exists():ref=read(refpath)
        else:
            ref=pack(base/'archive','run-'+row['run_id'],{n:r/n for n in ('manifest.json','snapshot.json','frozen','raw-usage','usage.json')},metadata={'run_id':row['run_id']});atomic(refpath,ref)
        if faults['restore'] and row['execution_order']==1:
            faults['restore']=False;raise OSError('Injected restoration failure after original package preservation')
        receipt=restore(base/'archive',ref,r.parent/'restored',resume=True);verify_receipt(base/'archive',receipt)
        codes=read(r.parent/'fixture-proof.json')['http_codes']
        if 429 in codes:return {'may_continue':False,'stop_reason':'repeated_http_429'}
        enough_fallbacks=scenario!='fallback' or len([x for x in load(root)[1]['runs'] if x.get('fallback_of')])>=2
        if row['execution_order']>=8 and enough_fallbacks:
            os.kill(os.getpid(),signal.SIGTERM)  # Real controller stop signal, drains active work.
        return {'may_continue':True,'stop_reason':''}
    def evaluator(root,c,row,r):
        saved=r.parent/'surrogate-result.json'
        if saved.exists():return read(saved)
        eid=str(uuid.uuid4());work=r.parent/'evaluation-surrogate';work.mkdir();net='sample1-drill-eval-'+eid
        script="import sqlite3,json,os,pathlib; p=pathlib.Path('/evidence'); d=sqlite3.connect(p/'db.sqlite'); d.execute('CREATE TABLE marker(owner TEXT)'); d.execute('INSERT INTO marker VALUES(?)',(os.environ['OWNER'],)); d.commit(); (p/'maildrop.json').write_text(json.dumps({'owner':os.environ['OWNER']})); assert d.execute('SELECT owner FROM marker').fetchone()[0]==os.environ['OWNER']; (p/'done.json').write_text(json.dumps({'owner':os.environ['OWNER'],'evaluation_id':os.environ['EID']}))"
        identity=None
        try:
            docker('network','create','--internal',net)
            identity=docker('create','--network',net,'--read-only','--cap-drop','ALL','--env','OWNER='+row['run_id'],'--env','EID='+eid,
                '--mount',f'type=bind,source={work},target=/evidence',GATEWAY_IMAGE,'python','-c',script)
            docker('start','-a',identity);done=read(work/'done.json');assert done['owner']==row['run_id'] and done['evaluation_id']==eid
            result={'result':{'evaluation_id':eid},'records':[{'evaluation_id':eid,'run_id':row['run_id'],'submission_hash':digest(r/'snapshot.json'),'status':'synthetic_only'}]}
            atomic(saved,result);return result
        finally:
            if identity:subprocess.run(['docker','rm','-f',identity],capture_output=True,timeout=30)
            subprocess.run(['docker','network','rm',net],capture_output=True,timeout=30)
    original_atomic=atomic
    def injected_atomic(path,value):
        if Path(path)==validity and faults['registration'] and value.get('attempts'):
            faults['registration']=False;raise OSError('Injected shared registration interruption after saved Docker result')
        original_atomic(path,value)
    with patch('parallel_acquisition.atomic',injected_atomic):first=run_controller(batch,command,collector,evaluator,validity)
    _,index=load(batch);before={r['planned_run']:r['run_id'] for r in index['runs'] if r['run_id']}
    failed=[r for r in index['runs'] if r['status']=='evaluation_error'];assert len(failed)==1
    fixed=read(batch/'runs'/failed[0]['planned_run']/'surrogate-result.json')
    for r in failed:r['status']='awaiting_evaluation'
    atomic(batch/'run-index.json',index)
    # The fixture controller ran in this process, which is now idle; mark its owner stale for restart.
    state=read(batch/'controller.json');state['owner']={'pid':99999999,'start_ticks':'0','boot_id':'fixture-idle'};atomic(batch/'controller.json',state)
    atomic(batch/'resume-resolution.json',{'prior_dispatch_id':state['dispatch_id'],'reason':'Injected storage/registration fault removed; retained UUIDs and saved outputs; resume unused slots.'})
    # Do not erase the repeated429 evidence. During recovery it is preserved again, but the synthetic provider is now known safe.
    def recovered_collector(root,c,row,r):
        result=collector(root,c,row,r)
        if row['execution_order']<=5:return {'may_continue':True,'stop_reason':''}
        return result
    second=run_controller(batch,command,recovered_collector,evaluator,validity,resume=True)
    _,after=load(batch);assert all(next(r for r in after['runs'] if r['planned_run']==slot)['run_id']==rid for slot,rid in before.items())
    assert read(batch/'runs'/failed[0]['planned_run']/'surrogate-result.json')==fixed
    registry=read(validity)['attempts'];assert len({r['evaluation_id'] for r in registry})==len(registry)
    actual=[r for r in after['runs'] if r['run_id']];assert len(actual)<40 and all(r['status']=='awaiting_review' for r in actual)
    events=[json.loads(l) for l in (batch/'pipeline-events.jsonl').read_text().splitlines()]
    starts=[e['run_id'] for e in events if e['event']=='implementation_started'];assert len(starts)==len(set(starts))==len(actual)
    stopped=[e['run_id'] for e in events if e['event']=='implementation_stopped'];assert stopped!=starts
    first_five=[r['run_id'] for r in sorted(actual,key=lambda r:r['execution_order'])[:5]]
    first_five_stops=[rid for rid in stopped if rid in first_five]
    assert first_five_stops==list(reversed(first_five)),first_five_stops
    active=set();occupied=set();evaluating=set();max_active=max_occupied=max_evaluating=0
    for e in events:
        rid=e.get('run_id');kind=e['event']
        if kind=='implementation_started':active.add(rid);occupied.add(rid)
        elif kind=='implementation_stopped':active.discard(rid)
        elif kind=='preserved_and_restored':occupied.discard(rid)
        elif kind=='evaluation_started':
            evaluating.add(rid)
            if not e['generation_done']:assert len(evaluating)<=1
        elif kind in ('evaluation_preserved','evaluation_failed'):evaluating.discard(rid)
        max_active=max(max_active,len(active));max_occupied=max(max_occupied,len(occupied));max_evaluating=max(max_evaluating,len(evaluating))
    assert max_active<=5 and max_occupied<=5 and max_evaluating<=4
    first_events=events[:next(i for i,e in enumerate(events) if e['event']=='controller_finished')+1]
    stop_events=[e for e in first_events if e['event'] in ('collection_failed','stop_new_starts') or (e['event']=='preserved_and_restored' and not e['may_continue'])]
    assert stop_events
    first_stop_at=min(e['at'] for e in stop_events)
    assert not any(e['event']=='implementation_started' and e['at']>first_stop_at for e in first_events)
    if scenario=='retention':
        assert any(e['event']=='collection_failed' for e in first_events)
        assert read(batch/'runs'/next(r['planned_run'] for r in actual if r['execution_order']==2)/'fixture-proof.json')['http_codes']==[429,429]
    children=[r for r in actual if r.get('fallback_of')]
    if scenario=='fallback':
        assert len(children)==2 and len({r['fallback_of'] for r in children})==2
        assert all(r['model_id']==MODELS[1] for r in children)
    for r in actual:
        ref=read(batch/'runs'/r['planned_run']/'archive-ref.json');verify(base/'archive',ref['package_id'],ref['sha256'])
    proof={'scenario':scenario,'model_calls':0,'real_credentials':False,'client':'synthetic HTTP client in Docker; native CLI verified separately',
        'started':len(actual),'unstarted':40-len(actual),'maximum':40,'start_ids_unique':True,'out_of_order_completion':True,
        'first_five_stopped_in_exact_reverse_order':True,
        'max_implementation_processes':max_active,'max_occupied_slots':max_occupied,'max_evaluations':max_evaluating,
        'no_new_start_after_observed_stop_until_explicit_resume':True,
        'first_stop_reason':first['stop_reason'],'second_stop_reason':second['stop_reason'],'resumed_without_reusing_started_slots':True,
        'saved_docker_evaluation_reused_after_registration_failure':True,'all_actual_originals_verified':True,'fallback_children':len(children),
        'controller_sha256':digest(ROOT/'scripts/parallel_acquisition.py'),'script_sha256':digest(Path(__file__))}
    atomic(base/'evidence.json',proof);print(json.dumps(proof),flush=True)

def registration_resume(base):
    """Exercise the production evaluate_run resume branch with a Docker-produced fixture output."""
    from test_telemetry_link import fixture
    from copilot_batch import evaluate_run
    base.mkdir(parents=True);r=base/'run';rid,_=fixture(r);eid=str(uuid.uuid4());private=base/'private'
    manifest=read(r/'manifest.json');manifest['environment']={'image':GATEWAY_IMAGE};atomic(r/'manifest.json',manifest)
    private.mkdir();(private/'run.mjs').write_text('Synthetic evaluator fixture; never invoked by evaluate_run.')
    (private/'package-lock.json').write_text('{}');atomic(private/'case-manifest.json',read(ROOT/'evaluation/case-manifest.json'))
    atomic(r/'usage.json',{'usage_complete':True,'total_tokens':27,'observed_tokens':27})
    result=private/'evaluations'/eid/'result';result.mkdir(parents=True);(result/'evaluator-snapshot').mkdir()
    (result/'evaluator-snapshot/requirements-ledger.json').write_bytes((ROOT/'evaluation/requirements-ledger.json').read_bytes())
    sub=digest(r/'snapshot.json');meta={'run_id':rid,'submission_hash':sub,'evaluator_hash':'synthetic-fixture-v1','ledger_hash':digest(ROOT/'evaluation/requirements-ledger.json')}
    atomic(base/'metadata.json',meta)
    producer="import pathlib,json; p=pathlib.Path('/result'); m=json.loads(pathlib.Path('/metadata.json').read_text()); ledger=json.loads((p/'evaluator-snapshot/requirements-ledger.json').read_text()); rows=[dict(run_id=m['run_id'],evaluation_id=i['evaluation_id'],case_id=c,status='blocked',score_version=m['evaluator_hash'],submission_hash=m['submission_hash']) for i in ledger['items'] for c in (('lower','upper') if i['evaluation_id']=='T-006-05' else ('main',))]; (p/'results.jsonl').write_text(''.join(json.dumps(r)+'\\n' for r in rows)); (p/'summary.json').write_text(json.dumps(dict(m,kind='evaluation',outcome='server_unavailable',quality=0,counts={'denominator':57,'pass':0,'fail':0,'blocked':57,'error':0})))"
    net='sample1-drill-register-'+eid;docker('network','create','--internal',net)
    app=docker('create','--network',net,GATEWAY_IMAGE,'python','-c','pass');docker('start','-a',app)
    researcher=docker('create','--network',net,'--read-only','--mount',f'type=bind,source={result},target=/result',
        '--mount',f'type=bind,source={base}/metadata.json,target=/metadata.json,readonly',GATEWAY_IMAGE,'python','-c',producer)
    docker('start','-a',researcher)
    resources={'evaluation_id':eid,'output':str(result),'researcher_container':researcher,'app_container':app,'network':net}
    atomic(result.parent/'resources.json',resources)
    atomic(r.parent/'evaluation-jobs/active.json',{'run_id':rid,'evaluation_id':eid,'submission_hash':sub,'score_version':'synthetic-fixture-v1'})
    validity=private/'validity.json';atomic(validity,{'schema_version':1,'attempts':[]})
    scope=base/'scope.json';atomic(scope,{'preservation':{'archive':{'linux':str(base/'archive'),'windows':str(base/'archive')}}})
    config={'batch_schema':2,'score_version':'synthetic-fixture-v1','evaluator_files':{'run.mjs':digest(private/'run.mjs')},'authorization_file':str(scope),'measurement_review_required':True}
    lock=validity.with_suffix('.json.lock');lock.write_text('Injected registration interruption')
    original_run=subprocess.run;calls=[]
    def guard(args,**kwargs):
        calls.append(args)
        assert args[0]=='docker' and args[1] in ('rm','network'),'Resume attempted a new helper or evaluation process'
        return original_run(args,**kwargs)
    hashes={n:digest(result/n) for n in ('summary.json','results.jsonl')}
    with patch('copilot_batch.subprocess.run',side_effect=guard):
        try:evaluate_run(base,config,{'run_id':rid},r,private,GATEWAY_IMAGE,validity)
        except FileExistsError:pass
        else:raise AssertionError('Registration fault was not exercised')
        lock.unlink()
        answer=evaluate_run(base,config,{'run_id':rid},r,private,GATEWAY_IMAGE,validity)
    assert answer['evaluation_id']==eid and len(read(validity)['attempts'])==1
    assert {n:digest(result/n) for n in hashes}==hashes
    assert read(r/'evaluation-ref.json')['submission_hash']==sub
    assert (r/'evaluation-restoration.json').exists()
    proof={'model_calls':0,'v6_assertions_executed':False,'docker_generated_result_records':58,'production_evaluate_run_resume_verified':True,
        'registration_interruption_injected':True,'evaluation_uuid_reused':eid,'submission_hash':sub,'result_hashes_unchanged':hashes,
        'helper_or_evaluator_restarts':0,'cleanup_commands':len(calls),'registered_attempts':1,'archived_and_restored':True}
    atomic(base/'evidence.json',proof);print(json.dumps(proof),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--scenario');p.add_argument('--output',type=Path);a=p.parse_args()
    if a.worker:worker(a.worker.resolve(),a.scenario)
    else:
        if not a.output:raise ValueError('--output required')
        for scenario in ('fallback','retention'):campaign(a.output.resolve()/scenario,scenario)
        registration_resume(a.output.resolve()/'registration-resume')
