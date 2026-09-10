"""Single assigned implementation subprocess; never writes shared research ledgers."""
import argparse
import signal
from pathlib import Path
from preserve import read,digest
from telemetry_link import atomic
from copilot_parallel import load,process_identity
from prepare_workspace import prepare
from run_copilot import execute


def main(assignment_file,secret):
    a=read(assignment_file);root=Path(a['root']);config,index=load(root)
    row=next(r for r in index['runs'] if r['planned_run']==a['planned_run'])
    if row['run_id']!=a['run_id'] or a['config_sha256']!=index['config_sha256']:
        raise ValueError('Assignment changed')
    directory=assignment_file.parent;run=directory/'attempt'
    atomic(directory/'worker-started.json',dict(run_id=a['run_id'],owner=process_identity()))
    c=dict(config,**{k:row[k] for k in ('planned_run','condition','execution_order')})
    if config.get('phase') == 'data-acquisition':
        from serial_acquisition import slot_config
        c = slot_config(root, config, row)
        atomic(directory/'execution-config.json', c)
    from execution_scope import check_start
    from run_copilot import validate_config
    validate_config(c);check_start(c)
    distribution=directory/'distribution'
    prepare(root/'inputs',row['condition'],distribution,c if c.get('contract_version')==2 else None)
    def stop(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:execute(distribution,c,run,secret,opt_in=True,run_id=a['run_id'])
    finally:
        if (run/'manifest.json').exists() and (run/'usage.json').exists():
            m=read(run/'manifest.json');u=read(run/'usage.json')
            cleanup=read(run/'cleanup-result.json') if (run/'cleanup-result.json').exists() else {}
            atomic(directory/'execution-result.json',dict(run_id=a['run_id'],experiment_id=c['experiment_id'],
                planned_run=a['planned_run'],end_reason=m['end_reason'],producer_stopped=u.get('producer_stopped') is True,
                submission_hash=digest(run/'snapshot.json') if (run/'snapshot.json').exists() else None,
                cleanup_status=cleanup.get('status','not_requested'),preservation=read(run/'preservation.json') if (run/'preservation.json').exists() else None))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('assignment',type=Path);p.add_argument('secret',type=Path)
    a=p.parse_args();main(a.assignment,a.secret)
