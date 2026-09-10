"""Archive and restore only the new reanalysis inputs, then recompute offline without original paths."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys,uuid
from analyze import BASE,read,sha,write_json
from verify import logical
ROOT=BASE.parents[1]
IMAGE='mcr.microsoft.com/playwright@sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime',type=Path,default=ROOT/'results/acquisition20-20260911/restored-report-runtime');ap.add_argument('--archive',type=Path,default=Path('/mnt/c/Users/mwam0/ResearchArchives/sample1'));a=ap.parse_args()
    sys.path.insert(0,str(ROOT/'scripts'));from preserve import pack,restore,verify_receipt
    work=ROOT/'results/reanalysis-v3'/('replay-'+str(uuid.uuid4()));stage=work/'stage';stage.mkdir(parents=True)
    for name in ('source','evidence'):shutil.copytree(BASE/name,stage/name)
    scripts=['analyze.py','query_evidence.py','build_support.py','render_figures.py','queries.sql','source-manifest.json','analysis-plan.json']
    for name in scripts:shutil.copyfile(BASE/name,stage/name)
    (stage/'data').mkdir();shutil.copyfile(BASE/'data/selected-request-trajectories.csv',stage/'data/selected-request-trajectories.csv')
    runtime_ref=read(ROOT/'results/acquisition20-20260911/report-runtime-reference.json')
    ref=pack(a.archive,'reanalysis-v3-inputs-'+str(uuid.uuid4()),{'inputs':stage},metadata={'kind':'60-Run-two-condition-reanalysis-inputs','runtime_reference':runtime_ref,'model_runs':0,'evaluator_runs':0})
    restored=work/'restored';receipt=restore(a.archive,ref,restored);verify_receipt(a.archive,receipt)
    inp=restored/'inputs';output=work/'output';output.mkdir()
    driver="""from pathlib import Path
import subprocess,shutil,json
assert not Path('/mnt/c/Users/mwam0/Documents/ls/sample1').exists()
assert not Path('/mnt/c/Users/mwam0/ResearchArchives/sample1').exists()
assert not Path('/mnt/c/Users/mwam0/Documents/ls/sample1-private-eval-linux').exists()
Path('/output/data').mkdir()
shutil.copyfile('/inputs/data/selected-request-trajectories.csv','/output/data/selected-request-trajectories.csv')
commands=[['analyze.py','--source','/inputs/source','--output','/output/data'],['query_evidence.py','--data','/output/data'],
 ['build_support.py','--data','/output/data','--output','/output'],['render_figures.py','--data','/output/data','--output','/output/figures','--font','/runtime/YuGothR.ttc']]
for args in commands:
 result=subprocess.run(['python3','-B','/inputs/'+args[0],*args[1:]],capture_output=True,text=True)
 if result.returncode:raise RuntimeError(result.stdout+'\\n'+result.stderr)
print(json.dumps({'network':'none','original_paths_absent':True,'only_restored_inputs_and_runtime':True,'model_runs':0,'evaluations':0}))
"""
    cmd=['docker','run','--rm','--network','none','--read-only','--tmpfs','/tmp:rw,size=1g',
      '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/runtime/site-packages','-e','MPLCONFIGDIR=/tmp/matplotlib',
      '-v',str(a.runtime.resolve())+':/runtime:ro','-v',str(inp.resolve())+':/inputs:ro','-v',str(output.resolve())+':/output:rw',IMAGE,'python3','-B','-c',driver]
    result=subprocess.run(cmd,capture_output=True,text=True)
    (work/'docker.stdout.txt').write_text(result.stdout);(work/'docker.stderr.txt').write_text(result.stderr)
    if result.returncode:raise RuntimeError(result.stderr[-8000:]+result.stdout[-2000:])
    bindings={}
    for path in sorted(output.rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(output);expected=BASE/rel;fun=logical if path.suffix=='.sqlite' else sha
        assert expected.exists() and fun(path)==fun(expected),str(rel)
        bindings[str(rel)]={'comparison':'logical SQLite' if fun==logical else 'byte equality','sha256':fun(path)}
    proof={'input_archive':ref,'input_restoration':receipt,'runtime_reference':runtime_ref,'docker_image':IMAGE,
      'docker':json.loads(result.stdout),'outputs':bindings,'compared_outputs':len(bindings),'only_source_bound_reanalysis':True,
      'original_report_or_raw_evaluation_not_modified':True,'model_runs':0,'evaluator_runs':0}
    write_json(BASE/'checks/replay.json',proof)
    print(json.dumps({'outputs_matched':len(bindings),'source_only_offline_replay':True,'input_archive':ref,'work':str(work)}))

if __name__=='__main__':main()
