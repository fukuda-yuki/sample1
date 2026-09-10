"""Archive completed originals, then regenerate from restored-only Docker mounts."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from preserve import read,digest,pack,restore,verify_receipt,write_new,tree,content_equal
from copilot_analysis_archive import preserve_analysis,restore_analysis

ARCHIVE=Path('/mnt/c/Users/mwam0/ResearchArchives/sample1')
WORK=ROOT/'results/acquisition20-20260911'
IMAGE='mcr.microsoft.com/playwright@sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d'

def database_rows(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        names=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in names}

def stopped():
    c=read(WORK/'batch/controller.json');index=read(WORK/'batch/run-index.json')
    if c['status']!='stopped' or any(r['status'] in ('running','reserved','collecting','evaluating','awaiting_collection') for r in index['runs']):
        raise ValueError('Do not archive a changing acquisition corpus')

def runtime():
    ref_file=WORK/'report-runtime-reference.json';destination=WORK/'restored-report-runtime'
    if not ref_file.exists():
        sites=Path(sys.prefix)/'lib/python3.12/site-packages'
        common=read(ROOT/'results/go-muse12-20260909/common-reference.json')
        ref=pack(ARCHIVE,'report-runtime-'+str(uuid.uuid4()),
            {'site-packages':sites,'YuGothR.ttc':Path('/mnt/c/Windows/Fonts/YuGothR.ttc')},
            metadata={'kind':'offline-report-runtime','python':'3.12.3','image':IMAGE},references=[common])
        write_new(ref_file,ref)
    ref=read(ref_file)
    claim=destination.parent/('.'+destination.name+'.restore-request.json')
    if destination.is_dir() and claim.exists():
        binding=read(claim)
        if binding.get('status')=='completed':
            if binding['reference']!=ref or binding['destination']!=str(destination.absolute()):
                raise ValueError('Restored runtime binding changed')
            # Reuse the completed copy, checking both archived and restored bytes once.
            # Calling restore again would also repeat copying checks and chmod every library file.
            receipt=binding['receipt'];verified=verify_receipt(ARCHIVE,receipt)
            if verified['reference']!=ref or verified['restored_to']!=str(destination.absolute()):
                raise ValueError('Runtime receipt binding changed')
            expected=read(ARCHIVE/'packages'/ref['package_id']/'package.json')['files']
            if not content_equal(tree(destination),expected):raise ValueError('Restored runtime changed')
            proof={'runtime_reference':ref,'original_restoration':receipt,'file_count':len(expected),
                'archive_and_restored_bytes_reverified':True,'copy_or_mode_reapplication':False}
            (BASE/'checks/runtime-confirmations').mkdir(parents=True,exist_ok=True)
            write_new(BASE/'checks/runtime-confirmations'/('verified-'+str(uuid.uuid4())+'.json'),proof)
            return destination,ref
    receipt=restore(ARCHIVE,ref,destination,resume=True)
    write_new(WORK/('report-runtime-restoration-'+str(uuid.uuid4())+'.json'),receipt)
    verify_receipt(ARCHIVE,receipt)
    return destination,ref

def docker(command,mounts,runtime_root,workdir='/work'):
    args=['docker','run','--rm','--network','none','--read-only','--tmpfs','/tmp:rw,size=1g',
        '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/runtime/site-packages',
        '-e','MPLCONFIGDIR=/tmp/matplotlib','-e','REPORT_FONT=/runtime/YuGothR.ttc',
        '-v',str(runtime_root.resolve())+':/runtime:ro','-w',workdir]
    for host,container,mode in mounts:args.extend(['-v',str(host.resolve())+':'+container+':'+mode])
    result=subprocess.run(args+[IMAGE,*command],check=True,capture_output=True,text=True)
    return result.stdout.strip()

def raw_replay(runtime_root,runtime_ref):
    # Raw packages keep private traces and tests inside the independent archive.
    ref_file=WORK/'analysis-reference.json'
    if not ref_file.exists():
        write_new(ref_file,preserve_analysis(WORK/'batch',WORK/'review/validity.json',ARCHIVE))
    ref=read(ref_file);destination=WORK/('restored-analysis-'+str(uuid.uuid4()))
    mapping=restore_analysis(ARCHIVE,ref,destination)
    out=WORK/('raw-replay-output-'+str(uuid.uuid4()));out.mkdir()
    script='''import pathlib,sys,json
p=pathlib.Path('/restored/payload')
sys.path.insert(0,str(p/'management/scripts'))
from copilot_batch import export
locations=json.loads((p/'evaluation-locations.json').read_text())
for value in locations.values():
 assert not pathlib.Path(value['original_directory']).exists()
try:
 export(p/'batch',p/'validity.json',output=pathlib.Path('/output/without-map'))
except (FileNotFoundError,PermissionError): pass
else: raise AssertionError('Original evaluation unexpectedly accessible')
counts=export(p/'batch',p/'validity.json',output=pathlib.Path('/output/export'),restoration_map=pathlib.Path('/restored/restoration-map.json'))
pathlib.Path('/output/container-evidence.json').write_text(json.dumps({'original_evaluation_paths_absent':len(locations),'network':'none','original_workspace_mounted':False,'counts':counts},indent=2))
print(json.dumps(counts))
'''
    stdout=docker(['python3','-B','-c',script],[(destination,'/restored','ro'),(out,'/output','rw')],runtime_root,workdir='/output')
    expected=WORK/'report-export';actual=out/'export'
    matched=[]
    for name in ('runs.csv','missing-runs.csv','test-results.jsonl','provenance.json'):
        assert digest(expected/name)==digest(actual/name),name;matched.append(name)
    assert database_rows(expected/'analysis.sqlite')==database_rows(actual/'analysis.sqlite')
    record={'kind':'additional-originals-restored-export','reference':ref,'restoration_map_sha256':digest(mapping),
        'runtime_reference':runtime_ref,'image':IMAGE,'identical_files':matched,'sqlite_logically_identical':True,
        'docker':read(out/'container-evidence.json'),'model_calls':0,'evaluations':0,'stdout':stdout}
    (BASE/'checks').mkdir(exist_ok=True);write_new(BASE/'checks/raw-restored-replay.json',record)
    print(json.dumps({'raw_restored_replay':True,'output':str(out)}))

def report_replay(runtime_root,runtime_ref):
    allowed=['source','source-manifest.json','analysis-policy.json','analyze.py','query_evidence.py','queries.sql','render_figures.py','build_supplement.py','reviews']
    sources={name:BASE/name for name in allowed}
    ref=pack(ARCHIVE,'cumulative-report-inputs-'+str(uuid.uuid4()),sources,
        metadata={'kind':'cumulative-offline-analysis','model_calls':0,'evaluations':0},references=[runtime_ref])
    destination=WORK/('restored-cumulative-inputs-'+str(uuid.uuid4()))
    receipt=restore(ARCHIVE,ref,destination);verify_receipt(ARCHIVE,receipt)
    out=WORK/('cumulative-replay-output-'+str(uuid.uuid4()));out.mkdir()
    script='''import pathlib,subprocess,json
assert not pathlib.Path('/mnt/c/Users/mwam0/Documents/ls/sample1').exists()
assert not pathlib.Path('/mnt/c/Users/mwam0/ResearchArchives/sample1').exists()
assert not pathlib.Path('/mnt/c/Users/mwam0/Documents/ls/sample1-private-eval-linux').exists()
for args in [['/work/analyze.py','--output','/output/data'],['/work/query_evidence.py','--database','/output/data/analysis.sqlite','--output','/output/data/sql-evidence.json'],['/work/render_figures.py','--data','/output/data/results.json','--output','/output/figures'],['/work/build_supplement.py','--data','/output/data','--output','/output/supplement.md']]:
 subprocess.run(['python3','-B',*args],check=True)
pathlib.Path('/output/container-evidence.json').write_text(json.dumps({'original_paths_absent':True,'network':'none','only_restored_inputs_code_and_runtime_mounted':True}))
'''
    stdout=docker(['python3','-B','-c',script],[(destination,'/work','ro'),(out,'/output','rw')],runtime_root)
    identical=[]
    for folder in ('data','figures'):
        expected={p.name:p for p in (BASE/folder).iterdir() if p.is_file() and p.suffix in ('.csv','.json','.sqlite','.png','.svg')}
        actual={p.name:p for p in (out/folder).iterdir() if p.is_file()}
        assert set(expected)==set(actual),(folder,set(expected)^set(actual))
        for name,p in expected.items():
            if p.suffix=='.sqlite':assert database_rows(p)==database_rows(actual[name])
            else:assert digest(p)==digest(actual[name]),folder+'/'+name
            identical.append(folder+'/'+name)
    assert digest(BASE/'supplement.md')==digest(out/'supplement.md')
    identical.append('supplement.md')
    record={'kind':'cumulative-restored-analysis','reference':ref,'restoration':receipt,
        'runtime_reference':runtime_ref,'image':IMAGE,'identical_outputs':identical,'sqlite_logically_identical':True,
        'docker':read(out/'container-evidence.json'),'model_calls':0,'evaluations':0,'stdout':stdout}
    (BASE/'checks').mkdir(exist_ok=True)
    write_new(BASE/'checks'/('cumulative-restored-replay-'+str(uuid.uuid4())+'.json'),record)
    print(json.dumps({'cumulative_restored_replay':True,'output':str(out),'outputs':len(identical)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['raw','report']);a=p.parse_args();stopped();rt,ref=runtime()
    if a.stage=='raw':raw_replay(rt,ref)
    else:report_replay(rt,ref)
