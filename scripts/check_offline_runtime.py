"""Exercise real startup and cached dependency restoration in the worker image."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

INNER = r'''
import json,os,pathlib,subprocess,time,urllib.request
root=pathlib.Path('/workspace')
backend=root/'backend';frontend=root/'frontend'
backend.mkdir();frontend.mkdir()
(backend/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup><ItemGroup><PackageReference Include="Microsoft.EntityFrameworkCore.Sqlite" Version="8.0.19" /></ItemGroup></Project>')
(backend/'Program.cs').write_text('using Microsoft.Data.Sqlite; var builder=WebApplication.CreateBuilder(args); var app=builder.Build(); app.MapGet("/api/health",()=> { using var db=new SqliteConnection("Data Source=/tmp/probe.db"); db.Open(); using var cmd=db.CreateCommand(); cmd.CommandText="select 1"; return Results.Json(new { value=cmd.ExecuteScalar() }); }); app.Run();')
nuget_config=pathlib.Path.home()/'.nuget/NuGet/NuGet.Config'
nuget_config.parent.mkdir(parents=True,exist_ok=True)
nuget_config.write_text('<configuration><packageSources><clear /></packageSources></configuration>')
os.environ['npm_config_offline']='true'
os.environ['npm_config_audit']='false'
(frontend/'package.json').write_text(json.dumps({'name':'runtime-probe','private':True,'type':'module','scripts':{'dev':'vite --host 0.0.0.0 --port 5173'},'dependencies':{'react':'19.2.8','react-dom':'19.2.8','vite':'8.2.2'}}))
(frontend/'index.html').write_text('<div id="root"></div><script type="module" src="/src.jsx"></script>')
(frontend/'src.jsx').write_text('import React from "react";import {createRoot} from "react-dom/client";createRoot(document.getElementById("root")).render(React.createElement("h1",null,"Runtime ready"));')
def call(argv,cwd):
 result=subprocess.run(argv,cwd=cwd,text=True,capture_output=True,timeout=90)
 if result.returncode: raise RuntimeError(result.stdout+result.stderr)
call(['dotnet','restore'],backend)
call(['npm','install','--ignore-scripts'],frontend)
call(['npm','ci'],frontend)
logs=[];processes=[]
try:
 for title,argv,cwd in [('backend',['dotnet','run','--no-restore','--urls','http://0.0.0.0:5080'],backend),('frontend',['npm','run','dev'],frontend)]:
  stream=(root/(title+'.log')).open('w');logs.append(stream)
  processes.append(subprocess.Popen(argv,cwd=cwd,stdout=stream,stderr=stream))
 def wait(url):
  for _ in range(60):
   try:
    return urllib.request.urlopen(url,timeout=1).read().decode()
   except OSError: time.sleep(0.5)
  raise RuntimeError('Startup timeout: '+url+' '+''.join(p.read_text() for p in root.glob('*.log')))
 assert json.loads(wait('http://127.0.0.1:5080/api/health'))['value']==1
 assert '/src.jsx' in wait('http://127.0.0.1:5173/')
 assert 'Runtime ready' in wait('http://127.0.0.1:5173/src.jsx')
 print(json.dumps({'dotnet_restore_offline':True,'sqlite_native_query':True,'npm_ci_offline':True,'backend_http_5080':True,'vite_http_5173':True,'react_module_transformed':True,'nuget_packages':os.environ.get('NUGET_PACKAGES')}))
finally:
 for process in processes: process.terminate()
 for stream in logs: stream.close()
'''


def main(image, evidence):
    with tempfile.TemporaryDirectory(prefix='sample1-runtime-') as temp:
        root=Path(temp)
        (root/'probe.py').write_text(INNER)
        result=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--user',f'{os.getuid()}:{os.getgid()}',
            '--tmpfs','/tmp:mode=1777,exec','--tmpfs','/home/agent:mode=1777,exec','--env','HOME=/home/agent',
            '--mount',f'type=bind,source={root},target=/workspace','--workdir','/workspace',image,
            'sh','-c','cp -r /opt/npm-cache /tmp/npm-cache && python3 /workspace/probe.py'],
            text=True,capture_output=True,timeout=240)
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)
        data=json.loads(result.stdout)
        data.update(kind='offline_runtime_calibration',image=image,model_called=False)
        evidence.write_text(json.dumps(data,indent=2),encoding='utf-8')
        print(json.dumps(data))


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--image',required=True)
    p.add_argument('--evidence',required=True,type=Path)
    a=p.parse_args()
    main(a.image,a.evidence)
