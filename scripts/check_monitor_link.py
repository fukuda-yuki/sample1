"""Use the actual monitor importer with a disposable explicit DB; no model."""
import argparse
import json
from pathlib import Path
import subprocess
import sqlite3
from contextlib import closing
from test_telemetry_link import fixture
from telemetry_link import link, atomic, native_to_otlp, inventory, readback


def main(output, command):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    locator={'instance_id':'synthetic-monitor-'+output.name,'database_path':str(output/'monitor.db'),
             'import_command':command,'kind':'actual-monitor-synthetic-input'}
    atomic(output/'locator.json',locator)
    target, other=output/'target',output/'unrelated'
    rid,eid=fixture(target)
    fixture(other,experiment_id=eid)
    first=link(other,locator,ingest=True,initialize=True)
    result=link(target,locator,ingest=True)
    repeated=link(target,locator,ingest=True)
    assert result['usage_complete'] and repeated['usage_complete']
    assert result['ingestion']['records']==repeated['ingestion']['records']
    assert set(result['trace_ids']).isdisjoint(first['trace_ids'])
    # Explicitly repeat the importer too: even duplicate physical rows do not add tokens.
    subprocess.run([*command,'ingest-raw',str(target/'telemetry/otlp.json'),'--db',locator['database_path']],
                   check=True,capture_output=True,timeout=120)
    repeat_raw=link(target,locator)
    assert repeat_raw['usage_complete']
    assert json.loads((target/'usage.json').read_text())['total_tokens']==27
    # SQLite's online backup includes the committed WAL view; never copy .db alone.
    backup=output/'moved-monitor.db'
    with closing(sqlite3.connect(Path(locator['database_path']).as_uri()+'?mode=ro',uri=True)) as source:
        with closing(sqlite3.connect(backup)) as destination:source.backup(destination)
    relocated=link(target,dict(locator,database_path=str(backup)))
    assert relocated['trace_ids']==repeat_raw['trace_ids'] and relocated['usage_complete']
    # Wrong DB must not silently create a database or retain a complete total.
    try:
        link(target,dict(locator,database_path=str(output/'absent.db')))
        raise AssertionError('wrong DB accepted')
    except ValueError:
        assert json.loads((target/'usage.json').read_text())['total_tokens'] is None
    repeat_raw=link(target,locator)
    # An unrelated Run claiming a target native span ID is an error, not a filter match.
    collision=json.loads((target/'telemetry/otlp.json').read_text())
    collision['resourceSpans'][0]['resource']['attributes'][0]['value']['stringValue']='unrelated'
    atomic(output/'collision.json',collision)
    subprocess.run([*command,'ingest-raw',str(output/'collision.json'),'--db',locator['database_path']],
                   check=True,capture_output=True,timeout=120)
    try:
        link(target,locator)
        raise AssertionError('ID collision accepted')
    except ValueError:
        assert json.loads((target/'usage.json').read_text())['total_tokens'] is None
    evidence={'kind':'actual-monitor-synthetic-input','model_called':False,'target_only':True,
              'reimport_idempotent':True,'raw_duplicate_deduped':True,'multiple_sessions':True,
              'tokens_before_collision':27,'wrong_db_rejected':True,'id_collision_rejected':True,'consistent_backup_relocated':True,
              'monitor':locator,'ingestion':repeat_raw['ingestion']}
    atomic(output/'evidence.json',evidence)
    print(json.dumps(evidence))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('import_command',nargs=argparse.REMAINDER)
    a=p.parse_args();main(a.output,a.import_command)
