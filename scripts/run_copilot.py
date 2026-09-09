"""Explicit opt-in Copilot/Zen native Responses entry point (run on Docker host)."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid
from execution_scope import check_start, reserve_start
from run_codex import GATEWAY_IMAGE, validate_distribution, save_usage
from run_experiment import run, write_json
from preserve import pack, read

CLI_VERSION = '1.0.83-5'
PROMPT = 'Read /workspace/RUN_CONTRACT.md and /workspace/spec.md. Complete implementation. Follow the supplied instructions.'
SMOKE = 'Create probe.txt containing 42. Run a shell command that reads it and checks its value. After the tool result, explain the observed value.'


def validate_config(c):
    for key, value in {'agent': 'github-copilot-cli',
                       'agent_version': CLI_VERSION, 'effort': None,
                       'subagent_policy': 'disabled'}.items():
        if c.get(key) != value:
            raise ValueError('Unsupported Copilot setting: ' + key)
    if c.get('provider') == 'opencode-zen':
        valid = (c.get('base_url') == 'https://opencode.ai/zen/v1' and
                 re.fullmatch(r'muse-[a-z0-9.-]+-contributor-free', c.get('model_id') or ''))
    elif c.get('provider') == 'opencode-go':
        valid = (c.get('base_url') == 'https://opencode.ai/zen/go/v1' and
                 c.get('model_id') in ('muse-spark-1.3-contributor', 'muse-spark-1.2-contributor', 'omen-alpha', 'mimo-v2.5'))
    else:
        valid = False
    if not valid:
        raise ValueError('Unsupported fixed provider, endpoint or exact model ID')
    expected_wire = 'completions' if c['model_id'] in ('omen-alpha','mimo-v2.5') else 'responses'
    if c.get('wire_api') != expected_wire:
        raise ValueError('Model wire protocol mismatch')
    uuid.UUID(c['experiment_id'])
    if not c['experiment_version'].startswith('copilot-'):
        raise ValueError('New Copilot experiment version required')
    if not re.fullmatch(r'[a-zA-Z0-9-]+', c['planned_run']):
        raise ValueError('Invalid planned slot')
    if c.get('phase') not in ('comparison', 'copilot-smoke', 'copilot-validation'):
        raise ValueError('Explicit comparison, copilot-smoke or copilot-validation phase required')
    b = c['budget']
    if b['kind'] != 'wall_clock_seconds' or b['scope'] != 'container' or type(b['value']) is not int or b['value'] <= 0:
        raise ValueError('Positive common container budget required')
    if not re.fullmatch(r'(?:[^\s]+@)?sha256:[0-9a-f]{64}', c['environment']['image']):
        raise ValueError('Digest-pinned prepared image required')


def worker_environment(c, run_id):
    return {'COPILOT_HOME': '/home/agent/.copilot', 'COPILOT_PROVIDER_TYPE': 'openai',
            'COPILOT_PROVIDER_BASE_URL': 'http://model-gateway:8080',
            'COPILOT_PROVIDER_WIRE_API': c.get('wire_api','responses'), 'COPILOT_PROVIDER_TRANSPORT': 'http',
            'COPILOT_MODEL': c['model_id'], 'COPILOT_OTEL_EXPORTER_TYPE': 'file',
            'COPILOT_OTEL_FILE_EXPORTER_PATH': '/telemetry/native.jsonl',
            'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT': 'false',
            'OTEL_RESOURCE_ATTRIBUTES': f"run.id={run_id},experiment.id={c['experiment_id']},client.kind=copilot-cli",
            'CI': 'true'}


def worker_command(c, run_id):
    command = ['copilot', '--no-auto-update', '--no-custom-instructions', '--disable-builtin-mcps',
               '--no-ask-user', '--no-remote', '--no-remote-export', '--no-bash-env',
               '--available-tools=view,grep,glob,edit,create,apply_patch,bash,list_bash,write_bash,read_bash,stop_bash',
               '--allow-all-tools', '--output-format', 'json', '--log-level', 'none',
               '--session-id', run_id, '--model', c['model_id'], '-p',
               SMOKE if c['phase'] == 'copilot-smoke' else PROMPT]
    # Version gate happens inside the exact worker image, before any inference.
    bootstrap = ('test "$(copilot --version | head -n 1)" = "GitHub Copilot CLI ' + CLI_VERSION + '." || exit 120; '
                 'cp -R /opt/npm-cache /tmp/npm-cache && '
                 'export npm_config_offline=true npm_config_audit=false && exec ')
    return ['sh', '-c', bootstrap + shlex.join(command)]


def execute(distribution, config, output, secret, *, opt_in=False, run_id=None):
    validate_config(config)
    if not opt_in:
        raise ValueError('Real model execution requires --execute-real-model')
    if not secret.is_file() or not secret.read_text().strip():
        raise ValueError('Gateway-only secret file required')
    check_start(config)
    validate_distribution(distribution, config)
    if output.exists():
        raise ValueError('Output already exists')
    run_id = str(uuid.UUID(run_id)) if run_id else str(uuid.uuid4())
    reserve_start(config, run_id)
    raw = output.parent / '.raw-usage' / run_id
    raw.mkdir(parents=True)
    write_json(raw / 'provenance.json', {'run_id': run_id, 'experiment_id': config['experiment_id']})
    network, gateway = 'sample1-private-' + run_id, 'sample1-gateway-' + run_id
    c = dict(config, command=worker_command(config, run_id), usage_raw_directory=str(raw.resolve()))
    stopped, created, failure = True, False, None
    result = None
    network_created=None
    def docker(*args):
        return subprocess.run(['docker', *args], check=True, capture_output=True, timeout=60)
    try:
        network_created=docker('network', 'create', '--internal', '--opt', 'com.docker.network.bridge.gateway_mode_ipv4=isolated',
               '--label', 'sample1.run_id=' + run_id, network)
        gateway_created=docker('create', '--name', gateway, '--network', 'bridge', '--read-only', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--user', f'{os.getuid()}:{os.getgid()}',
               '--env', 'RUN_ID=' + run_id, '--env', 'MODEL_ID=' + config['model_id'],
               '--env', 'EXPERIMENT_ID=' + config['experiment_id'],
               '--env', 'WIRE_API=' + config['wire_api'],
               '--env', 'MODEL_HTTP_503_POLICY=' + config.get('model_http_503_policy',''),
               '--label', 'sample1.run_id=' + run_id,
               '--env', 'PROVIDER=' + config['provider'], '--env', 'PYTHONDONTWRITEBYTECODE=1',
               '--mount', f'type=bind,source={secret.resolve()},target=/secrets/zen-key,readonly',
               '--mount', f'type=bind,source={Path(__file__).with_name("model_gateway.py").resolve()},target=/gateway.py,readonly',
               '--mount', f'type=bind,source={raw.resolve()},target=/usage',
               GATEWAY_IMAGE, 'python', '/gateway.py')
        c['runtime_resources']={network:network_created.stdout.decode().strip(),gateway:gateway_created.stdout.decode().strip()}
        created, stopped = True, False
        docker('network', 'connect', '--alias', 'model-gateway', network, gateway)
        check_start(c, run_id)
        docker('start', gateway)
        result = run(distribution, c, output, network=network, run_id_override=run_id, _reserved=True)
        from gateway_usage import collect
        for _ in range(10):
            if collect(raw)['usage_complete']:
                break
            time.sleep(1)
        return result
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        failure = type(error).__name__
        if not output.exists():
            run(distribution, c, output, run_id_override=run_id, setup_failure=True, _reserved=True)
        raise
    finally:
        failed_503 = (raw / 'provider-failure.json').exists()
        if created:
            try:
                docker('stop', '--time', '2', c['runtime_resources'][gateway])
            except (OSError, subprocess.SubprocessError):
                pass
            failed_503 = (raw / 'provider-failure.json').exists()
            try:
                if failed_503:
                    stopped = json.loads(docker('inspect',c['runtime_resources'][gateway]).stdout)[0]['State']['Running'] is False
                else:
                    docker('rm', '-f', c['runtime_resources'][gateway])
                    stopped = True
            except (OSError, subprocess.SubprocessError):
                pass
        # A final response can arrive after worker exit while usage is drained.
        # Apply the header signal before publishing the preserved manifest/result.
        failed_503 = (raw / 'provider-failure.json').exists()
        if failed_503:
            provider_failure=read(raw/'provider-failure.json')
            if (provider_failure.get('run_id')!=run_id or provider_failure.get('experiment_id')!=c['experiment_id']
                    or provider_failure.get('http_status')!=503):
                raise ValueError('Provider failure identity/status mismatch')
            if output.exists():
                manifest=read(output/'manifest.json')
                manifest.update(end_reason='provider_unavailable',stop_trigger='model_http_503',provider_failure=provider_failure)
                write_json(output/'manifest.json',manifest)
                if result is not None:result.update(manifest)
        if not failed_503 and network_created:
            try:
                docker('network', 'rm', network_created.stdout.decode().strip())
            except (OSError, subprocess.SubprocessError):
                pass
        save_usage(output, raw, producer_stopped=stopped, error=failure)
        if output.exists():
            scope = read(Path(c['authorization_file']))
            from preservation_gate import archive_root
            sources = {name: output / name for name in ('manifest.json', 'snapshot.json', 'frozen', 'inputs',
                       'raw-usage', 'usage.json', 'telemetry', 'management-source', 'agent.stdout.log', 'agent.stderr.log') if (output / name).exists()}
            receipt = pack(archive_root(scope), 'copilot-' + run_id, sources,
                           metadata={'kind': 'copilot-run', 'run_id': run_id})
            write_json(output / 'preservation.json', receipt)
            if failed_503 and c.get('model_http_503_policy') == 'stop_run_and_cleanup':
                from run_cleanup import cleanup
                try:
                    if not stopped:
                        raise ValueError('Gateway stop unconfirmed')
                    result = cleanup(output,run_id,archive_root(scope),receipt)
                except (ValueError,OSError,subprocess.SubprocessError) as error:
                    result = {'run_id':run_id,'status':'failed','reason':str(error)}
                write_json(output/'cleanup-result.json',result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check', 'run'])
    p.add_argument('config', type=Path)
    p.add_argument('--distribution', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--secret-file', type=Path)
    p.add_argument('--execute-real-model', action='store_true')
    a = p.parse_args()
    c = read(a.config)
    validate_config(c)
    if a.action == 'check':
        try:
            check_start(c)
            print('Settings and start gate valid; no model called. Live connectivity not tested.')
        except (OSError, ValueError, KeyError) as e:
            p.exit(2, str(e) + '\nNo model called.\n')
    else:
        if not all((a.distribution, a.output, a.secret_file)):
            p.error('run requires --distribution, --output and --secret-file')
        print(json.dumps(execute(a.distribution, c, a.output, a.secret_file, opt_in=a.execute_real_model)))
