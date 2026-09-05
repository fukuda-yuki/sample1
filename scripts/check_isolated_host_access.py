"""A host listener canary proves isolated bridge clients cannot reach host services."""
import argparse
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import uuid

IMAGE='python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea'


def main(output):
    name='sample1-host-canary-'+str(uuid.uuid4())
    listener=socket.socket()
    listener.bind(('0.0.0.0',0));listener.listen()
    port=listener.getsockname()[1]
    external=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    external.connect(('1.1.1.1',443));host_ip=external.getsockname()[0];external.close()
    subprocess.run(['docker','network','create','--internal','--opt',
                    'com.docker.network.bridge.gateway_mode_ipv4=isolated',name],check=True,capture_output=True)
    try:
        net=json.loads(subprocess.check_output(['docker','network','inspect',name]))[0]
        bridge_ip=str(ipaddress.ip_network(net['IPAM']['Config'][0]['Subnet']).network_address+1)
        probe='''import socket,sys
for host in sys.argv[1:]:
 try: s=socket.create_connection((host,PORT),timeout=2)
 except OSError: continue
 s.close();raise RuntimeError('Host canary reachable')
print('denied')
'''.replace('PORT',str(port))
        result=subprocess.run(['docker','run','--rm','--network',name,'--read-only','--cap-drop','ALL',
                               '--security-opt','no-new-privileges',IMAGE,'python','-c',probe,host_ip,bridge_ip],
                              capture_output=True,text=True,timeout=15,check=True)
        output.write_text(json.dumps({'kind':'isolated_host_service_probe','gateway_mode':'isolated',
                          'host_interface_canary_denied':True,'bridge_address_canary_denied':True,
                          'model_called':False,'image':IMAGE},indent=2),encoding='utf-8')
    finally:
        listener.close()
        subprocess.run(['docker','network','rm',name],capture_output=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    main(p.parse_args().output)
