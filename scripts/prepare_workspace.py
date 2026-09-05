"""Allowlisted experiment inputs. Run this outside the implementation sandbox."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_pair(repo):
    normal = (repo / 'normal/spec.md').read_text(encoding='utf-8')
    anti = (repo / 'anti/spec.md').read_text(encoding='utf-8')
    replacements = [('999,999円以下', '499,999円以下'), ('1,000,000円以上', '500,000円以上')]
    expected = normal
    for old, new in replacements:
        old_line = next((line for line in normal.splitlines() if old in line and '承認者:' in line), None)
        if not old_line or normal.count(old_line) != 1:
            raise ValueError('Expected exactly one F-006 approval boundary')
        expected = expected.replace(old_line, old_line.replace(old, new), 1)
    if expected != anti:
        raise ValueError('Unexpected condition difference; AP-001 boundaries must be the only difference')
    return normal, anti


def prepare(repo, condition, destination):
    normal, anti = validate_pair(repo)
    if destination.exists():
        raise ValueError('Destination must not already exist')
    destination.mkdir(parents=True)
    workspace = destination / 'workspace'
    workspace.mkdir()
    files = {'spec.md': (normal if condition == 'normal' else anti).encode('utf-8'),
             'RUN_CONTRACT.md': (repo / 'implementation_prompt.md').read_text(encoding='utf-8-sig').encode('utf-8')}
    for name, data in files.items():
        (workspace / name).write_bytes(data)
    manifest = {'schema_version': 1, 'condition': condition, 'neutral_path': '/workspace',
                'files': {name: {'sha256': digest(data), 'bytes': len(data)} for name, data in files.items()},
                'common_contract_sha256': digest(files['RUN_CONTRACT.md']),
                'isolation_verified': False}
    (destination / 'distribution.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('condition', choices=['normal', 'anti'])
    p.add_argument('destination', type=Path)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    prepare(a.repo, a.condition, a.destination)
