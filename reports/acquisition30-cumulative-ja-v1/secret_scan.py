"""Check exact gateway credential absence without exposing its value or hash."""
from pathlib import Path
import argparse,json,subprocess
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];WORK=ROOT/'results/acquisition20-20260911'
ARCHIVE=Path('/mnt/c/Users/mwam0/ResearchArchives/sample1')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def contains(path,secret):
    overlap=b''
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            data=overlap+chunk
            if secret in data:return True
            overlap=data[-max(len(secret)-1,0):]
    return False
def main(key,publication_only=False):
    key=key.resolve(strict=True)
    secret=key.read_bytes().strip()
    if len(secret)<16:raise ValueError('Expected the existing gateway credential, never a printed value')
    files=set();packages=set()
    for name in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'):
        if name and (ROOT/name).is_file():files.add(ROOT/name)
    files.update(p for p in BASE.rglob('*') if p.is_file())
    for row in ([] if publication_only else read(WORK/'batch/run-index.json')['runs']):
        if not row['run_id']:continue
        run=WORK/'batch/runs'/row['planned_run']/'attempt'
        for name in ('inputs','frozen','raw-usage','telemetry','management-source','measurements'):
            files.update(p for p in (run/name).rglob('*') if p.is_file())
        files.update(p for p in run.iterdir() if p.is_file())
        for name in ('preservation.json','linked-preservation.json','evaluation-preservation.json'):
            if (run/name).exists():packages.add(read(run/name)['package_id'])
    for name in (() if publication_only else ('analysis-reference.json','report-runtime-reference.json')):
        if (WORK/name).exists():packages.add(read(WORK/name)['package_id'])
    # Runtime libraries/images predate the credential; scan the newly created model/evaluation originals.
    for package in packages:
        if package.startswith('report-runtime-'):continue
        directory=ARCHIVE/'packages'/package
        files.add(directory/'package.json');files.update(p for p in (directory/'payload').rglob('*') if p.is_file())
    matches=[];byte_count=0
    for p in sorted(files):
        # Entries already come from absolute repository/archive roots. Avoid resolving
        # every ancestor again; linked content, if any, is still checked byte for byte.
        if p.absolute()==key:raise ValueError('A publication/archive scope unexpectedly includes the credential file')
        byte_count+=p.stat().st_size
        if contains(p,secret):matches.append(str(p))
    if matches:raise ValueError('Credential present in '+str(len(matches))+' files: '+json.dumps(matches))
    proof={'exact_credential_absent':True,'files_scanned':len(files),'bytes_scanned':byte_count,'new_archive_packages':len(packages),
        'scope':('Final publication files: tracked repository files and every new report file; original/archive payloads are covered by the separate full scan.' if publication_only else 'Tracked repository files, new report files, new frozen inputs/source/logs/usage/telemetry, and new Run/evaluation/analysis archive payloads. Runtime images predate this temporary credential.'),
        'publication_only':publication_only,
        'credential_value_or_hash_disclosed':False,'model_calls':0}
    name='publication-secret-scan.json' if publication_only else 'secret-scan.json'
    (BASE/'checks').mkdir(exist_ok=True);(BASE/'checks'/name).write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--key-file',type=Path,required=True);p.add_argument('--publication-only',action='store_true');a=p.parse_args();main(a.key_file,a.publication_only)
