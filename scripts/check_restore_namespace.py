"""Run as root via unshare --net: verify restore daemons cannot touch host links.

No model, images, credentials or shared Docker socket are used. A marker docker0
inside the new namespace tests the side effect that broke the initial pilot's
gateway. Future full drills must launch BOTH containerd and dockerd this way.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def main(output):
    current = os.readlink('/proc/self/ns/net')
    host = os.readlink('/proc/1/ns/net')
    if current == host:
        raise ValueError('Must run under unshare --net; never use the host network namespace')
    with tempfile.TemporaryDirectory(prefix='sample1-namespace-check-') as temporary:
        root = Path(temporary)
        subprocess.run(['ip', 'link', 'set', 'lo', 'up'], check=True)
        subprocess.run(['ip', 'link', 'add', 'docker0', 'type', 'bridge'], check=True)
        logs = [open(root / name, 'w') for name in ('containerd.log', 'docker.log')]
        children = []
        try:
            children.append(subprocess.Popen(['containerd', '--address', str(root / 'containerd.sock'),
                '--root', str(root / 'containerd-data'), '--state', str(root / 'containerd-state')],
                stdout=logs[0], stderr=subprocess.STDOUT))
            for _ in range(100):
                if (root / 'containerd.sock').exists():break
                time.sleep(.1)
            children.append(subprocess.Popen(['dockerd', '--host=unix://' + str(root / 'docker.sock'),
                '--containerd=' + str(root / 'containerd.sock'), '--data-root=' + str(root / 'docker-data'),
                '--exec-root=' + str(root / 'docker-exec'), '--pidfile=' + str(root / 'docker.pid'),
                '--bridge=none', '--iptables=false', '--ip-masq=false'], stdout=logs[1], stderr=subprocess.STDOUT))
            env = dict(os.environ, DOCKER_HOST='unix://' + str(root / 'docker.sock'))
            for _ in range(100):
                result = subprocess.run(['docker', 'info', '--format', '{{.DockerRootDir}}'], env=env, capture_output=True)
                if result.returncode == 0:break
                time.sleep(.1)
            if result.returncode:
                raise RuntimeError('Namespace-isolated daemon failed to start')
            marker = subprocess.run(['ip', 'link', 'show', 'docker0'], capture_output=True)
            evidence = {'model_called': False, 'network_namespace': current, 'host_network_namespace': host,
                        'isolated_daemon_started': True, 'marker_existed_before': True,
                        'marker_exists_after': marker.returncode == 0,
                        'conclusion': 'Separate Docker data-root does not isolate host networking; use unshare --net for both daemons.'}
        finally:
            for child in reversed(children):
                child.send_signal(signal.SIGTERM)
                try: child.wait(timeout=20)
                except subprocess.TimeoutExpired: child.kill();child.wait()
            for log in logs:log.close()
        evidence['daemon_log'] = (root / 'docker.log').read_text()
        output.write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps({k:v for k,v in evidence.items() if k != 'daemon_log'}))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();main(a.output)
