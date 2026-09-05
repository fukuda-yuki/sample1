"""Tiny real provider check, excluded from experiment comparisons."""
import argparse
import json
from pathlib import Path
import tempfile
from run_codex import execute
from run_experiment import snapshot


def main(image, auth, evidence):
    root=Path(tempfile.mkdtemp(prefix='sample1-model-smoke-'))
    workspace=root/'distribution/workspace'
    workspace.mkdir(parents=True)
    (workspace/'spec.md').write_text('Integration smoke test only. No implementation task.',encoding='utf-8')
    distribution={'condition':'calibration','files':{k:{'sha256':v} for k,v in snapshot(workspace).items()}}
    (root/'distribution/distribution.json').write_text(json.dumps(distribution),encoding='utf-8')
    config=dict(experiment_version='model-smoke-only',model_id='gpt-5.6-luna',effort='xhigh',
                agent_version='codex-cli-0.153.0',tool_versions={'node':'22.23.2','dotnet':'8.0.424'},
                subagent_policy='disabled',execution_order=0,environment={'image':image},
                budget={'kind':'wall_clock_seconds','value':300,'scope':'container'})
    result=execute(root/'distribution',config,root/'run',auth,'Reply with exactly OK. Do not use tools.')
    evidence.write_text(json.dumps({'kind':'model_usage_smoke','run_directory':str(root/'run'),
        'run_id':result['run_id'],'end_reason':result['end_reason'],
        'usage':json.loads((root/'run/usage.json').read_text()),
        'native_usage':json.loads((root/'run/native-usage.json').read_text()) if (root/'run/native-usage.json').exists() else [],
        'model_id':config['model_id'],'effort':config['effort']},indent=2),encoding='utf-8')
    print(evidence.read_text())


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--image',required=True)
    p.add_argument('--auth',required=True,type=Path)
    p.add_argument('--evidence',required=True,type=Path)
    a=p.parse_args()
    main(a.image,a.auth,a.evidence)
