"""Reconcile started calls with terminal usage, including interrupted calls."""
import argparse
import json
from pathlib import Path
from normalize_usage import normalize


def collect(directory):
    def read(name):
        path = directory / name
        return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []
    started, finished = read('started.jsonl'), read('events.jsonl')
    terminal = {e['event_id']: e for e in finished}
    events = [terminal.get(e['event_id'], e) for e in started]
    if len(terminal) != len(finished) or set(terminal) - {e['event_id'] for e in started}:
        raise ValueError('Gateway request inventory inconsistent')
    result = normalize(events, ['implementation'], inventory_complete=bool(started))
    result['source'] = 'fixed-upstream-gateway'
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    args=parser.parse_args()
    args.output.write_text(json.dumps(collect(args.directory),indent=2),encoding='utf-8')
