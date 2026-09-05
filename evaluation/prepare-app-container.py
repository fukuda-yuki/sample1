"""Create stopped app/researcher containers; private E2E owns app start/stop.

Run on the Docker host (WSL). No hidden assertions are included here.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def main(run_root, private_root, evaluator_image):
    run_root, private_root = run_root.resolve(), private_root.resolve()
    manifest = json.loads((run_root / 'manifest.json').read_text())
    if not manifest.get('submission_fixed') or not manifest.get('processes_stopped'):
        raise ValueError('Submission must be fixed after stopping implementation processes')
    image = manifest['environment']['image']
    for value in (image, evaluator_image):
        if not re.fullmatch(r'(?:[^\s]+@)?sha256:[0-9a-f]{64}', value):
            raise ValueError('Pin both images by digest')
    evaluation_id = str(uuid.uuid4())
    network = 'sample1-eval-' + evaluation_id
    app = 'sample1-app-' + evaluation_id
    researcher = 'sample1-researcher-' + evaluation_id
    evaluation_root = private_root / 'evaluations' / evaluation_id
    output = evaluation_root / 'result'
    maildrop = private_root / 'maildrops' / evaluation_id
    evaluation_root.mkdir(parents=True)
    maildrop.mkdir(parents=True)
    source = run_root / 'frozen'
    snapshot = run_root / 'snapshot.json'
    uid, gid = os.getuid(), os.getgid()
    private_node = private_root / 'tools/node'
    node_version = subprocess.check_output([str(private_node), '--version'], text=True).strip()
    try:
        docker('network', 'create', '--internal', '--opt',
               'com.docker.network.bridge.gateway_mode_ipv4=isolated', '--label',
               'sample1.evaluation_id=' + evaluation_id, network)
        info = json.loads(docker('network', 'inspect', network))[0]
        subnet = ipaddress.ip_network(info['IPAM']['Config'][0]['Subnet'])
        app_ip = str(subnet.network_address + 10)
        startup = '''set -eu
mkdir -p /tmp/app /home/agent/.nuget/NuGet
cp -R /submission/. /tmp/app/
cp -R /opt/npm-cache /tmp/npm-cache
printf %s '<configuration><packageSources><clear /></packageSources></configuration>' > /home/agent/.nuget/NuGet/NuGet.Config
(cd /tmp/app/backend && dotnet restore && exec dotnet run --no-restore) &
backend_pid=$!
(cd /tmp/app/frontend && npm ci && exec npm run dev -- --host 0.0.0.0) &
frontend_pid=$!
wait -n "$backend_pid" "$frontend_pid"
'''
        docker('create', '--name', app, '--network', network, '--ip', app_ip,
               '--user', f'{uid}:{gid}', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--read-only', '--tmpfs', '/tmp:mode=1777,exec', '--tmpfs', '/home/agent:mode=1777,exec',
               '--env', 'HOME=/home/agent', '--env', 'npm_config_offline=true', '--env', 'npm_config_audit=false',
               '--env', 'ASPNETCORE_ENVIRONMENT=Development', '--env', 'ASPNETCORE_URLS=http://0.0.0.0:5080',
               '--env', 'TZ=Asia/Tokyo',
               '--mount', f'type=bind,source={source},target=/submission,readonly',
               '--mount', f'type=bind,source={maildrop},target=/tmp/app/backend/maildrop',
               image, 'bash', '-c', startup)
        config = dict(kind='evaluation', run_id=manifest['run_id'], evaluation_id=evaluation_id,
                      submission_root=str(source), snapshot_file=str(snapshot), container_id=app,
                      app_url=f'http://{app_ip}:5173', api_url=f'http://{app_ip}:5080',
                      maildrop=str(maildrop), output=str(output))
        if (source / 'ui-map.json').exists():
            config['ui_map'] = str(source / 'ui-map.json')
        config_path = evaluation_root / 'researcher-config.json'
        config_path.write_text(json.dumps(config, indent=2))
        socket = Path('/var/run/docker.sock')
        docker_binary = Path(shutil.which('docker')).resolve()
        docker('create', '--name', researcher, '--network', network, '--user', f'{uid}:{gid}',
               '--group-add', str(socket.stat().st_gid), '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--read-only',
               '--tmpfs', '/tmp:mode=1777,exec', '--tmpfs', '/home/pwuser:mode=1777,exec',
               '--env', 'HOME=/home/pwuser', '--env', 'TZ=Asia/Tokyo',
               '--mount', f'type=bind,source={private_root},target={private_root},readonly',
               '--mount', f'type=bind,source={evaluation_root},target={evaluation_root}',
               '--mount', f'type=bind,source={source},target={source},readonly',
               '--mount', f'type=bind,source={snapshot},target={snapshot},readonly',
               '--mount', f'type=bind,source={maildrop},target={maildrop},readonly',
               '--mount', f'type=bind,source={socket},target=/var/run/docker.sock',
               '--mount', f'type=bind,source={docker_binary},target=/usr/local/bin/docker,readonly',
               '--workdir', str(private_root), evaluator_image, str(private_node), str(private_root / 'run.mjs'), str(config_path))
        resources = dict(evaluation_id=evaluation_id, app_container=app, researcher_container=researcher,
                         network=network, config=str(config_path), output=str(output),
                         evaluator_image=evaluator_image, app_image=image, evaluator_node_version=node_version,
                         evaluator_node_sha256=hashlib.sha256(private_node.read_bytes()).hexdigest())
        (evaluation_root / 'resources.json').write_text(json.dumps(resources, indent=2))
        print(json.dumps(resources, indent=2))
    except Exception:
        for name in (researcher, app):
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', network], capture_output=True)
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('run_root', type=Path)
    p.add_argument('private_root', type=Path)
    p.add_argument('--evaluator-image', required=True)
    a = p.parse_args()
    main(a.run_root, a.private_root, a.evaluator_image)
