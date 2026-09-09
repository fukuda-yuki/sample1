"""Delete only a verified Run's stopped runtime after immutable preservation."""
import json
from pathlib import Path
import shutil
import subprocess
from preserve import verify, read, digest


def confirmed_absent(result,kind,name):
    message=result.stderr.strip().casefold()
    identity=name.casefold()
    return bool(result.returncode) and (message.endswith('no such container: '+identity)
        or message.endswith('no such object: '+identity)
        or (kind=='network' and message.endswith('network '+identity+' not found')))


def cleanup(run, run_id, archive, receipt):
    run = Path(run).resolve()
    verify(archive, receipt['package_id'], receipt['sha256'])
    package=read(Path(archive)/'packages'/receipt['package_id']/'package.json')
    if (package['metadata'].get('run_id')!=run_id
            or package['files'].get('snapshot.json',{}).get('sha256')!=digest(run/'snapshot.json')):
        raise ValueError('Preservation does not bind this Run/submission')
    manifest = read(run / 'manifest.json')
    if manifest['run_id'] != run_id or not manifest.get('processes_stopped') or not manifest.get('submission_fixed'):
        raise ValueError('Cleanup requires this stopped and frozen Run')
    actions=[]
    for kind, name in [('container','sample1-'+run_id),('container','sample1-gateway-'+run_id),
                       ('network','sample1-private-'+run_id)]:
        result = subprocess.run(['docker',kind,'inspect',name],capture_output=True,text=True,timeout=30)
        if result.returncode:
            if not confirmed_absent(result,kind,name):
                raise ValueError('Cannot establish runtime absence')
            actions.append({'kind':kind,'name':name,'status':'already_absent'});continue
        resource=json.loads(result.stdout)[0]
        labels=resource['Config'].get('Labels',{}) if kind=='container' else resource.get('Labels',{})
        if labels.get('sample1.run_id') != run_id or (kind=='container' and resource['State']['Running']):
            raise ValueError('Runtime ownership or stop mismatch')
        identity=resource['Id']
        if manifest.get('batch_schema')==2 and manifest.get('runtime_resources',{}).get(name)!=identity:
            raise ValueError('Runtime ID differs from original allocation')
        subprocess.run(['docker',kind,'rm',identity],check=True,capture_output=True,timeout=30)
        actions.append({'kind':kind,'id':identity,'name':name,'status':'removed'})
    workspace=run/'working'
    if workspace.exists():
        if workspace.is_symlink() or workspace.is_junction() or workspace.resolve().parent!=run:
            raise ValueError('Working directory escapes this Run')
        # rmtree removes links themselves without following them; never invoke a shell.
        shutil.rmtree(workspace)
        actions.append({'kind':'directory','name':'working','status':'removed'})
    return {'run_id':run_id,'status':'completed','preservation':receipt,'actions':actions}
