"""One-time researcher preparation; no model calls or implementation starts."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import uuid
import tarfile
from preserve import pack, restore, write_new, digest
from run_experiment import snapshot


def compact(common, stage):
    for relative in ('evaluator/node_modules', 'evaluator/tools', 'historical-calibration'):
        source = common / relative
        if not source.exists():
            continue
        with tarfile.open(str(source) + '.tar', 'w', dereference=True) as target:
            target.add(source, arcname=source.name)
        # Keep the staging source outside the package; no original is deleted.
        source.rename(stage / ('expanded-' + source.name))


def main(root, archive, stage):
    root, stage = root.resolve(), stage.resolve()
    stage.mkdir(parents=True, exist_ok=False)
    legacy = stage / 'legacy'
    legacy.mkdir()
    incident = {'recorded_at': datetime.now(timezone.utc).isoformat(),
                'status': 'originals_missing_unevaluable', 'cause': 'unconfirmed',
                'last_presence_evidence': 'Historical Issue #11 stop record and docs/pilot-artifacts/pilot-provenance.json; not a current original verification',
                'first_missing_evidence': 'docs/evaluator-repair-verification.json recorded_at=2026-09-05T16:10:30.016241+00:00',
                'operation_history': 'Git history and preserved Issue records reviewed; no evidenced deletion operation identified',
                'quality': None, 'usage_status': 'historical_reconciliation_only', 'runs': []}
    for condition in ('normal', 'anti'):
        old = root / 'results/runs' / ('pilot-1-' + condition)
        target = legacy / ('pilot-1-' + condition)
        target.mkdir()
        hashes = snapshot(old / 'working')
        for relative in hashes:
            dest = target / 'working-investigation-only' / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old / 'working' / relative, dest)
        write_new(target / 'working-inventory.json', hashes)
        for name in ('management-source', 'raw-usage', 'raw-usage-recovery'):
            if (old / name).exists():
                shutil.copytree(old / name, target / name)
        incident['runs'].append({'condition': condition, 'frozen_files': len(snapshot(old / 'frozen')),
                                'missing': [n for n in ('manifest.json', 'snapshot.json', 'usage.json', 'native-usage.json') if not (old / n).exists()],
                                'working_is_submission': False})
    write_new(legacy / 'incident.json', incident)
    # Evaluator outputs are researcher-owned; these paths contain no implementation transcripts/auth.
    private = root.parent / 'sample1-private-eval-linux'
    sources = {'legacy': legacy, 'historical-public-records': root / 'docs/pilot-artifacts',
               'evaluations': private / 'evaluations', 'evaluation-validity.json': private / 'evaluation-validity.json'}
    ref = pack(archive, 'legacy-investigation-' + str(uuid.uuid4()), sources,
               metadata={'kind': 'investigation-only', 'originals_recovered': False})
    receipt = restore(archive, ref, stage / 'legacy-restored')
    write_new(stage / 'legacy-reference.json', {'reference': ref, 'receipt': receipt})
    write_new(root / 'docs/original-loss-incident.json', dict(incident, preservation={'reference': ref, 'receipt': receipt}))
    common = stage / 'common'
    common.mkdir()
    evaluator = common / 'evaluator'
    evaluator.mkdir()
    for name in ('run.mjs', 'playwright.config.ts', 'package.json', 'package-lock.json',
                 'case-manifest.json', 'requirements-ledger.json', 'tests', 'node_modules', 'tools'):
        source = private / name
        if source.is_dir():
            shutil.copytree(source, evaluator / name, symlinks=False)
        else:
            shutil.copy2(source, evaluator / name)
    original = root.parent / 'sample1-private-eval'
    shutil.copytree(original / 'calibration', evaluator / 'calibration')
    shutil.copy2(original / 'calibrate.mjs', evaluator / 'calibrate.mjs')
    shutil.copytree(original / 'calibration-runs', common / 'historical-calibration')
    images = [json.loads((root / 'config/experiment.json').read_text())['environment']['image'],
              'python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea',
              'mcr.microsoft.com/playwright@sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d']
    runtime = common / 'runtime'
    runtime.mkdir()
    records = []
    for index, image in enumerate(images):
        target = runtime / (str(index) + '.tar')
        subprocess.run(['docker', 'image', 'save', '-o', str(target), image], check=True)
        records.append({'image': image, 'file': target.name, 'sha256': digest(target)})
    write_new(runtime / 'images.json', records)
    compact(common, stage)
    print(json.dumps({'stage': str(stage), 'legacy': ref, 'runtime': records}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path); p.add_argument('archive', type=Path); p.add_argument('stage', type=Path)
    a = p.parse_args(); main(a.root, a.archive, a.stage)
