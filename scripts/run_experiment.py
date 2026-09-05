"""Stop the whole container before freezing a submission; evaluation is separate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
import uuid


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


EXCLUDED_DIRS = {'node_modules', 'bin', 'obj', '.git', '.codex', '.cache', 'maildrop'}
EXCLUDED_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.db-shm', '.db-wal'}
MANAGEMENT_FILES = ('run_experiment.py', 'run_codex.py', 'model_gateway.py', 'gateway_usage.py', 'normalize_usage.py')


def snapshot(root, source_only=True):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not source_only or d not in EXCLUDED_DIRS)
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError('Links are not accepted in immutable source submissions')
        for name in sorted(files):
            path = Path(directory) / name
            if source_only and path.suffix in EXCLUDED_SUFFIXES:
                continue
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def verify_snapshot(root, expected, source_only=True):
    if snapshot(root, source_only=source_only) != expected:
        raise ValueError('Submission changed')


def run(distribution, config, output, *, network='none', run_id_override=None, setup_failure=False):
    required = ['experiment_version', 'model_id', 'effort', 'agent_version', 'tool_versions',
                'subagent_policy', 'environment', 'budget', 'execution_order', 'command']
    for field in required:
        if field not in config:
            raise ValueError('Missing setting: ' + field)
    budget = config['budget']
    if budget['kind'] != 'wall_clock_seconds' or budget['scope'] != 'container' or budget['value'] <= 0:
        raise ValueError('Only positive container wall-clock limits are supported')
    image = config['environment']['image']
    if not re.fullmatch(r'(?:[^\s]+@)?sha256:[0-9a-f]{64}', image):
        raise ValueError('Pin the prepared image by digest')
    if not isinstance(config['command'], list) or not config['command']:
        raise ValueError('command must be a nonempty argument list')
    output.mkdir(parents=True, exist_ok=False)
    workspace = output / 'working'
    shutil.copytree(distribution / 'workspace', workspace)
    dist = json.loads((distribution / 'distribution.json').read_text(encoding='utf-8'))
    expected = {name: entry['sha256'] for name, entry in dist['files'].items()}
    verify_snapshot(workspace, expected, source_only=False)
    run_id = run_id_override or str(uuid.uuid4())
    name = 'sample1-' + run_id
    management = {'version': 'measurement-control-v2', 'files': {}}
    sources = output / 'management-source'
    sources.mkdir()
    for filename in MANAGEMENT_FILES:
        data = Path(__file__).with_name(filename).read_bytes()
        (sources / filename).write_bytes(data)
        management['files'][filename] = hashlib.sha256(data).hexdigest()
    manifest = dict(config, schema_version=1, run_id=run_id, distribution=dist,
                    started_at=datetime.now(timezone.utc).isoformat(),
                    rerun_of=config.get('rerun_of'), status='running', evaluation=None,
                    management=management)
    write_json(output / 'manifest.json', manifest)
    started = time.monotonic()
    reason, exit_code, stopped = 'environment_failure', None, False
    container_created = False
    budget_waiting = False
    try:
        if setup_failure:
            raise RuntimeError('Gateway setup failed')
        if network != 'none':
            net = subprocess.run(['docker', 'network', 'inspect', network], check=True,
                                 capture_output=True, text=True, timeout=30)
            data = json.loads(net.stdout)[0]
            if (not data['Internal'] or data.get('Labels', {}).get('sample1.run_id') != run_id
                    or data.get('Options', {}).get('com.docker.network.bridge.gateway_mode_ipv4') != 'isolated'):
                raise ValueError('Worker requires a dedicated internal network')
        input_mounts = []
        for relative in dist['files']:
            input_mounts += ['--mount', f'type=bind,source={(workspace / relative).resolve()},target=/workspace/{relative},readonly']
        subprocess.run(['docker', 'create', '--name', name, '--network', network,
                        '--user', f'{os.getuid() if hasattr(os, "getuid") else 1000}:{os.getgid() if hasattr(os, "getgid") else 1000}',
                        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                        '--read-only', '--tmpfs', '/tmp:mode=1777,exec', '--tmpfs', '/home/agent:mode=1777,exec',
                        '--env', 'HOME=/home/agent', '--env', 'CODEX_HOME=/home/agent/.codex',
                        '--mount', f'type=bind,source={workspace.resolve()},target=/workspace',
                        '--workdir', '/workspace', *input_mounts, image, *config['command']],
                       check=True, capture_output=True, timeout=60)
        container_created = True
        subprocess.run(['docker', 'start', name], check=True, capture_output=True, timeout=30)
        remaining = max(0.001, budget['value'] - (time.monotonic() - started))
        budget_waiting = True
        result = subprocess.run(['docker', 'wait', name], capture_output=True, text=True, timeout=remaining)
        budget_waiting = False
        if result.returncode:
            raise RuntimeError('docker wait failed')
        exit_code = int(result.stdout.strip())
        reason = 'agent_completed' if exit_code == 0 else 'agent_error'
    except subprocess.TimeoutExpired as failure:
        reason = 'budget_exhausted' if budget_waiting else 'environment_failure'
        manifest['timeout_stage'] = failure.cmd[1] if isinstance(failure.cmd, list) and len(failure.cmd) > 1 else 'unknown'
    except KeyboardInterrupt:
        reason = 'operator_aborted'
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError):
        reason = 'environment_failure'
    finally:
        if container_created:
            try:
                subprocess.run(['docker', 'kill', name], capture_output=True, timeout=30)
                state = subprocess.run(['docker', 'inspect', '--format', '{{.State.Running}}', name],
                                       capture_output=True, text=True, timeout=30, check=True)
                stopped = state.stdout.strip() == 'false'
                if stopped:
                    logs = subprocess.run(['docker', 'logs', name], capture_output=True, text=True, timeout=30)
                    native_usage = []
                    for line in logs.stdout.splitlines():
                        try:
                            event = json.loads(line)
                            if event.get('type') == 'turn.completed' and isinstance(event.get('usage'), dict):
                                native_usage.append({k: v for k, v in event['usage'].items() if type(v) is int})
                        except (ValueError, AttributeError):
                            pass
                    write_json(output / 'native-usage.json', native_usage)
                    subprocess.run(['docker', 'rm', name], capture_output=True, timeout=30, check=True)
            except (OSError, subprocess.SubprocessError):
                stopped = False
        else:
            stopped = True
        manifest.update(ended_at=datetime.now(timezone.utc).isoformat(),
                        elapsed_seconds=time.monotonic() - started, end_reason=reason,
                        exit_code=exit_code, processes_stopped=stopped, status='ended')
        if stopped:
            try:
                source_hashes = snapshot(workspace)
                (output / 'frozen').mkdir()
                for relative in source_hashes:
                    target = output / 'frozen' / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(workspace / relative, target)
                hashes = snapshot(output / 'frozen')
                write_json(output / 'snapshot.json', hashes)
                manifest['submission_fixed'] = True
                manifest['excluded_generated_directories'] = sorted(EXCLUDED_DIRS)
                manifest['excluded_runtime_suffixes'] = sorted(EXCLUDED_SUFFIXES)
            except (ValueError, OSError):
                manifest['submission_fixed'] = False
                manifest['end_reason'] = 'environment_failure'
        else:
            manifest['submission_fixed'] = False
            manifest['end_reason'] = 'environment_failure'
        write_json(output / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('distribution', type=Path)
    parser.add_argument('config', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = run(args.distribution, json.loads(args.config.read_text(encoding='utf-8')), args.output)
    print(json.dumps(result))
    raise SystemExit(0 if result['end_reason'] == 'agent_completed' else 1)
