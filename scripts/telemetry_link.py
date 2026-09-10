"""Copilot 1.0.83-5 file exporter -> official monitor importer -> read-only proof.

Native IDs are preserved. No timestamp/repository/model heuristic selects a Run.
Only chat spans are token observations; root totals and metric histograms are not.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import uuid
from contextlib import closing
from gateway_usage import collect
from preserve import digest, read


def atomic(path, data):
    import os, uuid
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + str(uuid.uuid4()) + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2);stream.flush();os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        if temp.exists():temp.unlink()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def attributes(values):
    out = {}
    for item in values:
        value = item['value']
        v = next(iter(value.values()))
        if 'intValue' in value:
            v = int(v)
        if item['key'] in out and out[item['key']] != v:
            raise ValueError('Conflicting attribute')
        out[item['key']] = v
    return out


def kv(values):
    result = []
    for k, v in values.items():
        if isinstance(v, bool):
            value = {'boolValue': v}
        elif isinstance(v, int):
            value = {'intValue': str(v)}
        elif isinstance(v, float):
            value = {'doubleValue': v}
        elif isinstance(v, str):
            value = {'stringValue': v}
        else:
            continue
        result.append({'key': k, 'value': value})
    return result


def native_to_otlp(path):
    resources, ignored, problems = [], {}, []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if item.get('type') in ('metric', 'metrics', 'log'):
                ignored[item['type']] = ignored.get(item['type'], 0) + 1
                continue
            if item.get('type') != 'span':
                raise ValueError('Unsupported native signal')
            span = {k: item[k] for k in ('traceId', 'spanId', 'name')}
            span['parentSpanId'] = item.get('parentSpanId') or ''
            span['kind'] = int(item.get('kind', 0)) + 1  # SDK SpanKind starts at zero; OTLP starts at one.
            for source, target in [('startTime', 'startTimeUnixNano'), ('endTime', 'endTimeUnixNano')]:
                seconds, nanos = item[source]
                span[target] = str(seconds * 1000000000 + nanos)
            span['attributes'] = kv(item['attributes'])
            span['status'] = item.get('status', {})
            resources.append({'resource': {'attributes': kv(item['resource']['attributes'])},
                              'scopeSpans': [{'scope': item.get('instrumentationScope', {}), 'spans': [span]}]})
        except (ValueError, KeyError, TypeError) as e:
            problems.append({'line': number, 'reason': type(e).__name__})
    return {'resourceSpans': resources}, ignored, problems


def spans(payload):
    for resource in payload.get('resourceSpans', []):
        attrs = attributes(resource.get('resource', {}).get('attributes', []))
        for scope in resource.get('scopeSpans', []):
            for span in scope.get('spans', []):
                yield attrs, span


def inventory(payload, run_id, experiment_id):
    found = {}
    for resource, span in spans(payload):
        if resource.get('run.id') != run_id or resource.get('experiment.id') != experiment_id:
            raise ValueError('Native spool contains a different Run')
        if resource.get('client.kind') != 'copilot-cli':
            raise ValueError('Wrong CLI source')
        key = (span['traceId'], span['spanId'])
        import re
        if not re.fullmatch('[0-9a-f]{32}', key[0]) or not re.fullmatch('[0-9a-f]{16}', key[1]):
            raise ValueError('Invalid native identity')
        entry = {'resource': resource, 'span': span}
        if key in found and found[key] != entry:
            raise ValueError('Conflicting native span')
        found[key] = entry
    if not found:
        raise ValueError('No native spans')
    return found


def db_read(db):
    if not db.is_absolute() or not db.is_file():
        raise ValueError('Explicit existing absolute monitor DB required')
    connection = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=30)
    connection.execute('PRAGMA query_only=ON')
    connection.execute('BEGIN')
    return connection


def readback(db, expected, run_id, experiment_id):
    found, receipts, projection = {}, [], []
    with closing(db_read(db)) as connection:
        schemas = connection.execute('SELECT component,version FROM schema_version ORDER BY component').fetchall()
        # Scan all records in one WAL-consistent read transaction; no LIMIT or recency filter.
        for raw_id, raw in connection.execute('SELECT id,payload_json FROM raw_records ORDER BY id'):
            payload = json.loads(raw)
            selected = []
            for resource, span in spans(payload):
                key = (span['traceId'], span['spanId'])
                belongs = resource.get('run.id') == run_id and resource.get('experiment.id') == experiment_id
                if key in expected and not belongs:
                    raise ValueError('Native ID collision with unrelated Run')
                if not belongs:
                    continue
                entry = {'resource': resource, 'span': span}
                if key not in expected or entry != expected[key]:
                    raise ValueError('DB and native spool differ')
                if key in found and found[key] != entry:
                    raise ValueError('Conflicting DB duplicate')
                found[key] = entry
                selected.append(key)
            if selected:
                receipts.append({'raw_record_id': raw_id, 'payload_sha256': hashlib.sha256(raw.encode()).hexdigest()})
                try:
                    projected = connection.execute('SELECT id FROM monitor_ingestions WHERE raw_record_id=?', (raw_id,)).fetchone()
                except sqlite3.OperationalError:
                    projected = None
                projection.append(bool(projected))
    return found, {'records': receipts, 'schema': schemas, 'projection_complete': bool(projection) and all(projection)}


def reconcile(raw, expected, run_id):
    usage = collect(raw)
    problems = list(usage['missing'])
    chats, sessions, relations = {}, set(), []
    for (trace_id, span_id), entry in expected.items():
        span = entry['span']
        a = attributes(span['attributes'])
        session = a.get('gen_ai.conversation.id')
        if not session:
            problems.append({'reason': 'native_session_missing', 'span_id': span_id})
        else:
            sessions.add(session)
        parent = span.get('parentSpanId')
        if parent and (trace_id, parent) not in expected:
            problems.append({'reason': 'parent_span_missing', 'span_id': span_id})
        relations.append({'trace_id': trace_id, 'span_id': span_id, 'parent_span_id': parent,
                          'session_id': session, 'parent_session_id': a.get('gen_ai.parent.conversation.id')})
        if a.get('gen_ai.operation.name') != 'chat':
            continue
        response = a.get('gen_ai.response.id')
        counts = (a.get('gen_ai.usage.input_tokens'), a.get('gen_ai.usage.output_tokens'))
        if not response or any(type(n) is not int or n < 0 for n in counts) or response in chats:
            problems.append({'reason': 'chat_identity_or_usage_invalid', 'span_id': span_id})
        else:
            chats[response] = {'tokens': counts, 'trace_id': trace_id, 'span_id': span_id, 'session_id': session}
    responses, calls = set(), []
    try:
        ends = [json.loads(line) for line in (raw / 'events.jsonl').read_text().splitlines() if line]
        unique = {}
        for event in ends:
            if event['run_id'] != run_id:
                raise ValueError('Wrong gateway Run')
            identity = event['request_id']
            if identity in unique and unique[identity] != event:
                raise ValueError('Conflicting gateway duplicate')
            unique[identity] = event
        for event in unique.values():
            response = event.get('provider_response_id')
            u = event.get('usage') or {}
            if response not in chats or response in responses or chats[response]['tokens'] != (u.get('input_tokens'), u.get('output_tokens')):
                problems.append({'reason': 'request_native_mismatch', 'request_id': event['request_id']})
            else:
                calls.append(dict(chats[response], response_id=response, request_id=event['request_id']))
            responses.add(response)
        if responses != set(chats):
            problems.append({'reason': 'native_request_inventory_mismatch'})
    except (OSError, ValueError, KeyError, TypeError):
        problems.append({'reason': 'gateway_inventory_invalid'})
    usage.update(usage_complete=not problems, total_tokens=usage['observed_tokens'] if not problems else None, missing=problems)
    return usage, sorted(sessions), relations, calls


def _link(run, locator, *, ingest=False, initialize=False):
    manifest = read(run / 'manifest.json')
    run_id, experiment_id = manifest['run_id'], manifest['experiment_id']
    db = Path(locator['database_path'])
    if not db.is_absolute():
        raise ValueError('Absolute monitor database path required')
    if not locator.get('instance_id') or not locator.get('import_command'):
        raise ValueError('Monitor instance and actual importer command required')
    build_files = {str(Path(arg).resolve()): digest(Path(arg)) for arg in locator['import_command'] if Path(arg).is_file()}
    if not build_files:
        raise ValueError('Importer executable or DLL must be an existing absolute file')
    payload, ignored, problems = native_to_otlp(run / 'telemetry/native.jsonl')
    expected = inventory(payload, run_id, experiment_id)
    converted = run / 'telemetry/otlp.json'
    atomic(converted, payload)
    evidence = {'run_id': run_id, 'experiment_id': experiment_id, 'monitor': dict(locator, build_files_sha256=build_files),
                'native_sha256': digest(run / 'telemetry/native.jsonl'), 'otlp_sha256': digest(converted),
                'status': 'pending', 'ignored_signals': ignored, 'adapter_problems': problems}
    atomic(run / 'telemetry-link.json', evidence)
    try:
        if not db.exists() and not (initialize and ingest):
            raise ValueError('Monitor DB does not exist; explicit initialize required for new instance')
        before, receipt = readback(db, expected, run_id, experiment_id) if db.exists() else ({}, {})
        if ingest and before != expected:
            subprocess.run([*locator['import_command'], 'ingest-raw', str(converted.resolve()), '--db', str(db)],
                           check=True, capture_output=True, timeout=120)
        found, receipt = readback(db, expected, run_id, experiment_id)
        usage, sessions, relations, calls = reconcile(run / 'raw-usage', expected, run_id)
        reasons = []
        if found != expected:
            reasons.append({'reason': 'monitor_ingestion_pending'})
        if problems:
            reasons.append({'reason': 'native_spool_corrupt'})
        if not manifest.get('processes_stopped'):
            reasons.append({'reason': 'producer_stop_unconfirmed'})
        if reasons:
            usage.update(usage_complete=False, total_tokens=None, missing=usage['missing'] + reasons)
        evidence.update(status='readback_verified' if found == expected else 'pending',
                        session_ids=sessions, trace_ids=sorted({k[0] for k in expected}),
                        relationships=relations, model_calls=calls, ingestion=receipt,
                        usage_complete=usage['usage_complete'],
                        submission_hash=digest(run / 'snapshot.json'), gateway_usage_hash=canonical(collect(run / 'raw-usage')))
        atomic(run / 'usage.json', usage)
    except (OSError, ValueError, KeyError, sqlite3.Error, subprocess.SubprocessError) as error:
        evidence.update(status='failed', error=type(error).__name__ + ': ' + str(error))
        usage = collect(run / 'raw-usage')
        usage.update(usage_complete=False, total_tokens=None, missing=usage['missing'] + [{'reason': 'monitor_link_failed'}])
        atomic(run / 'usage.json', usage)
        raise
    finally:
        atomic(run / 'telemetry-link.json', evidence)
    return evidence


def link(run, locator, *, ingest=False, initialize=False):
    try:
        return _link(run, locator, ingest=ingest, initialize=initialize)
    except (OSError, ValueError, KeyError, sqlite3.Error, subprocess.SubprocessError) as error:
        usage=collect(run/'raw-usage')
        usage.update(usage_complete=False,total_tokens=None,
                     missing=usage['missing']+[{'reason':'monitor_link_failed'}])
        atomic(run/'usage.json',usage)
        atomic(run/'telemetry-link.json',{'run_id':read(run/'manifest.json')['run_id'],
               'monitor':locator,'status':'failed','error':type(error).__name__})
        raise


def project_measurement(run, destination):
    """Append a source-bound v2 projection without altering legacy evidence.

    Gateway accounting, native call correspondence, trace hierarchy and monitor
    delivery are independent observations. A hierarchy defect does not erase
    successfully captured gateway usage.
    """
    from preserve import write_new
    destination.mkdir(parents=True, exist_ok=False)
    manifest = read(run/'manifest.json')
    gateway = collect(run/'raw-usage')
    if (run/'raw-usage/started.jsonl').exists():
        try:
            starts=[json.loads(line) for line in (run/'raw-usage/started.jsonl').read_text().splitlines() if line.strip()]
            if any(e.get('run_id') != manifest['run_id'] for e in starts):
                gateway.update(usage_complete=False,total_tokens=None,missing=gateway['missing']+[{'reason':'gateway_run_mismatch'}])
        except (ValueError, TypeError): pass  # collect already reports malformed raw records.
    native, adapter, calls, relations, sessions = [], [], [], [], []
    try:
        payload, ignored, adapter = native_to_otlp(run/'telemetry/native.jsonl')
        expected = inventory(payload, manifest['run_id'], manifest['experiment_id'])
        reconciled, sessions, relations, calls = reconcile(run/'raw-usage', expected, manifest['run_id'])
        native = [p for p in reconciled['missing'] if p not in gateway['missing']]
    except (OSError, ValueError, KeyError, TypeError) as error:
        adapter = [{'reason':'native_processing_failed', 'error_type':type(error).__name__}]
    hierarchy = [p for p in native if p.get('reason') == 'parent_span_missing']
    correspondence = [p for p in native if p.get('reason') != 'parent_span_missing'] + adapter
    try: monitor = read(run/'telemetry-link.json') if (run/'telemetry-link.json').exists() else {}
    except (OSError,ValueError): monitor = {'status':'failed'}
    from preserve import tree
    result = dict(schema_version=2, processing_id=destination.name, run_id=manifest['run_id'],
        submission_hash=digest(run/'snapshot.json'), processor_sha256=digest(Path(__file__)),
        input_hashes={n:digest(run/n) for n in ('manifest.json','snapshot.json','telemetry/native.jsonl','telemetry-link.json') if (run/n).exists()},
        raw_usage_hashes=tree(run/'raw-usage'), gateway=gateway,
        native_calls=dict(verified=not correspondence and bool(calls), problems=correspondence, count=len(calls)),
        trace_structure=dict(complete=not hierarchy and not adapter, problems=hierarchy+adapter),
        monitor=dict(status=monitor.get('status','not_attempted')),
        total_tokens=gateway['total_tokens'], usage_complete=gateway['usage_complete'],
        observed_tokens=gateway['observed_tokens'], total_tokens_basis='fixed-upstream-gateway')
    write_new(destination/'measurement.json', result)
    return result


def selected_measurement(run):
    """Validate an explicit processing selection against immutable raw inputs."""
    reference = run/'measurement-ref.json'
    if not reference.exists(): return None
    from preserve import tree, safe_name
    ref = read(reference); name = ref['path']; safe_name(name)
    target = run/name
    if digest(target) != ref['sha256']: raise ValueError('Measurement selection changed')
    value = read(target)
    if value['run_id'] != read(run/'manifest.json')['run_id'] or value['submission_hash'] != digest(run/'snapshot.json'):
        raise ValueError('Measurement identity changed')
    for name, expected in value['input_hashes'].items():
        if digest(run/name) != expected: raise ValueError('Measurement source changed')
    if tree(run/'raw-usage') != value['raw_usage_hashes']: raise ValueError('Raw accounting changed')
    current=collect(run/'raw-usage')
    if not any(p.get('reason')=='gateway_run_mismatch' for p in value['gateway']['missing']) and value['gateway'] != current:
        raise ValueError('Selected gateway accounting mismatch')
    return value


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path)
    p.add_argument('locator',type=Path)
    p.add_argument('--ingest',action='store_true')
    p.add_argument('--initialize',action='store_true')
    a=p.parse_args()
    print(json.dumps(link(a.run,read(a.locator),ingest=a.ingest,initialize=a.initialize)))
