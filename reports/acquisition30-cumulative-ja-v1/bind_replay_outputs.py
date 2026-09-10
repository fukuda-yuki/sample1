"""Bind completed restored-only comparisons to current output hashes."""
from pathlib import Path
import argparse,hashlib,json
from archive_and_replay import database_rows

BASE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def logical(p):return hashlib.sha256(json.dumps(database_rows(p),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def main(raw_output,report_output):
    proofs=sorted((BASE/'checks').glob('cumulative-restored-replay-*.json'))
    assert len(proofs)==1,'Select the matching completed replay explicitly if later versions are added'
    report_proof=read(proofs[0]);raw_proof=read(BASE/'checks/raw-restored-replay.json')
    assert (report_output/'container-evidence.json').is_file() and (raw_output/'container-evidence.json').is_file()
    bindings={}
    for name in report_proof['identical_outputs']:
        expected=BASE/name;actual=report_output/name
        fun=logical if expected.suffix=='.sqlite' else sha
        assert fun(expected)==fun(actual),name
        bindings[name]={'comparison':'logical SQLite content' if expected.suffix=='.sqlite' else 'file bytes',
                        'sha256':fun(expected)}
    expected=BASE.parents[1]/'results/acquisition20-20260911/report-export'
    raw_bindings={}
    for name in [*raw_proof['identical_files'],'analysis.sqlite']:
        fun=logical if name.endswith('.sqlite') else sha
        assert fun(expected/name)==fun(raw_output/'export'/name),name
        raw_bindings[name]={'comparison':'logical SQLite content' if name.endswith('.sqlite') else 'file bytes','sha256':fun(expected/name)}
    record={'kind':'completed-replay-output-bindings',
        'cumulative_proof':str(proofs[0].relative_to(BASE)),'cumulative_proof_sha256':sha(proofs[0]),
        'raw_proof':'checks/raw-restored-replay.json','raw_proof_sha256':sha(BASE/'checks/raw-restored-replay.json'),
        'cumulative_outputs':bindings,'raw_outputs':raw_bindings,
        'raw_output_directory':str(raw_output.resolve()),'cumulative_output_directory':str(report_output.resolve()),
        'new_model_calls':0,'new_evaluations':0}
    (BASE/'checks/replay-output-bindings.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cumulative_outputs':len(bindings),'raw_outputs':len(raw_bindings),'all_equal':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw-output',type=Path,required=True);p.add_argument('--report-output',type=Path,required=True)
    a=p.parse_args();main(a.raw_output,a.report_output)
