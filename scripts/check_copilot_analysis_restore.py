"""Non-model relocation drill over existing synthetic validation originals."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from copilot_batch import export, load, ROOT
from copilot_analysis_archive import preserve_analysis, restore_analysis
from preserve import read, digest, tree, content_equal, write_new


def database_rows(path):
    with closing(sqlite3.connect(path)) as db:
        return {name: sorted(db.execute('SELECT * FROM ' + name).fetchall(), key=repr)
                for name in ('runs','case_results','telemetry_refs','evaluations','provenance')}


def isolated_export(destination, forbidden):
    # File-open audit hook is scoped to this child; never change originals/ACLs.
    # All Python file opens (including native sqlite opens) to source roots fail.
    forbidden=[os.path.normcase(str(Path(p).resolve())) for p in forbidden]
    def guard(event,args):
        if event not in ('open','sqlite3.connect') or not isinstance(args[0],(str,bytes,os.PathLike)):
            return
        path=os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
        if any(path==p or path.startswith(p+os.sep) for p in forbidden):
            raise PermissionError('Source access forbidden by relocation drill')
    sys.addaudithook(guard)
    for path in forbidden:
        try: open(Path(path)/'blocked-probe','rb')
        except PermissionError: pass
        else: raise AssertionError('Source guard did not reject read')
    payload=destination/'payload'
    try: export(payload/'batch',payload/'validity.json',output=destination/'without-map')
    except (PermissionError,FileNotFoundError): pass
    else: raise AssertionError('Original absolute reference unexpectedly accessible')
    result=export(payload/'batch',payload/'validity.json',output=destination/'export',
                  restoration_map=destination/'restoration-map.json')
    write_new(destination/'isolation-evidence.json',{'source_reads_denied':True,
        'unmapped_export_rejected':True,'restored_only_export':True,'counts':result})


def check(source, output, archive=None):
    source=source.resolve(); output=output.resolve()
    config,index=load(source/'batch')
    if not config.get('synthetic') or config.get('phase')!='copilot-validation' or len(index['runs'])!=2:
        raise ValueError('Requires existing synthetic validation two-slot originals')
    output.mkdir(parents=True,exist_ok=False)
    archive=(archive or output/'archive').resolve()
    originals=tree(source)
    # Make a trial source without modifying the old absolute references.
    trial=output/'trial-source'
    shutil.copytree(source/'batch',trial/'batch')
    validity=source/'private-synthetic-eval/validity.json'
    baseline=export(trial/'batch',validity,output=output/'baseline')
    reference=preserve_analysis(trial/'batch',validity,archive)
    write_new(output/'reference.json',reference)
    restore_analysis(archive,reference,output/'restored')
    # Verified task-owned directory only. Existing research originals stay untouched.
    assert trial.resolve().is_relative_to(output)
    trial.rename(output/'trial-source-unavailable')
    assert not trial.exists()
    subprocess.run([sys.executable,str(Path(__file__).resolve()),'--isolated',str(output/'restored'),
                    str(source),str(output/'trial-source-unavailable'),str(archive),str(trial),
                    *(str(ROOT/name) for name in config['input_hashes'])],check=True)
    actual=output/'restored/export'
    for name in ('runs.csv','missing-runs.csv','test-results.jsonl','provenance.json'):
        assert digest(output/'baseline'/name)==digest(actual/name),name
    assert database_rows(output/'baseline/analysis.sqlite')==database_rows(actual/'analysis.sqlite')
    assert content_equal(tree(source),originals), 'Historical originals changed'
    evidence={'kind':'synthetic-analysis-relocation','model_called':False,'real_acceptance':False,
              'trial_source_absent':True,'historical_originals_unchanged':True,
              'csv_identical':True,'sqlite_all_tables_logically_identical':True,
              'package':reference,**read(output/'restored/isolation-evidence.json')}
    assert evidence['counts']==baseline
    write_new(output/'evidence.json',evidence)
    return evidence


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--isolated':
        isolated_export(Path(sys.argv[2]),sys.argv[3:])
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
        parser.add_argument('--archive',type=Path)
        args=parser.parse_args();print(json.dumps(check(args.source,args.output,args.archive)))
