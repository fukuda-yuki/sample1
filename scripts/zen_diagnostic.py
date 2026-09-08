"""Explicit, bounded management-only Zen diagnostic; never runs comparison work."""
import argparse
import http.client
import json
import os
import re
from pathlib import Path
import time
import uuid

MODEL = 'muse-spark-1.3-contributor-free'
HOST = 'opencode.ai'


def credential(name='OPENCODE_ZEN_API_KEY', *, windows_user_only=False):
    if name not in ('OPENCODE_ZEN_API_KEY', 'OPENAI_API_KEY'):
        raise ValueError('unsupported_credential')
    value = '' if windows_user_only else os.environ.get(name, '').strip()
    if value:
        return value, 'process-environment'
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as registry:
                value = winreg.QueryValueEx(registry, name)[0].strip()
            if value:
                return value, 'windows-user-environment'
        except FileNotFoundError:
            pass
    raise ValueError('credential_unavailable')


def classify_error(raw):
    # Persist a closed vocabulary, never arbitrary upstream strings or credentials.
    lower = raw.lower()
    if b'free tier can only be used in opencode' in lower:
        return 'free_tier_restricted_to_opencode'
    if b'insufficient' in lower or b'balance' in lower:
        return 'account_balance_or_quota'
    if b'unauthorized' in lower or b'invalid api key' in lower:
        return 'authentication_rejected'
    return 'upstream_rejected'


def sanitized(value, key, limit=1024):
    if not isinstance(value, (str, int, float)):
        return None
    text = str(value).replace(key, '[REDACTED]')
    text = re.sub(r'(?i)(incorrect api key provided:\s*)\S+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)bearer\s+[^\s"<>]+|\bsk-[\w-]+', '[REDACTED]', text)
    return ''.join(c for c in text if c.isprintable() or c == '\n')[:limit]


def response_metadata(headers, raw, key):
    allowed = ('retry-after', 'x-request-id', 'request-id', 'openai-request-id', 'cf-ray')
    saved = {k.lower(): sanitized(v, key, 256) for k, v in headers.items() if k.lower() in allowed}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        data = {}
    error = data.get('error', {}) if isinstance(data, dict) else {}
    if not isinstance(error, dict):
        error = {'message': error}
    fields = {name: sanitized(error[name], key) for name in ('code', 'type', 'message') if name in error}
    if not fields and raw:
        fields['message'] = sanitized(raw.decode('utf-8', errors='replace'), key)
    return saved, fields


def validate_response(data, key):
    texts = [part['text'] for item in data.get('output', []) if isinstance(item, dict)
             for part in item.get('content', []) if isinstance(part, dict)
             and part.get('type') == 'output_text' and isinstance(part.get('text'), str)
             and part['text'].strip()]
    usage = data.get('usage')
    names = ('input_tokens', 'output_tokens', 'total_tokens')
    valid_usage = (isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in names)
                   and usage['input_tokens'] + usage['output_tokens'] == usage['total_tokens'])
    failures = []
    if data.get('model') != MODEL:
        failures.append('response_model_mismatch')
    if not texts:
        failures.append('response_text_missing')
    if not valid_usage:
        failures.append('usage_missing' if not usage else 'usage_invalid')
    return {'response_model_matches': data.get('model') == MODEL,
            'model_response_received': bool(texts), 'response_text': sanitized('\n'.join(texts), key, 16384),
            'usage': {k: usage[k] for k in names} if valid_usage else None,
            'validation_errors': failures, 'status': failures[0] if failures else 'response_received'}


def request(key, method, path, body=None, session_id=None):
    connection = http.client.HTTPSConnection(HOST, timeout=30)
    try:
        headers = {
            'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json',
            'User-Agent': 'sample1-research-diagnostic/1',
        }
        if session_id:
            headers['x-opencode-session'] = str(uuid.UUID(session_id))
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        # No redirects, retries, alternate hosts, or provider fallback.
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('response_size_limit')
        return response.status, dict(response.getheaders()), raw
    finally:
        connection.close()


def run(root):
    key, source = credential()
    run_id = str(uuid.uuid4())
    directory = Path(root).resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'run_id': run_id, 'kind': 'diagnostic', 'comparison': False,
                'authorization': 'https://github.com/fukuda-yuki/sample1/issues/16',
                'authorization_date': '2026-09-08', 'model_id': MODEL,
                'credential_source': source, 'provider': 'opencode-zen',
                'limits': {'model_requests': 1, 'model_list_requests': 1,
                           'request_timeout_seconds': 30, 'max_output_tokens': 128},
                'client': 'management-http-diagnostic', 'session_header': True,
                'provider_session_id': run_id, 'native_session_id': None}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    result = {'run_id': run_id, 'status': 'started', 'usage': None,
              'model_requests_started': 0, 'model_response_received': False}
    def save():
        (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    save()
    started = time.monotonic()
    try:
        status, headers, raw = request(key, 'GET', '/zen/v1/models')
        result['models_http_status'] = status
        result['models_response_headers'], models_error = response_metadata(headers, raw if status != 200 else b'', key)
        if status != 200:
            result['models_error'] = models_error
        present = status == 200 and any(item.get('id') == MODEL for item in json.loads(raw).get('data', []))
        result['exact_model_listed'] = present
        if not present:
            result['status'] = 'model_list_check_failed'
            return directory
        result['model_requests_started'] = 1
        save()  # Record the sole request before sending it.
        body = json.dumps({'model': MODEL, 'input': 'Reply with the single word OK.',
                           'max_output_tokens': 128, 'store': False, 'stream': False})
        status, headers, raw = request(key, 'POST', '/zen/v1/responses', body, session_id=run_id)
        result['response_http_status'] = status
        result['rate_limited'] = status == 429
        result['response_headers'], error = response_metadata(headers, raw if status != 200 else b'', key)
        if status != 200:
            result['status'] = 'upstream_rejected'
            result['cause'] = classify_error(raw)
            result['error'] = error
        else:
            data = json.loads(raw)
            result.update(validate_response(data, key))
    except (OSError, ValueError, TypeError, AttributeError, http.client.HTTPException) as error:
        result['status'] = 'diagnostic_transport_or_format_error'
        result['error_type'] = type(error).__name__
    finally:
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        save()
    return directory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--execute-real-model', action='store_true')
    args = parser.parse_args()
    if not args.execute_real_model:
        parser.error('--execute-real-model is required; up to one authenticated model request')
    output = run(args.output)
    print(output)
    print((output / 'result.json').read_text())
    raise SystemExit(0 if json.loads((output / 'result.json').read_text())['status'] == 'response_received' else 1)
