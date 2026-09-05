"""Probe the live internal network and HTTP deny rules without calling a model."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from run_codex import GATEWAY_IMAGE


def main(output):
    identity=str(uuid.uuid4())
    network='sample1-check-' + identity
    gateway='sample1-gateway-check-' + identity
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        for name in ['other-condition','AGENTS.md','evaluator','past-run']:
            (root/name).write_text('CANARY-'+name)
        script=Path(__file__).with_name('model_gateway.py').resolve()
        subprocess.run(['docker','network','create','--internal',
                        '--opt','com.docker.network.bridge.gateway_mode_ipv4=isolated',network],check=True,capture_output=True)
        try:
            subprocess.run(['docker','create','--name',gateway,'--network','bridge',
                            '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                            '--env','MODEL_ID=fixed','--env','EFFORT=xhigh','--env','RUN_ID=probe',
                            '--mount',f'type=bind,source={script},target=/gateway.py,readonly',
                            GATEWAY_IMAGE,'python','/gateway.py'],check=True,capture_output=True)
            subprocess.run(['docker','network','connect','--alias','model-gateway',network,gateway],check=True,capture_output=True)
            subprocess.run(['docker','start',gateway],check=True,capture_output=True)
            probe="""import http.client,json,pathlib,socket,time
time.sleep(1)
for path in CANARIES:
 assert not pathlib.Path(path).exists(),path
for host in ['1.1.1.1','github.com','raw.githubusercontent.com']:
 try:
  s=socket.create_connection((host,443),timeout=2)
 except OSError: pass
 else:
  s.close();raise AssertionError('external egress reachable: '+host)
for path,body in [('/https://github.com/fukuda-yuki/sample1',{}),('/responses',{'model':'fixed','reasoning':{'effort':'xhigh'},'stream':True,'tools':[{'type':'web_search'}]}),('/responses',{'model':'other'})]:
 c=http.client.HTTPConnection('model-gateway',8080,timeout=3)
 c.request('POST',path,json.dumps(body),{'Content-Type':'application/json'})
 r=c.getresponse();assert r.status==403,(path,r.status);r.read();c.close()
print(json.dumps({'host_canaries_denied':4,'github_egress_denied':True,'arbitrary_gateway_path_denied':True,'remote_tools_denied':True,'model_change_denied':True}))
""".replace('CANARIES',repr([str(root/name) for name in ['other-condition','AGENTS.md','evaluator','past-run']]))
            result=subprocess.run(['docker','run','--rm','--network',network,'--read-only',
                                   '--cap-drop','ALL','--security-opt','no-new-privileges',
                                   GATEWAY_IMAGE,'python','-c',probe],check=True,capture_output=True,text=True,timeout=30)
            evidence=json.loads(result.stdout)
            evidence.update(kind='gateway_isolation_integration',model_called=False,image=GATEWAY_IMAGE)
            output.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        finally:
            subprocess.run(['docker','rm','-f',gateway],capture_output=True)
            subprocess.run(['docker','network','rm',network],capture_output=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    main(parser.parse_args().output)
