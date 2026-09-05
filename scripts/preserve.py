"""Researcher-only, append-only directory packages with verified restoration.

No credentials discovery and no implicit recursive capture of a Run workspace.
Callers provide an explicit allowlist of sources. Packages contain ordinary files
only; restored executable mode bits are retained for Linux runtimes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import uuid


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or any(p in ('', '.', '..') for p in name.split('/'))
            or PurePosixPath(name).is_absolute()):
        raise ValueError('Unsafe package path')
    return name


def tree(root):
    root = Path(root)
    if root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()):
        raise ValueError('Links forbidden')
    entries = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(base) / name
            if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
                raise ValueError('Links forbidden: ' + str(p))
            if not (p.is_file() or p.is_dir()):
                raise ValueError('Special files forbidden')
        for name in sorted(files):
            p = Path(base) / name
            relative = safe_name(p.relative_to(root).as_posix())
            entries[relative] = {'sha256': digest(p), 'bytes': p.stat().st_size,
                                 'executable': bool(p.stat().st_mode & stat.S_IXUSR)}
    return dict(sorted(entries.items()))


def content_equal(actual, expected):
    # Windows/DrvFS may not preserve Unix mode bits. Restore applies recorded modes.
    return ({k: (v['sha256'], v['bytes']) for k, v in actual.items()}
            == {k: (v['sha256'], v['bytes']) for k, v in expected.items()})


def verify(archive, package_id, expected_hash=None, seen=None, cache=None):
    cache = {} if cache is None else cache
    safe_name(package_id)
    if '/' in package_id:
        raise ValueError('Package ID must be one component')
    package = Path(archive) / 'packages' / package_id
    if package.is_symlink():
        raise ValueError('Package link forbidden')
    index = package / 'package.json'
    if expected_hash and digest(index) != expected_hash:
        raise ValueError('Package index changed')
    cache_key = (str(Path(archive).resolve()), package_id, digest(index))
    if cache_key in cache:
        return cache[cache_key]
    data = read(index)
    if data['package_id'] != package_id or data['schema_version'] != 1:
        raise ValueError('Package identity mismatch')
    if set(p.name for p in package.iterdir()) != {'package.json', 'payload'}:
        raise ValueError('Unexpected package member')
    for name in data['files']:
        safe_name(name)
    if not content_equal(tree(package / 'payload'), data['files']):
        raise ValueError('Package missing, extra or modified file')
    seen = set() if seen is None else set(seen)
    if package_id in seen:
        raise ValueError('Cyclic package references')
    seen.add(package_id)
    for ref in data['references']:
        verify(archive, ref['package_id'], ref['sha256'], seen, cache)
    cache[cache_key] = data
    return data


def pack(archive, package_id, sources, *, metadata=None, references=()):
    archive = Path(archive).resolve()
    safe_name(package_id)
    if '/' in package_id:
        raise ValueError('Package ID must be one component')
    packages = archive / 'packages'
    packages.mkdir(parents=True, exist_ok=True)
    final = packages / package_id
    # Persistent reservation also records failed packaging attempts; never reuse IDs.
    write_new(archive / 'package-reservations' / (package_id + '.json'),
              {'package_id': package_id, 'started_at': datetime.now(timezone.utc).isoformat()})
    temporary = packages / ('.partial-' + package_id + '-' + str(uuid.uuid4()))
    payload = temporary / 'payload'
    payload.mkdir(parents=True)
    for relative, source in sources.items():
        safe_name(relative)
        source = Path(source)
        if source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
            raise ValueError('Source link forbidden')
        source = source.resolve(strict=True)
        if archive == source or archive.is_relative_to(source) or source.is_relative_to(archive):
            raise ValueError('Archive and sources must be independent')
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            before = tree(source)
            shutil.copytree(source, destination)
            if not content_equal(tree(destination), before) or not content_equal(tree(source), before):
                raise ValueError('Source changed during copy')
        else:
            if source.is_symlink() or not source.is_file():
                raise ValueError('Regular sources required')
            before = digest(source)
            shutil.copy2(source, destination)
            if digest(source) != before or digest(destination) != before:
                raise ValueError('Source changed during copy')
    for ref in references:
        verify(archive, ref['package_id'], ref['sha256'])
    data = {'schema_version': 1, 'package_id': package_id,
            'created_at': datetime.now(timezone.utc).isoformat(), 'metadata': metadata or {},
            'references': list(references), 'files': tree(payload)}
    write_new(temporary / 'package.json', data)
    if not content_equal(tree(payload), data['files']):
        raise ValueError('Copy verification failed')
    if final.exists():
        raise FileExistsError(final)
    temporary.rename(final)
    return {'package_id': package_id, 'sha256': digest(final / 'package.json')}


def restore(archive, reference, destination):
    archive, destination = Path(archive).resolve(), Path(destination).absolute()
    if destination.is_relative_to(archive) or archive.is_relative_to(destination):
        raise ValueError('Restore must be independent of archive')
    data = verify(archive, reference['package_id'], reference['sha256'])
    source = archive / 'packages' / reference['package_id'] / 'payload'
    shutil.copytree(source, destination)
    for name, entry in data['files'].items():
        (destination / name).chmod(0o755 if entry['executable'] else 0o644)
    if not content_equal(tree(destination), data['files']):
        raise ValueError('Restoration mismatch')
    verify(archive, reference['package_id'], reference['sha256'])
    receipt = {'schema_version': 1, 'reference': reference, 'restored_to': str(destination),
               'verified_at': datetime.now(timezone.utc).isoformat(), 'file_count': len(data['files'])}
    receipt_id = str(uuid.uuid4())
    target = archive / 'receipts' / (receipt_id + '.json')
    write_new(target, receipt)
    return {'path': 'receipts/' + receipt_id + '.json', 'sha256': digest(target)}


def verify_receipt(archive, receipt, cache=None):
    safe_name(receipt['path'])
    path = Path(archive) / receipt['path']
    if digest(path) != receipt['sha256']:
        raise ValueError('Restore receipt changed')
    data = read(path)
    verify(archive, data['reference']['package_id'], data['reference']['sha256'], cache=cache)
    return data


def pack_run(archive, run_root, references):
    root = Path(run_root)
    manifest = read(root / 'manifest.json')
    # Missing artifacts are recorded, never converted to complete originals.
    names = ['frozen', 'snapshot.json', 'manifest.json', 'inputs', 'usage.json',
             'native-usage.json', 'raw-usage', 'management-source']
    sources = {name: root / name for name in names if (root / name).exists()}
    return pack(archive, 'run-' + manifest['run_id'], sources,
                metadata={'kind': 'run', 'run_id': manifest['run_id'],
                          'missing': [name for name in names if name not in sources]},
                references=references)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['pack', 'restore', 'verify'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('spec', type=Path, help='Explicit sources or pinned package reference JSON')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    spec = read(args.spec)
    if args.operation == 'pack':
        result = pack(args.archive, spec['package_id'], spec['sources'],
                      metadata=spec.get('metadata'), references=spec.get('references', []))
    elif args.operation == 'restore':
        result = restore(args.archive, spec, args.destination)
    else:
        result = verify(args.archive, spec['package_id'], spec['sha256'])
    print(json.dumps(result, ensure_ascii=False))
