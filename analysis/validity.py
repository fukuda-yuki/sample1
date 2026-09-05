"""Bind researcher adjudications to immutable evaluation attempts."""
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_registry(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if data['schema_version'] != 1:
        raise ValueError('Unknown validity registry version')
    records = {}
    for record in data['attempts']:
        identity = record['evaluation_id']
        if not identity or identity in records:
            raise ValueError('Duplicate or empty evaluation validity identity')
        if record['status'] not in ('valid', 'invalid', 'pending') or not record['reason']:
            raise ValueError('Validity requires a known status and reason')
        for field in ('run_id', 'submission_hash', 'evaluator_hash', 'summary_hash', 'results_hash'):
            if field not in record:
                raise ValueError('Missing validity binding: ' + field)
        for reference in record.get('adjudications', []):
            source = Path(reference['path'])
            if not source.is_absolute():
                source = path.parent / source
            if digest(source) != reference['sha256']:
                raise ValueError('Adjudication original changed')
            adjudication = json.loads(source.read_text(encoding='utf-8-sig'))
            legacy = record.get('legacy_adjudication_binding')
            if 'run_id' not in adjudication and legacy:
                config_path = path.parent / legacy['config_path']
                if digest(config_path) != legacy['config_sha256']:
                    raise ValueError('Legacy adjudication config changed')
                config = json.loads(config_path.read_text(encoding='utf-8-sig'))
                adjudication = dict(adjudication, run_id=config['run_id'])
            for field in ('evaluation_id', 'run_id'):
                if adjudication.get(field) != record[field]:
                    raise ValueError('Adjudication identity mismatch')
            if (adjudication.get('submission_snapshot_sha256') is not None
                    and adjudication['submission_snapshot_sha256'] != record['submission_hash']):
                raise ValueError('Adjudication submission mismatch')
            if str(adjudication.get('outcome', adjudication.get('disposition', ''))).startswith('invalid_') and record['status'] == 'valid':
                raise ValueError('Invalid adjudication cannot be promoted to valid; evaluate a new attempt')
        records[identity] = record
    return records, digest(path)


def resolve(records, registry_hash, identity, summary, directory):
    record = records.get(identity)
    if record is None:
        return dict(evaluation_validity='pending', validity_reason='No validity record for evaluation attempt',
                    validity_record_hash=None, validity_registry_hash=registry_hash)
    expected = {k: summary[k] for k in ('run_id', 'submission_hash', 'evaluator_hash')}
    expected.update(summary_hash=digest(directory / 'summary.json'), results_hash=digest(directory / 'results.jsonl'))
    if any(record[k] != value for k, value in expected.items()):
        raise ValueError('Validity record does not match Run, submission, evaluator or raw results')
    return dict(evaluation_validity=record['status'], validity_reason=record['reason'],
                validity_record_hash=hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False,
                                                              separators=(',', ':')).encode()).hexdigest(),
                validity_registry_hash=registry_hash)
