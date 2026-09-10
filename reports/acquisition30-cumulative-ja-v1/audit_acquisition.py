"""Final read-only audit of acquisition bindings and archived/restored bytes."""
from pathlib import Path
import collections
import json
import subprocess
import sys

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from preserve import read,digest,verify_receipt,tree,content_equal
from run_experiment import verify_snapshot
from parallel_acquisition import validate_batch

WORK=ROOT/'results/acquisition20-20260911';ARCHIVE=Path('/mnt/c/Users/mwam0/ResearchArchives/sample1')

def main():
    batch=WORK/'batch';c=read(batch/'experiment.json');index=read(batch/'run-index.json');state=read(batch/'controller.json')
    validate_batch(c,index)
    assert state['status']=='stopped'
    assert not any(r['status'] in ('running','reserved','collecting','evaluating','awaiting_collection') for r in index['runs'])
    cache={};checked=[]
    def verify_restored(receipt):
        data=verify_receipt(ARCHIVE,receipt,cache=cache)
        expected=read(ARCHIVE/'packages'/data['reference']['package_id']/'package.json')['files']
        assert content_equal(tree(Path(data['restored_to'])),expected),data['reference']['package_id']
        return {'package_id':data['reference']['package_id'],'package_sha256':data['reference']['sha256'],'files':len(expected)}
    missing_seen=False
    for row in index['runs']:
        if not row['run_id']:missing_seen=True;continue
        assert not missing_seen,'Out-of-order start'
        run=batch/'runs'/row['planned_run']/'attempt'
        m=read(run/'manifest.json');receipt=read(run.parent/'acquisition-completion.json')
        assert m['run_id']==receipt['run_id']==row['run_id']
        assert m['processes_stopped'] and m['submission_fixed']
        assert digest(run/'manifest.json')==receipt['manifest_sha256']
        assert m['experiment_id']==index['experiment_id'] and m['condition']==row['condition']
        assert m['agent_version']=='1.0.83-5' and m['effort'] is None and m['subagent_policy']=='disabled'
        assert m['environment']['image']=='sha256:d70dc026cbd41542004ed010b6f40650be8dd7f7531fd59fd6a3d05ef3e407cb'
        assert m['budget']['value']==3600
        distribution=run/'inputs/workspace'
        assert {p.name for p in distribution.iterdir()}=={'spec.md','RUN_CONTRACT.md'}
        delivery=read(run/'inputs/distribution.json')['files']
        assert digest(distribution/'spec.md')==delivery['spec.md']['sha256']
        old=ROOT/'results/acquisition10-20260910/batch/runs'/(row['condition']+'-001')/'attempt/inputs/workspace/spec.md'
        assert old.is_file(),old
        assert digest(distribution/'spec.md')==digest(old)
        for filename,item in delivery.items():assert digest(distribution/filename)==item['sha256']
        if m['model_id']=='muse-spark-1.2-contributor':
            assert digest(distribution/'RUN_CONTRACT.md')==digest(ROOT/'reports/acquisition10-reanalysis-ja-v2/source/run-contract.md')
        command=' '.join(m['command']);assert '--available-tools=view,grep,glob,edit,create,apply_patch,bash,list_bash,write_bash,read_bash,stop_bash' in command
        tools=collections.Counter();disabled=False
        for line in (run/'agent.stdout.log').read_text(encoding='utf-8',errors='replace').splitlines():
            if not line.startswith('{'):continue
            try:entry=json.loads(line)
            except json.JSONDecodeError:continue
            # Inspect CLI control records only, never hidden model reasoning.
            if entry.get('type')=='tool.execution_start':tools[entry.get('data',{}).get('toolName')]+=1
            if entry.get('type')=='session.info':
                message=entry.get('data',{}).get('message','')
                disabled|=message.startswith('Disabled tools:') and all(t in message for t in ('list_agents','read_agent','task','write_agent'))
        assert not set(tools)&{'task','list_agents','read_agent','write_agent'},row['planned_run']
        assert disabled,row['planned_run']
        for name,expected in receipt['hashes'].items():assert digest(run/name)==expected,name
        verify_snapshot(run/'frozen',read(run/'snapshot.json'))
        original=verify_restored(receipt['original_restoration']);linked=verify_restored(receipt['linked_restoration'])
        evaluation=None
        if (run/'evaluation-ref.json').exists():
            ref=read(run/'evaluation-ref.json');assert ref['run_id']==row['run_id']
            assert ref['submission_hash']==digest(run/'snapshot.json') and ref['evaluation_id']==row['evaluation_id']
            assert ref['score_version']==c['score_version']
            p=Path(ref['evaluation_directory'])
            assert digest(p/'summary.json')==ref['summary_sha256'] and digest(p/'results.jsonl')==ref['results_sha256']
            evaluation=verify_restored(read(run/'evaluation-restoration.json'))
        checked.append({'run_id':row['run_id'],'planned_run':row['planned_run'],'model_id':m['model_id'],
            'end_reason':m['end_reason'],'exit_code':m['exit_code'],'implementation_subagent_tools_disabled':disabled,
            'executed_tool_counts':dict(tools),'original':original,'linked':linked,'evaluation':evaluation})
    names=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
    owned=[n for n in names if any(r['run_id'] in n or (r.get('evaluation_id') and r['evaluation_id'] in n) for r in index['runs'] if r['run_id'])]
    assert not owned,owned
    for name,expected in read(WORK/'legacy-hashes-before.json').items():assert digest(ROOT/name)==expected,name
    result={'kind':'final-acquisition-audit','experiment_id':index['experiment_id'],'planned':len(index['runs']),
        'started':len(checked),'conditions':dict(collections.Counter(r['planned_run'].split('-')[0] for r in checked)),
        'archived_and_restored_bytes_verified':True,'running_owned_containers':owned,'old_hashes_unchanged':True,
        'shared_archive_verification_cache_entries':len(cache),'runs':checked,'model_calls':0,'evaluations':0}
    (BASE/'checks').mkdir(exist_ok=True)
    (BASE/'checks/acquisition-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='runs'}))

if __name__=='__main__':main()
