"""Explicit private analysis originals package; no model calls or start authority."""
import argparse
from pathlib import Path
import shutil
import tempfile
import uuid
from copilot_batch import load, export, ROOT
from preserve import pack, restore, read, write_new


def preserve_analysis(root, validity, archive):
    config, index = load(root)
    sources = {'batch/' + name: root / name for name in
               ('experiment.json', 'planned-runs.json', 'run-index.json')}
    sources['validity.json'] = validity
    sources.update({'inputs/'+name: ROOT/name for name in config['input_hashes']})
    # These two-slot originals have no adjudications. Do not silently omit them.
    if any(r.get('adjudications') for r in read(validity)['attempts']):
        raise ValueError('Archive adjudication dependencies explicitly before relocation')
    locations = {}
    for slot in index['runs']:
        if slot['run_id'] is None:
            continue
        relative = 'batch/runs/' + slot['planned_run'] + '/attempt/'
        run = root / 'runs' / slot['planned_run'] / 'attempt'
        for name in ('manifest.json', 'snapshot.json', 'frozen', 'usage.json',
                     'telemetry', 'telemetry-link.json', 'raw-usage', 'evaluation-ref.json'):
            if (run / name).exists():
                sources[relative + name] = run / name
        if not (run / 'evaluation-ref.json').exists():
            continue
        ref = read(run / 'evaluation-ref.json')
        eid = ref['evaluation_id']
        if eid in locations:
            raise ValueError('Duplicate selected evaluation')
        directory = Path(ref['evaluation_directory'])
        locations[eid] = {'original_directory': str(directory), 'path': 'evaluations/' + eid}
        for name in ('summary.json', 'results.jsonl', 'evaluator-snapshot/requirements-ledger.json'):
            if (directory / name).exists():
                sources['evaluations/' + eid + '/' + name] = directory / name
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        # Validate before sealing, including missingness and every selected binding.
        export(root, validity, output=temporary / 'validation-export')
        write_new(temporary / 'evaluation-locations.json', locations)
        sources['evaluation-locations.json'] = temporary / 'evaluation-locations.json'
        return pack(archive, 'analysis-' + str(uuid.uuid4()), sources,
                    metadata={'kind': 'analysis-originals', 'experiment_id': config['experiment_id'],
                              'synthetic': config.get('synthetic', False)})


def restore_analysis(archive, reference, destination):
    destination.mkdir(parents=True, exist_ok=False)
    receipt = restore(archive, reference, destination / 'payload')
    shutil.copy2(archive / 'packages' / reference['package_id'] / 'package.json',
                 destination / 'package.json')
    write_new(destination / 'restoration-map.json', {
        'schema_version': 1, 'payload': 'payload', 'package_index': 'package.json',
        'package_sha256': reference['sha256'], 'receipt': receipt})
    return destination / 'restoration-map.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('pack')
    p.add_argument('root', type=Path); p.add_argument('validity', type=Path)
    p.add_argument('archive', type=Path); p.add_argument('reference', type=Path)
    p = sub.add_parser('restore')
    p.add_argument('archive', type=Path); p.add_argument('reference', type=Path)
    p.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.action == 'pack':
        write_new(args.reference, preserve_analysis(args.root, args.validity, args.archive))
    else:
        print(restore_analysis(args.archive, read(args.reference), args.destination))
