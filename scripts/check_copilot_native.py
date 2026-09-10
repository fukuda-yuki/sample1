"""Real CLI against synthetic server on internal Docker network; no API key/model."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import uuid
from unittest.mock import patch
from run_experiment import run, snapshot, write_json
from run_copilot import worker_command
from run_codex import GATEWAY_IMAGE


def main(image, output, completion=False):
    output.mkdir(parents=True, exist_ok=False)
    run_id = str(uuid.uuid4())
    dist = output / 'distribution'
    (dist / 'workspace').mkdir(parents=True)
    (dist / 'workspace/spec.md').write_text('Synthetic probe only.')
    write_json(dist / 'distribution.json', {'files': {k: {'sha256': v} for k,v in snapshot(dist / 'workspace').items()}})
    spool = output / 'server'
    spool.mkdir()
    net, server = 'sample1-native-' + run_id, 'sample1-fake-' + run_id
    def docker(*args):
        return subprocess.run(['docker', *args], check=True, capture_output=True, text=True, timeout=60)
    c = dict(agent='github-copilot-cli', phase='copilot-smoke', experiment_id=str(uuid.uuid4()),
             experiment_version='copilot-synthetic-only', model_id='muse-fixture-contributor-free', effort=None,
             agent_version='1.0.83-5', tool_versions={}, subagent_policy='disabled', execution_order=0,
             environment={'image': image}, budget={'kind':'wall_clock_seconds','value':90,'scope':'container'})
    c['command'] = worker_command(c, run_id)
    if completion:
        c.update(phase='data-acquisition',model_http_503_policy='stop_run',usage_raw_directory=str(spool.resolve()))
        c['command'][-1]='sleep 120 &\n'+c['command'][-1].replace(' && exec ', ' && ')+'; wait'
    try:
        docker('network','create','--internal','--opt','com.docker.network.bridge.gateway_mode_ipv4=isolated',
               '--label','sample1.run_id='+run_id,net)
        docker('run','-d','--name',server,'--network',net,'--network-alias','model-gateway',
               '--env','RUN_ID='+run_id,
               '--user',f'{os.getuid()}:{os.getgid()}', '--read-only','--cap-drop','ALL',
               '--mount',f'type=bind,source={Path(__file__).with_name("fake_responses.py").resolve()},target=/fake.py,readonly',
               '--mount',f'type=bind,source={spool.resolve()},target=/telemetry',GATEWAY_IMAGE,'python','/fake.py')
        # Only this fixed no-upstream fixture bypasses research start reservations.
        with patch('run_experiment.check_start', return_value={'kind':'synthetic-no-upstream'}), patch('run_experiment.reserve_start'):
            result = run(dist,c,output/'run',network=net,run_id_override=run_id)
        shutil.copytree(spool,output/'run/raw-usage')
        requests=[json.loads(line) for line in (spool/'requests.jsonl').read_text().splitlines()]
        assert len(requests)==2
        from model_gateway import validate_request
        for request in requests:validate_request(request['policy'],c['model_id'],None)
        assert all(not set(r['tools']) & {'task','web_fetch','skill','list_agents','read_agent','write_agent'} for r in requests)
        assert (output/'run/frozen/probe.txt').read_text()=='42'
        from telemetry_link import native_to_otlp,inventory,reconcile
        payload,_,problems=native_to_otlp(output/'run/telemetry/native.jsonl')
        usage,sessions,_,calls=reconcile(output/'run/raw-usage',inventory(payload,run_id,c['experiment_id']),run_id)
        assert not problems and sessions==[run_id]
        if completion:
            from gateway_usage import collect
            gateway=collect(output/'run/raw-usage')
            assert gateway['usage_complete'] and gateway['total_tokens']==36
            assert len(calls)==2 and sum(sum(call['tokens']) for call in calls)==36
            assert all(p['reason']=='parent_span_missing' for p in usage['missing'])
            assert result['stop_trigger']=='copilot_completion_declaration'
            assert result['processes_stopped'] and result['submission_fixed'] and result['elapsed_seconds']<60
        else: assert usage['total_tokens']==36
        write_json(output/'run/usage.json',usage)
        write_json(output/'evidence.json', {'kind':'real-cli-fake-provider','model_called':False,
                   'run_id':run_id,'end_reason':result['end_reason'],
                   'file_edit':True,'tool_execution':True,'continuation':True,
                   'delegation_tools_absent':True,'native_response_reconciliation':True,'gateway_total_tokens':36,
                   'completion_boundary_test':completion, 'trace_structure_complete':not usage['missing'],
                   'elapsed_seconds':result['elapsed_seconds'],'actual_exit_code':result['exit_code']})
        print(json.dumps(json.loads((output/'evidence.json').read_text())))
    finally:
        for argv in [('rm','-f',server),('network','rm',net)]:
            subprocess.run(['docker',*argv],capture_output=True,timeout=30)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--image',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--background-completion',action='store_true')
    a=p.parse_args()
    main(a.image,a.output,a.background_completion)
