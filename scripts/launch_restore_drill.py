"""Root launcher: `unshare --net python3 launch_restore_drill.py ...`.

Both daemons share a private network namespace, content store and socket.
The actual drill runs as the explicitly named researcher, not root.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def launch(user, archive, common, destination):
    host = os.readlink('/proc/1/ns/net')
    namespace = os.readlink('/proc/self/ns/net')
    if host == namespace or os.getuid() != 0:
        raise ValueError('Launch as root under unshare --net')
    root = Path(tempfile.mkdtemp(prefix='sample1-restore-isolated-'))
    root.chmod(0o755)
    subprocess.run(['ip', 'link', 'set', 'lo', 'up'], check=True)
    children, logs = [], []
    try:
        for name, argv in [('containerd', ['containerd', '--address', str(root/'containerd.sock'),
                    '--root', str(root/'containerd-data'), '--state', str(root/'containerd-state')]),
                ('docker', ['dockerd', '--host=unix://'+str(root/'docker.sock'),
                    '--containerd='+str(root/'containerd.sock'), '--data-root='+str(root/'docker-data'),
                    '--exec-root='+str(root/'docker-exec'), '--pidfile='+str(root/'docker.pid'),
                    '--bridge=none', '--iptables=false', '--ip-masq=false'])]:
            log = (root/(name+'.log')).open('w');logs.append(log)
            children.append(subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT))
            for _ in range(200):
                if (root/(name+'.sock')).exists():break
                if children[-1].poll() is not None:raise RuntimeError(name+' exited')
                time.sleep(.1)
        command = ['runuser', '-u', user, '--', 'env',
                   'DOCKER_HOST=unix://'+str(root/'docker.sock'),
                   'SAMPLE1_HOST_NETWORK_NAMESPACE='+host, 'python3',
                   str(Path(__file__).with_name('check_preservation_restore.py')),
                   str(archive), str(common), str(destination)]
        result = subprocess.run(command)
        if result.returncode:
            raise RuntimeError('Restore drill failed; evidence retained at '+str(root))
        print(json.dumps({'daemon_files':str(root),'network_namespace':namespace,
                          'host_network_namespace':host,'drill_exit_code':result.returncode}),flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
                try:child.wait(timeout=20)
                except subprocess.TimeoutExpired:child.kill();child.wait()
        for log in logs:log.close()
        # Keep diagnostics and daemon data; never remove shared Docker state.


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('user');p.add_argument('archive',type=Path)
    p.add_argument('common',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();launch(a.user,a.archive,a.common,a.destination)
