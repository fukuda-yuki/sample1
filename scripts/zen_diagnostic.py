"""Explicit, bounded management-only Zen diagnostic; never runs comparison work."""
import argparse
import http.client
import json
import os
from pathlib import Path
import time
import uuid

MODEL = 'muse-spark-1.3-contributor-free'
HOST = 'opencode.ai'


def credential():
    value = os.environ.get('OPENCODE_ZEN_API_KEY', '').strip()
    if value:
        return value, 'process-environment'
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as registry:
                value = winreg.QueryValueEx(registry, 'OPENCODE_ZEN_API_KEY')[0].strip()
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
        return response.status, raw
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
        status, raw = request(key, 'GET', '/zen/v1/models')
        result['models_http_status'] = status
        present = status == 200 and any(item.get('id') == MODEL for item in json.loads(raw).get('data', []))
        result['exact_model_listed'] = present
        if not present:
            result['status'] = 'model_list_check_failed'
            return directory
        result['model_requests_started'] = 1
        save()  # Record the sole request before sending it.
        body = json.dumps({'model': MODEL, 'input': 'Reply with the single word OK.',
                           'max_output_tokens': 128, 'store': False, 'stream': False})
        status, raw = request(key, 'POST', '/zen/v1/responses', body, session_id=run_id)
        result['response_http_status'] = status
        result['rate_limited'] = status == 429
        if status != 200:
            result['status'] = 'rate_limited' if status == 429 else classify_error(raw)
        else:
            data = json.loads(raw)
            result['response_model_matches'] = data.get('model') == MODEL
            result['model_response_received'] = bool(data.get('output'))
            usage = data.get('usage') or {}
            result['usage'] = {name: usage[name] for name in ('input_tokens', 'output_tokens', 'total_tokens')
                               if isinstance(usage.get(name), int) and not isinstance(usage[name], bool)}
            result['status'] = 'response_received' if result['response_model_matches'] else 'response_model_mismatch'
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
