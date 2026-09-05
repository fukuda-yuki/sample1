"""Dedicated internal worker network plus fixed-endpoint model gateway."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid
from gateway_usage import collect
from run_experiment import run, write_json

GATEWAY_IMAGE = 'python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea'


def execute(distribution, config, output, auth, prompt=None):
    run_id = str(uuid.uuid4())
    network = 'sample1-private-' + run_id
    gateway = 'sample1-gateway-' + run_id
    script = Path(__file__).with_name('model_gateway.py').resolve()
    with tempfile.TemporaryDirectory(prefix='sample1-usage-') as temp:
        usage = Path(temp)
        uid, gid = os.getuid(), os.getgid()
        try:
            subprocess.run(['docker', 'network', 'create', '--internal',
                            '--opt', 'com.docker.network.bridge.gateway_mode_ipv4=isolated',
                            '--label', 'sample1.run_id=' + run_id,
                            network], check=True, capture_output=True)
            subprocess.run(['docker', 'create', '--name', gateway, '--network', 'bridge',
                            '--user', f'{uid}:{gid}', '--read-only', '--cap-drop', 'ALL',
                            '--security-opt', 'no-new-privileges', '--env', 'PYTHONDONTWRITEBYTECODE=1',
                            '--env', 'RUN_ID=' + run_id, '--env', 'MODEL_ID=' + config['model_id'],
                            '--env', 'EFFORT=' + config['effort'],
                            '--mount', f'type=bind,source={auth.resolve()},target=/secrets/auth.json,readonly',
                            '--mount', f'type=bind,source={script},target=/gateway.py,readonly',
                            '--mount', f'type=bind,source={usage},target=/usage',
                            GATEWAY_IMAGE, 'python', '/gateway.py'], check=True, capture_output=True)
            subprocess.run(['docker', 'network', 'connect', '--alias', 'model-gateway', network, gateway],
                           check=True, capture_output=True)
            subprocess.run(['docker', 'start', gateway], check=True, capture_output=True)
            time.sleep(1)
            instruction = prompt or 'Read /workspace/RUN_CONTRACT.md and /workspace/spec.md. Complete implementation. Follow the supplied instructions.'
            command = ['codex', 'exec', '--ignore-user-config', '--ignore-rules', '--skip-git-repo-check',
                       '--json', '--dangerously-bypass-approvals-and-sandbox',
                       '-m', config['model_id'], '-c', 'model_reasoning_effort=' + json.dumps(config['effort']),
                       '-c', 'model_provider="research"',
                       '-c', 'model_providers.research={name="Research",base_url="http://model-gateway:8080",wire_api="responses",requires_openai_auth=false}',
                       '-c', 'web_search="disabled"', '-c', 'features.multi_agent=false',
                       '-c', 'check_for_update_on_startup=false', instruction]
            import shlex
            bootstrap = ('mkdir -p /home/agent/.codex /home/agent/.nuget/NuGet && '
                         'printf %s \'<configuration><packageSources><clear /></packageSources></configuration>\' '
                         '> /home/agent/.nuget/NuGet/NuGet.Config && '
                         'cp -r /opt/npm-cache /tmp/npm-cache && '
                         'export npm_config_offline=true npm_config_audit=false && exec ')
            config = dict(config, command=['sh', '-c', bootstrap + shlex.join(command)])
            config['environment'] = dict(config['environment'], gateway_image=GATEWAY_IMAGE,
                                         gateway_sha256=__import__('hashlib').sha256(script.read_bytes()).hexdigest(),
                                         network_policy='dedicated-internal-fixed-responses-gateway')
            result = run(distribution, config, output, network=network, run_id_override=run_id)
            # Terminal SSE usage normally arrives before CLI exits. Give disconnected streams a bounded drain.
            for _ in range(10):
                summary = collect(usage)
                if summary['usage_complete']:
                    break
                time.sleep(1)
            subprocess.run(['docker', 'stop', '--time', '2', gateway], capture_output=True, timeout=10)
            shutil.copytree(usage, output / 'raw-usage')
            write_json(output / 'usage.json', collect(usage))
            return result
        except (OSError, subprocess.SubprocessError, ValueError):
            if not output.exists():
                failure_config = dict(config, command=['false'])
                result = run(distribution, failure_config, output, run_id_override=run_id, setup_failure=True)
                write_json(output / 'usage.json', collect(usage))
                return result
            raise
        finally:
            for cleanup in (['docker', 'rm', '-f', gateway], ['docker', 'network', 'rm', network]):
                try:
                    subprocess.run(cleanup, capture_output=True, timeout=30)
                except (OSError, subprocess.SubprocessError):
                    pass  # Run manifest remains available even when Docker is unavailable.


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('distribution', type=Path)
    p.add_argument('config', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--auth', required=True, type=Path)
    p.add_argument('--smoke-prompt')
    a=p.parse_args()
    result=execute(a.distribution,json.loads(a.config.read_text()),a.output,a.auth,a.smoke_prompt)
    print(json.dumps({'run_id':result['run_id'],'end_reason':result['end_reason']}))
