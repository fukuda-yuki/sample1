"""Post hoc accounting breakdown from saved gateway metadata; no response bodies."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def capture():
    rows=[]
    for batch,folder in [('previous','acquisition10-20260910'),('additional','acquisition20-20260911')]:
        base=ROOT/'results'/folder/'batch'
        for row in read(base/'run-index.json')['runs']:
            if not row['run_id']:continue
            run=base/'runs'/row['planned_run']/'attempt';path=run/'raw-usage/events.jsonl'
            if not path.exists() or not (run/'usage.json').exists() or not (run/'snapshot.json').exists():continue
            events=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            unique={}
            for e in events:
                assert e['run_id']==row['run_id'] and e['mode']=='request' and not e.get('includes_children',False)
                u=e.get('usage')
                if not u or u.get('input_tokens') is None or u.get('output_tokens') is None:continue
                counts=(u['input_tokens'],u['output_tokens'],u.get('input_tokens_details',{}).get('cached_tokens'))
                key=e['request_id']
                if key in unique:assert unique[key]==counts
                unique[key]=counts
            values=list(unique.values());original=read(run/'usage.json')
            inputs=sum(v[0] for v in values);outputs=sum(v[1] for v in values)
            assert inputs+outputs==original['observed_tokens']
            assert len(values)==original['observed_request_count']
            cached=[v[2] for v in values if v[2] is not None]
            assert all(0<=v[2]<=v[0] for v in values if v[2] is not None)
            rows.append(dict(batch=batch,run_id=row['run_id'],planned_run=row['planned_run'],
                submission_hash=sha(run/'snapshot.json'),recorded_input_tokens=inputs,recorded_output_tokens=outputs,
                recorded_cached_input_tokens=sum(cached) if len(cached)==len(values) else None,
                cached_detail_requests=len(cached),usage_requests=len(values),
                raw_events=str(path.relative_to(ROOT)),raw_events_sha256=sha(path),usage_sha256=sha(run/'usage.json')))
    return {'scope':'Post hoc descriptive accounting prompted by a high-token Run. Input and cached-input counts do not measure price, useful work, or reasoning quality. Missing cache details are not imputed.',
            'rows':rows,'model_calls':0,'evaluations':0}
