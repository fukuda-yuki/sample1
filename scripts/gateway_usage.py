"""Reconcile started calls with terminal usage, including interrupted calls."""
import argparse
import json
from pathlib import Path
from normalize_usage import normalize, VERSION


def collect(directory):
    issues = []
    def read(name):
        path = directory / name
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeError) as error:
            issues.append({'reason': 'raw_usage_read_error', 'file': name, 'error': type(error).__name__})
            return []
        events = []
        for number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict) or not isinstance(event.get('event_id'), str):
                    raise ValueError('Invalid event')
                events.append(event)
            except ValueError:
                issues.append({'reason': 'malformed_raw_usage', 'file': name, 'line': number})
        return events
    started, finished = read('started.jsonl'), read('events.jsonl')
    def index(events, name):
        indexed, conflicts = {}, set()
        for event in events:
            identity = event['event_id']
            if identity in indexed and indexed[identity] != event:
                conflicts.add(identity)
                issues.append({'reason': 'conflicting_gateway_event', 'file': name, 'event_id': identity})
            indexed[identity] = event
        for identity in conflicts:
            indexed.pop(identity, None)
        return indexed
    beginnings, terminal = index(started, 'started.jsonl'), index(finished, 'events.jsonl')
    for identity in set(terminal) - set(beginnings):
        issues.append({'reason': 'terminal_without_start', 'event_id': identity})
    events = []
    for identity, event in beginnings.items():
        completion = terminal.get(identity)
        if completion and any(completion.get(key) != event.get(key) for key in
                              ('run_id', 'session_id', 'request_id', 'model_id', 'provider')):
            issues.append({'reason': 'gateway_event_identity_mismatch', 'event_id': identity})
            completion = None
        events.append(completion or event)
    try:
        result = normalize(events, ['implementation'], inventory_complete=bool(started) and not issues)
    except (ValueError, KeyError, TypeError) as error:
        result = {'normalizer_version': VERSION, 'usage_complete': False, 'total_tokens': None,
                  'observed_tokens': None, 'observed_request_count': None, 'sessions': {},
                  'missing': [{'reason': 'usage_normalization_error', 'error': str(error)}],
                  'cumulative_sessions': []}
    if issues:
        result.update(usage_complete=False, total_tokens=None)
        result['missing'].extend(issues)
    result['source'] = 'fixed-upstream-gateway'
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    args=parser.parse_args()
    args.output.write_text(json.dumps(collect(args.directory),indent=2),encoding='utf-8')
