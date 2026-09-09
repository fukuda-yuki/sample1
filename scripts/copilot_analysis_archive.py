"""Explicit private analysis originals package; no model calls or start authority."""
import argparse
from pathlib import Path
import shutil
import tempfile
import uuid
from copilot_batch import load, export, ROOT
from preserve import pack, restore, read, write_new, digest, safe_name


def analysis_sources(root, validity):
    config, index = load(root)
    sources = {'batch/' + name: root / name for name in
               ('experiment.json', 'planned-runs.json', 'run-index.json')}
    sources['validity.json'] = validity
    input_root=root/'inputs' if config.get('batch_schema')==2 else ROOT
    sources.update({'inputs/'+name: input_root/name for name in config['input_hashes']})
    for folder in ('scripts','analysis'):
        for source in (ROOT/folder).glob('*.py'):
            sources['management/'+folder+'/'+source.name]=source
    sources['management/analysis/requirements.txt']=ROOT/'analysis/requirements.txt'
    for name in ('dispatches','plan-revisions','parallel-control.json',
                 'source-experiment.json','source-run-index.json','rescore-plan.json',
                 'reanalysis-source.json','pre-v3-experiment.json',
                 'pre-v3-run-index.json','rescore-plan-v3.json'):
        if (root/name).exists():sources['batch/'+name]=root/name
    # The complete registry may reference historical adjudications even when the
    # selected Runs are new. Keep its bytes and relative dependency paths intact.
    for record in read(validity)['attempts']:
        dependencies = [(r['path'], r['sha256']) for r in record.get('adjudications', [])+record.get('evidence',[])]
        legacy = record.get('legacy_adjudication_binding')
        if legacy:
            dependencies.append((legacy['config_path'], legacy['config_sha256']))
        for name, expected in dependencies:
            safe_name(name)
            source = validity.parent / name
            if not source.resolve().is_relative_to(validity.parent.resolve()):
                raise ValueError('Validity dependency must stay beside its registry')
            if digest(source) != expected:
                raise ValueError('Validity dependency original changed')
            if name in sources and sources[name] != source:
                raise ValueError('Conflicting validity dependency path')
            sources[name] = source
    locations = {}
    for slot in index['runs']:
        if slot['run_id'] is None:
            continue
        relative = 'batch/runs/' + slot['planned_run'] + '/attempt/'
        run = root / 'runs' / slot['planned_run'] / 'attempt'
        for name in ('assignment.json','worker-started.json','execution-result.json','evaluation-jobs','recovery-history'):
            if (run.parent/name).exists():sources['batch/runs/'+slot['planned_run']+'/'+name]=run.parent/name
        for name in ('manifest.json', 'snapshot.json', 'frozen', 'usage.json',
                     'telemetry', 'telemetry-link.json', 'raw-usage', 'evaluation-ref.json',
                     'inputs','management-source','agent.stdout.log','agent.stderr.log','cleanup-result.json','evaluation-refs',
                     'source-evaluation-ref.json','preservation.json','linked-preservation.json','linked-restoration.json',
                     'evaluation-preservation.json','evaluation-restoration.json','evaluation-restorations'):
            if (run / name).exists():
                sources[relative + name] = run / name
        if not (run / 'evaluation-ref.json').exists():
            continue
        references=[run/'evaluation-ref.json', *sorted((run/'evaluation-refs').glob('*.json'))]
        for path in references:
            ref=read(path); eid=ref['evaluation_id']; directory=Path(ref['evaluation_directory'])
            location={'original_directory':str(directory),'path':'evaluations/'+eid}
            if eid in locations and locations[eid]!=location:
                raise ValueError('Conflicting evaluation history')
            locations[eid]=location
            sources['evaluations/'+eid]=directory
            if (directory.parent/'management-evidence').exists():
                sources['evaluation-preparation/'+eid]=directory.parent/'management-evidence'
    from preserve import tree
    flattened={}
    for name,path in sources.items():
        files={name+'/'+relative:path/relative for relative in tree(path)} if path.is_dir() else {name:path}
        for relative,source in files.items():
            if relative in flattened and digest(flattened[relative])!=digest(source):
                raise ValueError('Conflicting preserved original: '+relative)
            flattened[relative]=source
    return flattened,locations


def immutable_inventory(root, validity):
    """Use the preservation allowlist, never walk mutable working dependencies."""
    from preserve import tree
    sources,_=analysis_sources(root,validity)
    return {name:tree(path) if path.is_dir() else digest(path) for name,path in sources.items()}


def preserve_analysis(root, validity, archive):
    config,_=load(root)
    sources,locations=analysis_sources(root,validity)
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
