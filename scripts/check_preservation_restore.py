"""Offline restore drill. Requires a NEW, EMPTY dedicated Docker daemon.

The source stage is inaccessible to all test containers. Images, evaluator,
dependencies, fixture and synthetic usage come solely from restored packages.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import tarfile
from unittest.mock import patch
from preserve import pack, restore, read, write_new, digest, tree, content_equal
from gateway_usage import collect
from run_experiment import run, snapshot


def drill(archive, common, destination):
    # A second data-root on the host can remove the production docker0 bridge.
    # Run this harness and BOTH daemons in a separate network namespace.
    namespace = os.readlink('/proc/self/ns/net')
    host_namespace = os.environ.get('SAMPLE1_HOST_NETWORK_NAMESPACE')
    if not host_namespace or namespace == host_namespace:
        raise ValueError('Run the drill and both daemons under unshare --net; host namespace required')
    if not os.environ.get('DOCKER_HOST', '').startswith('unix:///tmp/sample1-restore-'):
        raise ValueError('A dedicated restoration Docker daemon is required')
    initial = subprocess.check_output(['docker', 'image', 'ls', '-q'], text=True).strip()
    if initial:
        raise ValueError('Restore drill requires an empty Docker image store')
    destination.mkdir(parents=True, exist_ok=False)
    restored = destination / 'common'
    receipts = [restore(archive, common, restored)]
    runtime = read(restored / 'runtime/images.json')
    for image in runtime:
        file = restored / 'runtime' / image['file']
        if digest(file) != image['sha256']:
            raise ValueError('Runtime archive changed')
        subprocess.run(['docker', 'image', 'load', '-i', str(file)], check=True)
        identity = image['image'].split('@')[-1]
        if subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', identity], text=True).strip() != identity:
            raise ValueError('Loaded wrong image')
    manager = restored / 'management'
    evaluator = restored / 'evaluator'
    for bundle in ('node_modules.tar', 'tools.tar'):
        with tarfile.open(evaluator / bundle, 'r') as dependency_tar:
            members = dependency_tar.getmembers()
            from preserve import safe_name
            for member in members:
                safe_name(member.name.rstrip('/'))
                if not (member.isfile() or member.isdir()):
                    raise ValueError('Only regular dependency files/directories can be restored')
            dependency_tar.extractall(evaluator, members=members, filter='data')
    # Execute archived manager, not this checkout, for lifecycle/usage checks.
    import sys
    sys.path.insert(0, str(manager / 'scripts'))
    import importlib.util
    spec = importlib.util.spec_from_file_location('restored_runner', manager / 'scripts/run_experiment.py')
    runner = importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    distribution = destination / 'synthetic-distribution'
    (distribution / 'workspace').mkdir(parents=True)
    (distribution / 'workspace/spec.md').write_text('Synthetic lifecycle fixture; no model call.')
    write_new(distribution / 'distribution.json', {'condition': 'synthetic', 'files': {
        name: {'sha256': value} for name, value in snapshot(distribution / 'workspace').items()}})
    commands = [('normal', ['sh', '-c', 'printf complete > artifact'], 20, 'agent_completed'),
                ('timeout', ['sh', '-c', 'printf partial > artifact; sleep 30'], 2, 'budget_exhausted'),
                ('abnormal', ['sh', '-c', 'printf partial > artifact; exit 2'], 20, 'agent_error')]
    checks = {}; lifecycle = []
    for case, command, seconds, expected in commands:
        output = destination / case
        config = dict(experiment_version='restore-drill-only', model_id='none', effort='none',
                      agent_version='synthetic-shell', tool_versions={}, subagent_policy='disabled',
                      execution_order=0, environment={'image': runtime[0]['image']}, command=command,
                      budget={'kind': 'wall_clock_seconds', 'value': seconds, 'scope': 'container'})
        # Only this offline test harness substitutes authorization; fixed shell
        # commands, network=none, no credentials/gateway or configurable model argv.
        with patch.object(runner, 'check_start', return_value={'kind': 'offline-lifecycle-test'}), patch.object(runner, 'reserve_start'):
            result = runner.run(distribution, config, output)
        if result['end_reason'] != expected or not result['submission_fixed'] or not result['processes_stopped']:
            raise ValueError('Lifecycle failure: ' + json.dumps(result))
        raw = output / 'raw-usage'; raw.mkdir()
        start = {'run_id': result['run_id'], 'event_id': 'synthetic-1', 'session_id': 'implementation',
                 'request_id': 'synthetic-1', 'model_id': 'none', 'provider': 'synthetic', 'mode': 'request', 'usage': None}
        (raw / 'started.jsonl').write_text(json.dumps(start) + '\n')
        if case == 'normal':
            final = dict(start, usage={'input_tokens': 10, 'output_tokens': 3})
            (raw / 'events.jsonl').write_text(json.dumps(final) + '\n')
        usage = collect(raw)
        write_new(output / 'usage.json', dict(usage, synthetic=True))
        from preserve import pack_run
        ref = pack_run(archive, output, [common])
        restored_run = destination / ('restored-' + case)
        receipts.append(restore(archive, ref, restored_run))
        computed = json.loads(subprocess.check_output(['python3', '-c',
            'import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from gateway_usage import collect;print(json.dumps(collect(Path(sys.argv[2]))))',
            str(manager / 'scripts'), str(restored_run / 'raw-usage')], text=True))
        if computed != usage or (case != 'normal' and (computed['usage_complete'] or not computed['missing'])):
            raise ValueError('Synthetic usage restoration failed')
        checks[{'normal': 'normal_exit', 'timeout': 'timeout_exit', 'abnormal': 'abnormal_exit'}[case]] = True
        lifecycle.append({'case': case, 'run_id': result['run_id'], 'end_reason': result['end_reason'],
                          'usage': computed, 'reference': ref})
    # Each calibration container sees ONLY restored evaluator, fixture and deps.
    # No original checkout, stage, Docker socket, or external network is mounted.
    calibration = []
    image = runtime[2]['image'].split('@')[-1]
    for variant in ('standard', 'self-registration'):
        for threshold in ('1000000', '500000'):
            name = 'restore-' + variant + '-' + threshold
            command = ['docker', 'run', '--rm', '--network', 'none', '--user', f'{os.getuid()}:{os.getgid()}',
                       '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only',
                       '--tmpfs', '/tmp:mode=1777,exec', '--env', 'TZ=Asia/Tokyo',
                       '--mount', f'type=bind,source={evaluator},target=/evaluator', '--workdir', '/evaluator',
                       image, '/evaluator/tools/node', '/evaluator/calibrate.mjs', name, variant, threshold]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=1200)
            summary = read(evaluator / 'calibration-runs' / name / 'result/summary.json')
            expected = 57 if threshold == '1000000' else 44
            if completed.returncode or summary['outcome'] != 'completed' or summary['counts']['pass'] != expected:
                raise ValueError('Restored calibration failed: ' + json.dumps(summary['counts']) + completed.stderr[-1000:])
            calibration.append({'name': name, 'counts': summary['counts'], 'evaluator_hash': summary['evaluator_hash'],
                                'command': command, 'exit_code': completed.returncode})
            print(json.dumps(calibration[-1]), flush=True)
    # Original dependency/code files must still match after the test; outputs are separate.
    index = read(Path(archive) / 'packages' / common['package_id'] / 'package.json')
    for name, entry in index['files'].items():
        if digest(restored / name) != entry['sha256']:
            raise ValueError('Restored common input changed')
    evaluation_ref = pack(archive, 'restore-calibration-' + str(uuid.uuid4()),
                          {'calibration-runs': evaluator / 'calibration-runs'},
                          metadata={'kind': 'calibration', 'synthetic': True}, references=[common])
    receipts.append(restore(archive, evaluation_ref, destination / 'restored-calibration-results'))
    checks.update(hashes_match=True, usage_recomputed=True, normal_fixture=True, threshold_mutation=True,
                  empty_daemon_restore=True, source_unavailable=True, evaluation_restored=True)
    proof = {'model_called': False, 'recorded_at': datetime.now(timezone.utc).isoformat(),
             'checks': checks, 'common': common, 'receipts': receipts, 'lifecycle': lifecycle,
             'calibration': calibration, 'source_hashes': read(restored / 'source-hashes.json'),
             'docker_host': os.environ['DOCKER_HOST'], 'initial_images': [],
             'network_namespace': namespace, 'host_network_namespace': host_namespace,
             'limitation': 'Same physical C drive; no disk failure guarantee'}
    write_new(destination / 'proof.json', proof)
    gate = pack(archive, 'restoration-proof-' + str(uuid.uuid4()), {'proof.json': destination / 'proof.json'},
                metadata={'kind': 'restoration-proof'}, references=[common, evaluation_ref])
    write_new(destination / 'gate.json', gate)
    print(json.dumps({'gate': gate, 'proof': str(destination / 'proof.json')}), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('common',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();drill(a.archive,read(a.common),a.destination)
