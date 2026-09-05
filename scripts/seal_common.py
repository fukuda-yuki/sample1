"""Seal the fixed runtime/evaluator and manager source before the offline drill."""
import argparse
import json
from pathlib import Path
import shutil
import uuid
from preserve import digest, pack, write_new


def seal(root, stage, archive):
    common = stage / 'common'
    manager = common / 'management'
    manager.mkdir()
    files = [p for directory in ('scripts', 'analysis', 'config', 'evaluation')
             for p in (root / directory).rglob('*')
             if p.is_file() and p.suffix in ('.py', '.json', '.txt') and '__pycache__' not in p.parts
             and p.name != 'execution-scope.json']
    files += [root / name for name in ('normal/spec.md', 'anti/spec.md', 'implementation_prompt.md')]
    hashes = {}
    for source in files:
        relative = source.relative_to(root)
        target = manager / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative.as_posix()] = digest(source)
    write_new(common / 'source-hashes.json', hashes)
    ref = pack(archive, 'common-' + str(uuid.uuid4()),
               {p.name: p for p in common.iterdir()}, metadata={'kind': 'fixed-common',
                    'experiment_version': 'exp-001', 'management_version': 'measurement-control-v3'})
    write_new(stage / 'common-reference.json', ref)
    print(json.dumps(ref), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('stage',type=Path);p.add_argument('archive',type=Path)
    a=p.parse_args();seal(a.root,a.stage,a.archive)
