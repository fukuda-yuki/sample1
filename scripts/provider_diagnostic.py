"""Five fixed management probes: providers parallel, each provider serial, no retries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
from zen_diagnostic import credential, sanitized, response_metadata
from preserve import read, write_new

PROVIDERS = {'zen': ('opencode.ai', '/zen/v1', 'OPENCODE_ZEN_API_KEY'),
             'openai': ('api.openai.com', '/v1', 'OPENAI_API_KEY')}
MATRIX = {'zen': [('muse-spark-1.3-contributor-free', 'responses'),
                  ('mimo-v2.5-free', 'chat/completions'),
                  ('nemotron-3-ultra-free', 'chat/completions')],
          'openai': [('gpt-4.1-mini-2025-04-14', 'responses'),
                     ('gpt-4.1-mini-2025-04-14', 'chat/completions')]}


def now():
    return datetime.now(timezone.utc).isoformat()


def body_for(model, api):
    if api == 'responses':
        return {'model': model, 'input': 'Reply with OK.', 'max_output_tokens': 256,
                'stream': False, 'store': False}
    return {'model': model, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
            'max_tokens': 256, 'stream': False}


def exchange(provider, api, directory, model=None):
    """Runs only in a killable subprocess. Keys never cross argv/stdout or providers."""
    host, prefix, variable = PROVIDERS[provider]
    if api != 'models' and (model, api) not in MATRIX[provider]:
        raise ValueError('unsupported_target')
    key, _ = credential(variable, windows_user_only=True)
    connection = http.client.HTTPSConnection(host, timeout=30)
    try:
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                   'User-Agent': 'sample1-research-diagnostic/1'}
        if provider == 'zen': headers['x-opencode-session'] = str(uuid.UUID(directory.name))
        body = json.dumps(body_for(model, api)) if model else None
        connection.request('POST' if model else 'GET', prefix + '/' + api, body=body, headers=headers)
        response = connection.getresponse()
        allowed, _ = response_metadata(dict(response.getheaders()), b'', key)
        # Save headers immediately, even if receiving the body hits the deadline.
        write_new(directory/'http.json', {'http_status': response.status, 'headers': allowed,
                  'headers_received_at': now()})
        raw = response.read(1024 * 1024 + 1)
        if len(raw)>1024*1024: raise ValueError('response_size_limit')
        text = sanitized(raw.decode('utf-8', errors='replace'), key, 1024*1024)
        write_new(directory/'response.json', {'body': text, 'body_present': bool(raw),
                  'sanitized': True, 'received_at': now()})
    finally:
        connection.close()


def bounded_exchange(provider, api, directory, model=None, *, deadline=30):
    args = [sys.executable, str(Path(__file__).resolve()), '_request', provider, api, str(directory)]
    if model: args.append(model)
    try:
        done = subprocess.run(args, capture_output=True, timeout=deadline)
        return None if done.returncode == 0 else 'transport_or_format_error'
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for the child before the next request.
        return 'request_deadline_exceeded'
    except OSError:
        return 'local_process_start_error'


def probe(provider, api, root, model=None):
    directory=root/str(uuid.uuid4()); directory.mkdir()
    record = {'diagnostic_id': directory.name, 'provider': provider, 'model': model,
              'api': api, 'started_at': now(), 'model_request_started': model is not None,
              'http_status': None, 'error': None, 'headers': {}, 'body_present': False,
              'model_response_received': False, 'response_text': None, 'usage': None,
              'end_reason': 'started'}
    write_new(directory/'request.json',dict(record, host=PROVIDERS[provider][0],
        body=body_for(model,api) if model else None, deadline_seconds=30, retries=0,
        credential_source='windows-user-environment', session_id=directory.name if provider=='zen' else None))
    started=time.monotonic()
    failure=bounded_exchange(provider,api,directory,model)
    record.update(elapsed_seconds=round(time.monotonic()-started,3),finished_at=now())
    if (directory/'http.json').exists(): record.update(read(directory/'http.json'))
    data={}
    if (directory/'response.json').exists():
        original=read(directory/'response.json'); record['body_present']=original['body_present']
        try: data=json.loads(original['body'])
        except (ValueError,TypeError): failure=failure or 'response_format_error'
        if not isinstance(data,dict): data={}; failure=failure or 'response_format_error'
        if record['http_status'] != 200:
            _,record['error']=response_metadata({},original['body'].encode(),'never-a-credential-placeholder')
    if failure: record['end_reason']=failure
    elif record['http_status']==429: record['end_reason']='rate_limited'
    elif record['http_status']!=200: record['end_reason']='http_rejected'
    elif api=='models': record['end_reason']='model_list_received'
    else:
        try: record.update(interpret(data, model, api))
        except (ValueError,TypeError,AttributeError,KeyError): record['end_reason']='response_format_error'
    write_new(directory/'result.json',record)
    return record,data


def interpret(data, model, api):
    if api=='responses':
        texts=[p.get('text','') for item in (data.get('output') or []) if isinstance(item,dict)
               for p in (item.get('content') or []) if isinstance(p,dict) and p.get('type')=='output_text']
        limited=(data.get('incomplete_details') or {}).get('reason')=='max_output_tokens'
        finish=data.get('status')
        names=('input_tokens','output_tokens','total_tokens')
    else:
        choices=data.get('choices') or []
        texts=[(c.get('message') or {}).get('content','') for c in choices]
        limited=any(c.get('finish_reason')=='length' for c in choices)
        finish=[c.get('finish_reason') for c in choices]
        names=('prompt_tokens','completion_tokens','total_tokens')
    text='\n'.join(t for t in texts if isinstance(t,str) and t.strip())
    usage=data.get('usage')
    valid=isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in names)
    valid=valid and usage[names[0]]+usage[names[1]]==usage[names[2]]
    reason=('output_limit_reached' if limited else 'response_model_mismatch' if data.get('model')!=model
            else 'response_text_missing' if not text else 'usage_missing_or_invalid' if not valid
            else 'response_received')
    return dict(model_response_received=bool(text),response_text=text or None,usage=usage,
                usage_valid=bool(valid),response_model=data.get('model'),finish_reason=finish,end_reason=reason)


def provider_run(provider, root, openai_free_confirmed=False):
    listing,data=probe(provider,'models',root)
    listed={i.get('id') for i in data.get('data',[]) if isinstance(i,dict)} if isinstance(data.get('data',[]),list) else set()
    rows=[]
    for model,api in MATRIX[provider]:
        reason=('model_list_check_failed' if listing['http_status']!=200 or model not in listed
                else 'openai_free_application_unconfirmed' if provider=='openai' and not openai_free_confirmed else None)
        if reason:
            row=dict(diagnostic_id=str(uuid.uuid4()),provider=provider,model=model,api=api,
                     started_at=None,http_status=None,error=None,headers={},body_present=False,
                     model_response_received=False,usage=None,end_reason=reason,model_request_started=False)
            write_new(root/(row['diagnostic_id']+'.json'),row)
        else: row,_=probe(provider,api,root,model)
        row['exact_model_listed']=model in listed
        row['model_list_diagnostic_id']=listing['diagnostic_id']
        rows.append(row)
    return rows


def run(root, free_evidence=None):
    root.mkdir(parents=True,exist_ok=False)
    evidence=read(free_evidence) if free_evidence else {}
    confirmed=all(evidence.get(k) is True for k in
                  ('key_organization_verified','model_eligible','quota_remaining_verified'))
    write_new(root/'manifest.json',dict(kind='management-provider-diagnostic',comparison=False,
        created_at=now(),matrix=MATRIX,max_inference_requests=5,deadline_seconds=30,
        max_output_tokens=256,retries=0,parallelism='providers-only',openai_free_evidence=evidence))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(provider_run,p,root,confirmed) for p in PROVIDERS]
        rows=[r for f in futures for r in f.result()]
    write_new(root/'results.json',rows)
    return rows


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='_request':
        try: exchange(sys.argv[2],sys.argv[3],Path(sys.argv[4]),sys.argv[5] if len(sys.argv)>5 else None)
        except Exception: raise SystemExit(1)  # Never emit exception text from credential/transport layers.
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--output',type=Path,required=True)
        parser.add_argument('--openai-free-evidence',type=Path)
        parser.add_argument('--execute-real-model',action='store_true')
        args=parser.parse_args()
        if not args.execute_real_model: parser.error('Explicit --execute-real-model required')
        print(json.dumps(run(args.output,args.openai_free_evidence)))
