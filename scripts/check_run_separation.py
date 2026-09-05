"""Real two-container check for identical ports and independent mutable state."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import uuid


def check(image, evidence):
    containers = []
    program = '''import pathlib,socket,time
for name in ('app.db','maildrop/message.json','memory','cache/entry'):
 p=pathlib.Path('/tmp')/name
 assert not p.exists()
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text('private-to-this-container')
sockets=[]
for port in (5080,5173):
 s=socket.socket();s.bind(('0.0.0.0',port));s.listen();sockets.append(s)
print('SEPARATE_STATE_AND_PORTS_OK',flush=True)
time.sleep(5)
'''
    try:
        for _ in range(2):
            name = 'sample1-separation-' + str(uuid.uuid4())
            subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none',
                            '--read-only', '--user', '1000:1000', '--cap-drop', 'ALL',
                            '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:mode=1777,exec',
                            image, 'python', '-c', program], capture_output=True, check=True)
            containers.append(name)
        import time
        time.sleep(1)
        for name in containers:
            result = subprocess.run(['docker', 'logs', name], capture_output=True, text=True, check=True)
            assert 'SEPARATE_STATE_AND_PORTS_OK' in result.stdout, result.stderr
            running = subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', name], capture_output=True, text=True, check=True)
            assert running.stdout.strip() == 'true'
        evidence.write_text(json.dumps({'kind': 'simultaneous_run_separation', 'containers': 2,
                            'same_ports': [5080, 5173], 'independent_db_mail_memory_cache': True,
                            'simultaneously_running': True, 'image': image}, indent=2) + '\n', encoding='utf-8')
    finally:
        for name in containers:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('image')
    p.add_argument('evidence', type=Path)
    a = p.parse_args()
    check(a.image, a.evidence)
