#!/usr/bin/env python3
"""Prepare/review one-case RUSH benchmarks, then explicitly publish/start/collect.

prepare is offline, uses stdlib only, and never loads app credentials. Live commands
use the installed official NanoAgent connection helpers, for this member only.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import time
import uuid

SCHEMA = 1
PUBLIC_FILES = {'input.json', 'prompt.txt'}
NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,127}')
CUSTOM = re.compile(r'rush ((?!(?:forget|help)(?: |$))[a-z0-9][a-z0-9._-]{0,63})((?: [A-Za-z0-9._=:/,@+%-]+){0,32})')
BUILTINS = {'claude', 'codex', 'dsh', 'hermes', 'nanoagent', 'pi'}
LIMITS = {'wall_time_ms', 'max_model_calls', 'max_output_tokens_per_call', 'max_cost_usd',
          'cpus', 'memory_mb', 'pids', 'workspace_bytes', 'workspace_files', 'tmp_bytes',
          'build_wall_ms', 'build_memory_mb', 'build_output_bytes', 'build_files',
          'build_tmp_bytes', 'internet_access'}
REQUIRED_LIMITS = {'wall_time_ms', 'max_model_calls', 'max_output_tokens_per_call', 'max_cost_usd', 'internet_access'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError('Duplicate JSON key')
            result[k] = v
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + '.tmp')
    part.write_bytes(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n')
    part.replace(path)


def preserve(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != raw:
        raise ValueError(f'Refusing to overwrite evidence: {path.name}')
    if not path.exists():
        with path.open('xb') as f:
            f.write(raw)
    return {'path': str(path), 'sha256': digest(raw), 'bytes': len(raw)}


def child(base, relative):
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(p in {'.', '..'} for p in parts) or '\\' in relative:
        raise ValueError('Expected a contained relative path')
    path = base
    if base.is_symlink():
        raise ValueError('Symlink fixture root')
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Symlinks are not fixture inputs')
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('Path escaped fixture root')
    return path


def check_limits(limits):
    if not isinstance(limits, dict) or set(limits) - LIMITS or not REQUIRED_LIMITS <= limits.keys():
        raise ValueError('Explicit wall/call/output/cost limits required; unknown limit field')
    if limits.get('internet_access') is not False:
        raise ValueError('Controlled cases require internet_access=false; public upstream sources contain private answers')
    for key, value in limits.items():
        if key == 'internet_access':
            if type(value) is not bool:
                raise ValueError('internet_access must be boolean')
            continue
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Limit must be finite numeric')
        if value < 0 or (key not in {'max_cost_usd', 'max_model_calls'} and value <= 0):
            raise ValueError('Invalid nonpositive limit')
        if key not in {'cpus', 'max_cost_usd'} and type(value) is not int:
            raise ValueError('Integer limit required')
        if key == 'max_model_calls' and value > 10000:
            raise ValueError('max_model_calls exceeds server cap')


def prepare(manifest_path, case_id, namespace, limits):
    if not NAME.fullmatch(namespace) or not namespace.startswith('comp580-'):
        raise ValueError('Namespace must begin comp580- and fit benchmark name characters')
    check_limits(limits)
    manifest_path = Path(manifest_path).resolve()
    manifest = load(manifest_path)
    entries = [c for c in manifest['cases'] if c['id'] == case_id]
    if len(entries) != 1:
        raise ValueError('Expected one exact manifest case id')
    entry = entries[0]
    if set(entry['files']) != PUBLIC_FILES:
        raise ValueError('Only input.json and prompt.txt are approved public fixture files')
    base = child(manifest_path.parent, entry['directory'])
    if not base.is_dir() or {p.name for p in base.iterdir()} != PUBLIC_FILES:
        raise ValueError('Public case directory must contain exactly input.json and prompt.txt')
    raw = {}
    for name in sorted(PUBLIC_FILES):
        path = child(base, name)
        if not path.is_file():
            raise ValueError('Fixture must be a regular file')
        raw[name] = path.read_bytes()
        declared = entry['files'][name]
        if digest(raw[name]) != declared['sha256'] or len(raw[name]) != declared['bytes']:
            raise ValueError(f'Fixture hash/size mismatch: {name}')
    if sum(map(len, raw.values())) > 8 << 20:
        raise ValueError('Public input exceeds conservative 8 MiB upload bound')
    prompt = raw['prompt.txt'].decode('utf-8')
    if not prompt or prompt != prompt.strip():
        raise ValueError('Exact prompt must be nonempty with no surrounding whitespace; do not silently strip')
    case = entry['case']
    if not isinstance(case, str) or not re.search(r'(?<![\w./])' + re.escape(case) + r'(?!\w|[./]\w)', ' '.join(prompt.split())):
        raise ValueError('Case argument must appear as its own token in exact prompt')
    # JSON is a YAML subset: preserve exact string bytes on parse without a YAML dependency.
    case_document = {'plugin': entry['plugin_id'], 'task': entry['task'],
                     'cases': [{'prompt': prompt, 'arguments': {'case': case}, 'fixtures': 'public'}], 'refuse': []}
    body = {'plugin_id': entry['plugin_id'], 'case_file': json.dumps(case_document, ensure_ascii=False, indent=2),
            'files': {f'public/{name}': base64.b64encode(data).decode('ascii') for name, data in raw.items()},
            'limits': limits}
    suffix = digest(canonical(body))[:16]
    name = f'{namespace}-{entry["plugin_id"]}-{case}-{suffix}'
    if not NAME.fullmatch(name):
        raise ValueError('Generated benchmark name too long or invalid')
    body['name'] = name
    return {'schema_version': SCHEMA, 'kind': 'comp580-one-case-publish-plan', 'namespace': namespace,
            'source_manifest': str(manifest_path), 'source_manifest_sha256': digest(manifest_path.read_bytes()),
            'case_id': case_id, 'expected_plugin_version': entry['source']['version'],
            'prompt_sha256': digest(raw['prompt.txt']), 'public_file_sha256': {n: digest(v) for n, v in raw.items()},
            'payload_sha256': digest(canonical(body)), 'payload': body,
            'boundary': 'Only public/input.json and public/prompt.txt are uploaded. Source/checkers/references/manifest stay host-side.'}


def verify_plan(plan):
    if plan.get('schema_version') != SCHEMA or plan.get('kind') != 'comp580-one-case-publish-plan':
        raise ValueError('Wrong plan schema')
    payload = plan['payload']
    if set(payload) != {'plugin_id', 'name', 'case_file', 'files', 'limits'}:
        raise ValueError('Unexpected publication field')
    if digest(canonical(payload)) != plan['payload_sha256']:
        raise ValueError('Plan payload hash mismatch')
    check_limits(payload['limits'])
    if set(plan['public_file_sha256']) != PUBLIC_FILES:
        raise ValueError('Unexpected public fixture hash entry')
    if set(payload['files']) != {'public/' + n for n in PUBLIC_FILES}:
        raise ValueError('Unexpected upload filename')
    if not NAME.fullmatch(payload['name']) or not payload['name'].startswith('comp580-'):
        raise ValueError('Benchmark name outside comp580 namespace')
    doc = json.loads(payload['case_file'])
    if set(doc) != {'plugin', 'task', 'cases', 'refuse'} or len(doc['cases']) != 1 or doc['refuse']:
        raise ValueError('Expected one answer case, no refusals')
    case = doc['cases'][0]
    if set(case) != {'prompt', 'arguments', 'fixtures'} or case['fixtures'] != 'public' or set(case['arguments']) != {'case'}:
        raise ValueError('Unexpected case contract')
    if doc['plugin'] != payload['plugin_id'] or plan['case_id'] != f'{doc["plugin"]}/{case["arguments"]["case"]}':
        raise ValueError('Case/plugin identity mismatch')
    if not case['prompt'] or case['prompt'] != case['prompt'].strip():
        raise ValueError('Prompt must preserve exact nonempty trimmed content')
    uploaded_size = 0
    for name in PUBLIC_FILES:
        raw = base64.b64decode(payload['files']['public/' + name], validate=True)
        uploaded_size += len(raw)
        if digest(raw) != plan['public_file_sha256'][name]:
            raise ValueError('Embedded public fixture hash mismatch')
        if name == 'prompt.txt' and (raw != case['prompt'].encode() or digest(raw) != plan['prompt_sha256']):
            raise ValueError('Prompt is not byte-identical')
    if uploaded_size > 8 << 20:
        raise ValueError('Public input exceeds conservative 8 MiB bound')
    return doc


def check_harness(harness):
    if harness not in BUILTINS and not (len(harness) <= 512 and CUSTOM.fullmatch(harness)):
        raise ValueError('Unsupported harness: use installed CLI as rush <program> [safe args]')


def run_request(plan, benchmark_id, harness, replicate):
    check_harness(harness)
    uuid.UUID(benchmark_id)
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', replicate):
        raise ValueError('Replicate label must be explicit and stable')
    key = 'comp580-' + digest(canonical({'plan': plan['payload_sha256'], 'benchmark': benchmark_id,
                                       'harness': harness, 'replicate': replicate}))
    return {'benchmark_id': benchmark_id, 'harness': harness, 'idempotency_key': key}


def save_state(path, state):
    save(path, state)


def open_state(path, plan):
    state = load(path) if Path(path).exists() else {'schema_version': SCHEMA, 'plan_sha256': plan['payload_sha256'], 'runs': {}}
    if state['plan_sha256'] != plan['payload_sha256']:
        raise ValueError('State belongs to a different plan')
    return state


@contextmanager
def locked(path):
    lock = Path(str(path) + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('State is locked; ensure no helper is running before removing a stale lock') from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


class Live:
    """Only this adapter imports app authentication. Never serialize headers/tokens."""
    def __init__(self, lab=None):
        import httpx
        from nanoagent.cli.harness import app_data, connection, find_lab, find_plugin
        _, site, token = connection(Path(lab) if lab else find_lab(app_data()))
        self.client = httpx.Client(base_url=site, headers={'Authorization': 'Bearer ' + token, 'Origin': site},
                                   timeout=60.0, follow_redirects=False)
        self.find_plugin = find_plugin
        self.httpx = httpx

    def discover(self, plugin, workspace):
        return self.find_plugin(self.client, plugin, workspace)

    def download(self, path, params=None):
        try:
            response = self.client.get(path, params=params)
        except Exception:
            raise RuntimeError(f'GET {path}: transport failed; request headers and body omitted') from None
        if not response.is_success:
            raise RuntimeError(f'GET {path}: HTTP {response.status_code}; no response body logged')
        return response.content, {name: response.headers.get(name) for name in ('content-type', 'x-rush-redaction', 'content-length')}

    def get_bytes(self, path, params=None):
        return self.download(path, params)[0]

    def json(self, method, path, body=None, params=None):
        try:
            timeout = self.httpx.Timeout(60.0, read=960.0) if method == 'POST' and path.endswith('/benchmark/benchmarks/pinned') else 60.0
            response = self.client.request(method, path, json=body, params=params, timeout=timeout)
        except Exception:
            raise RuntimeError(f'{method} {path}: transport failed; request headers and body omitted') from None
        if not response.is_success:
            raise RuntimeError(f'{method} {path}: HTTP {response.status_code}; no response body logged')
        return response.json()

    def close(self):
        self.client.close()


def check_benchmark(plan, benchmark):
    doc = verify_plan(plan)
    if benchmark['name'] != plan['payload']['name'] or benchmark['plugin']['id'] != doc['plugin']:
        raise ValueError('Published benchmark identity mismatch')
    if benchmark['plugin']['version'] != plan['expected_plugin_version'] or benchmark['task_id'] != doc['task']:
        raise ValueError('Published plugin version/task differs from reviewed plan')
    cases = benchmark['cases']
    if len(cases) != 1 or cases[0]['kind'] != 'answer' or cases[0]['prompt'] != doc['cases'][0]['prompt']:
        raise ValueError('Published case prompt/count mismatch')
    if cases[0]['arguments'] != doc['cases'][0]['arguments'] or cases[0]['prompt_sha256'] != plan['prompt_sha256']:
        raise ValueError('Published arguments/hash mismatch')
    if cases[0]['fixtures']['files'] != plan['public_file_sha256']:
        raise ValueError('Published fixture file hashes mismatch')
    for field, requested in plan['payload']['limits'].items():
        if benchmark['limits'][field] != requested:
            raise ValueError('Published limits differ from requested override')


def publish(api, plan, state, state_path, workspace):
    doc = verify_plan(plan)
    prefix, app = api.discover(doc['plugin'], workspace)
    if app.get('version') != plan['expected_plugin_version']:
        raise ValueError('Installed app version not verified against plan')
    if state.get('prefix') not in (None, prefix):
        raise ValueError('Workspace changed from saved state')
    state['prefix'] = prefix
    state['publication_request'] = {'payload_sha256': plan['payload_sha256'], 'name': plan['payload']['name']}
    save_state(state_path, state)  # durable intent before mutation; deterministic name handles replay
    if 'benchmark' not in state:
        response = api.json('POST', prefix + '/benchmark/benchmarks/pinned', plan['payload'])
        state['publication_response'] = response
        state['benchmark'] = response['benchmark']
        save_state(state_path, state)
    detail = api.json('GET', prefix + '/benchmark/benchmarks/' + state['benchmark']['benchmark_id'])['benchmark']
    check_benchmark(plan, detail)
    state['benchmark'] = detail
    state['publication_verified'] = True
    save_state(state_path, state)
    return {'benchmark_id': detail['benchmark_id'], 'name': detail['name'], 'verified': True}


def start(api, plan, state, state_path, harness, replicate):
    if not state.get('publication_verified'):
        raise ValueError('Publish/verify this reviewed plan first')
    check_benchmark(plan, state['benchmark'])
    request = run_request(plan, state['benchmark']['benchmark_id'], harness, replicate)
    key = request['idempotency_key']
    record = state['runs'].setdefault(key, {'request': request, 'replicate': replicate})
    if record['request'] != request:
        raise ValueError('Idempotency intent changed')
    save_state(state_path, state)  # durable key before network; resume repeats the identical POST
    if 'run_id' not in record:
        response = api.json('POST', state['prefix'] + '/benchmark/runs', request)
        record['start_response'] = response
        record['run_id'] = response['run']['run_id']
        save_state(state_path, state)
    return {'run_id': record['run_id'], 'idempotency_key': key, 'replicate': replicate}


def all_attempts(run):
    return [a for c in run['cases'] for a in c['attempts']]


def complete(run):
    attempts = all_attempts(run)
    return run['status'] in {'complete', 'canceled'} and bool(attempts) and all(a['sealed'] for a in attempts)


def fetch_events(api, path):
    events, pages, cursor = [], [], 0
    while True:
        page = api.json('GET', path + '/events', params={'after': cursor, 'limit': 1000})
        pages.append(page)
        incoming = page['events']
        if any(type(e['cursor']) is not int or e['cursor'] <= cursor for e in incoming):
            raise ValueError('Nonmonotonic event cursor')
        if any(a['cursor'] >= b['cursor'] for a, b in zip(incoming, incoming[1:])):
            raise ValueError('Duplicate/out-of-order event cursor')
        events.extend(incoming)
        if incoming:
            cursor = incoming[-1]['cursor']
        if not page['has_more']:
            return events, pages
        if not incoming:
            raise ValueError('Pagination did not advance')


def workspace_answer(archive):
    import zstandard
    matches = []
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(archive)) as stream:
        with tarfile.open(fileobj=stream, mode='r|') as tar:
            for member in tar:
                if member.name in {'answer.json', './answer.json'}:
                    if not member.isfile() or member.size > (1 << 20):
                        raise ValueError('Workspace answer is not a bounded regular file')
                    matches.append(tar.extractfile(member).read())
    if len(matches) > 1:
        raise ValueError('Duplicate workspace answer')
    return matches[0] if matches else None


def capture(api, state, record, run, out):
    out = Path(out) / run['run_id'] / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    files, problems = [], []
    def keep(name, value, raw=False):
        data = value if raw else canonical(value) + b'\n'
        files.append(preserve(out / name, data))
    keep('run.json', run)
    # Exact native export bytes preserved; filter to this run locally. No member= parameter.
    raw = api.get_bytes('/api/traces/export', {'plugin': run['case_set']['plugin']['id'], 'since': run['created_at']})
    keep('native-export.jsonl', raw, True)
    rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    selected = [r for r in rows if r.get('type') == 'run' and r.get('run_id') == run['run_id']]
    if len(selected) != 1:
        raise ValueError('Native export did not contain exactly one selected run')
    exported = selected[0]
    keep('selected-run.json', exported)
    exported_attempts = {a['attempt_id']: a for a in exported['attempts']}
    if set(exported_attempts) != {a['attempt_id'] for a in all_attempts(run)}:
        raise ValueError('Native export omitted/added attempts')
    for listed in all_attempts(run):
        aid = str(uuid.UUID(listed['attempt_id']))
        path = state['prefix'] + '/benchmark/attempts/' + aid
        folder = 'attempts/' + aid + '/'
        attempt = api.json('GET', path)['attempt']
        keep(folder + 'attempt.json', attempt)
        if attempt['attempt_id'] != aid:
            raise ValueError('Attempt identity mismatch')
        if not attempt['sealed']:
            raise ValueError('Attempt still in flight')
        events, pages = fetch_events(api, path)
        keep(folder + 'event-pages.json', pages)
        keep(folder + 'events.jsonl', b''.join(canonical(e) + b'\n' for e in events), True)
        high = events[-1]['cursor'] if events else 0
        if high != attempt['final_cursor']:
            problems.append({'attempt': aid, 'issue': 'event_final_cursor_mismatch', 'last': high, 'expected': attempt['final_cursor']})
        keep(folder + 'accounting.json', api.json('GET', path + '/accounting'))
        spans = api.json('GET', path + '/spans', params={'limit': 5000})
        keep(folder + 'spans.json', spans)
        if spans.get('truncated'):
            problems.append({'attempt': aid, 'issue': 'spans_truncated', 'detail': spans.get('truncated')})
        keep(folder + 'recording.json', api.json('GET', path + '/recording'))
        for payload_hash in sorted({h for e in events for h in e.get('payload_sha256s', [])}):
            if not re.fullmatch('[0-9a-f]{64}', payload_hash):
                raise ValueError('Malformed payload hash')
            payload, download_metadata = api.download(path + '/payloads/' + payload_hash)
            if digest(payload) != payload_hash:
                raise ValueError('Payload content hash mismatch')
            keep(folder + 'payloads/' + payload_hash, payload, True)
            keep(folder + 'payloads/' + payload_hash + '.metadata.json', download_metadata)
        answers = [e['data']['outcome'].get('answer') for e in events if e['kind'] == 'result.read' and isinstance(e.get('data', {}).get('outcome'), dict)]
        keep(folder + 'answer-from-events.json', {'present': bool(answers), 'answer': answers[-1] if answers else None})
        workspace = exported_attempts[aid].get('workspace')
        if workspace and not workspace.get('error'):
            expected_path = '/api/traces/workspaces/' + aid
            if workspace.get('url') != expected_path:
                raise ValueError('Unexpected workspace download route')
            archive, download_metadata = api.download(expected_path)
            if len(archive) != workspace['bytes'] or digest(archive) != workspace['sha256']:
                raise ValueError('Workspace archive hash/size mismatch')
            keep(folder + 'workspace.tar.zst', archive, True)
            keep(folder + 'workspace-download.json', download_metadata)
            answer = workspace_answer(archive)
            if answer is not None:
                keep(folder + 'workspace-answer.json', answer, True)
            else:
                problems.append({'attempt': aid, 'issue': 'workspace_answer_missing'})
        else:
            problems.append({'attempt': aid, 'issue': 'workspace_unavailable', 'detail': workspace})
    index = {'run_id': run['run_id'], 'captured_at': now(), 'files': files, 'capture_issues': problems,
             'scope': 'Own run and every attempt, including worker retries. Native export may also contain other own records in the time window. No other-member scope requested.',
             'logical_trial_count': 1, 'actual_attempt_count': len(all_attempts(run)),
             'metrics_note': 'Retain raw usage completeness, coverage, settlement and verifier errors. Do not infer zeros or provider charges.'}
    save(out / 'capture.json', index)
    record.setdefault('captures', []).append(str(out / 'capture.json'))
    return {'run_id': run['run_id'], 'capture': str(out / 'capture.json'), 'issues': len(problems)}


def check_run(state, record, run):
    """The server's concrete pinned configuration must still match the reviewed publication."""
    bench = state['benchmark']
    if run['harness']['name'] != record['request']['harness']:
        raise ValueError('Run harness differs from submitted command')
    for field in ('model', 'endpoint_profile', 'providers', 'limits'):
        if run[field] != bench[field]:
            raise ValueError('Run pinned configuration differs from benchmark: ' + field)
    case_set = run['case_set']
    if case_set['plugin'] != bench['plugin'] or case_set['task_id'] != bench['task_id']:
        raise ValueError('Run plugin/task differs from benchmark')
    if len(run['cases']) != len(bench['cases']):
        raise ValueError('Run case count differs from benchmark')
    for got, expected in zip(run['cases'], bench['cases']):
        for field in ('case_id', 'kind', 'prompt', 'prompt_sha256', 'arguments', 'fixtures'):
            if got[field] != expected[field]:
                raise ValueError('Run public case differs from benchmark: ' + field)


def collect(api, state, state_path, run_id, out, wait_seconds):
    matches = [r for r in state['runs'].values() if r.get('run_id') == run_id]
    if len(matches) != 1:
        raise ValueError('Only a run created in this state may be collected')
    record = matches[0]
    deadline = time.monotonic() + wait_seconds
    while True:
        run = api.json('GET', state['prefix'] + '/benchmark/runs/' + str(uuid.UUID(run_id)))['run']
        if run['run_id'] != run_id or run['benchmark']['benchmark_id'] != record['request']['benchmark_id']:
            raise ValueError('Run identity mismatch')
        check_run(state, record, run)
        record['last_observation'] = {'at': now(), 'status': run['status'], 'attempts': all_attempts(run)}
        save_state(state_path, state)
        if complete(run):
            result = capture(api, state, record, run, out)
            save_state(state_path, state)
            return result
        if time.monotonic() >= deadline:
            return {'run_id': run_id, 'status': run['status'], 'pending': True}
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare', help='OFFLINE: create concrete reviewable publication payload')
    p.add_argument('--fixtures', type=Path, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--limits', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    for verb in ('publish', 'start', 'collect'):
        p = commands.add_parser(verb)
        p.add_argument('--plan', type=Path, required=True)
        p.add_argument('--state', type=Path, required=True)
        p.add_argument('--lab', type=Path)
        if verb == 'publish':
            p.add_argument('--workspace', default='comp-480-580')
        if verb == 'start':
            p.add_argument('--harness', required=True)
            p.add_argument('--replicate', required=True)
        if verb == 'collect':
            p.add_argument('--run-id', required=True)
            p.add_argument('--out', type=Path, required=True)
            p.add_argument('--wait-seconds', type=float, default=0)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        plan = prepare(args.fixtures, args.case, args.namespace, load(args.limits))
        verify_plan(plan)
        preserve(args.out, json.dumps(plan, indent=2, ensure_ascii=False).encode() + b'\n')
        print(json.dumps({'offline': True, 'plan': str(args.out), 'benchmark_name': plan['payload']['name'], 'payload_sha256': plan['payload_sha256']}))
        return 0
    if args.command == 'collect' and not 0 <= args.wait_seconds <= 60:
        parser.error('--wait-seconds must be between 0 and 60')
    plan = load(args.plan)
    verify_plan(plan)
    with locked(args.state):
        state = open_state(args.state, plan)
        api = Live(args.lab)
        try:
            if args.command == 'publish':
                result = publish(api, plan, state, args.state, args.workspace)
            elif args.command == 'start':
                result = start(api, plan, state, args.state, args.harness, args.replicate)
            else:
                result = collect(api, state, args.state, args.run_id, args.out, args.wait_seconds)
        finally:
            api.close()
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        raise SystemExit(f'rush_benchmark: {type(exc).__name__}: {exc}') from None
