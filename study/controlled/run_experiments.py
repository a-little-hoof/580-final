#!/usr/bin/env python3
"""Freeze 50 paired trials offline; execute at most one start/poll/capture per step.

No network access occurs in freeze/status. step is explicit and requires the
installed official client. Failed logical trials are retained, never replaced.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rush_benchmark as rb

ALGORITHM = 'sha256-sort-pairs-v1'
CONDITIONS = ('full', 'compact')
DEFAULT_INPUTS = ['src', 'pyproject.toml', 'build-requirements.txt',
                  'study/controlled/fixtures', 'study/controlled/validators',
                  'study/controlled/limits.json', 'study/controlled/rush_benchmark.py',
                  'study/controlled/run_experiments.py',
                  'study/controlled/development/platform-fix/scalar-enum-skeleton.patch',
                  'study/controlled/development/platform-fix/applied.json']


def source_tree(root, inputs):
    """Explicit research inputs only; hash private validators but never upload them."""
    root = Path(root).resolve()
    found = {}
    for item in inputs:
        path = rb.child(root, item)
        paths = sorted(path.rglob('*')) if path.is_dir() else [path]
        for p in paths:
            if '__pycache__' in p.parts or p.suffix in {'.pyc', '.pyo'}:
                continue
            if p.is_symlink():
                raise ValueError('Frozen tree contains a symlink')
            if p.is_dir():
                continue
            if not p.is_file():
                raise ValueError('Frozen input missing or not regular')
            found[p.relative_to(root).as_posix()] = rb.digest(p.read_bytes())
    if not found:
        raise ValueError('No source inputs')
    return {'inputs': inputs, 'files': found, 'sha256': rb.digest(rb.canonical(found))}


def wheel_identity(path):
    path = Path(path).resolve()
    modules = {}
    with zipfile.ZipFile(path) as wheel:
        for entry in wheel.infolist():
            if entry.filename.startswith('comp580_agent/') and entry.filename.endswith('.py'):
                relative = entry.filename[len('comp580_agent/'):]
                if not relative or '..' in PurePosixPath(relative).parts or relative in modules:
                    raise ValueError('Ambiguous wheel module path')
                if entry.file_size > 1 << 20:
                    raise ValueError('Wheel module exceeds bound')
                modules[relative] = rb.digest(wheel.read(entry))
    if not {'__init__.py', 'cli.py', 'agent.py'} <= modules.keys():
        raise ValueError('Wheel lacks original agent modules')
    return {'path': str(path), 'sha256': rb.digest(path.read_bytes()),
            'package_modules_sha256': modules, 'code_sha256': rb.digest(rb.canonical(modules))}


def source_modules(root):
    package = Path(root) / 'src/comp580_agent'
    return {p.relative_to(package).as_posix(): rb.digest(p.read_bytes()) for p in sorted(package.rglob('*.py')) if p.is_file()}


def schedule_rows(cases, seed, code_sha256):
    if len(cases) != 5 or len({c['case_id'] for c in cases}) != 5:
        raise ValueError('Exactly five distinct public cases required')
    pairs = [(case, rep) for case in cases for rep in range(1, 6)]
    def order_key(pair):
        case, rep = pair
        return rb.digest(rb.canonical([ALGORITHM, seed, 'pair', case['case_id'], rep]))
    rows = []
    for case, rep in sorted(pairs, key=order_key):
        order = list(CONDITIONS)
        if int(rb.digest(rb.canonical([ALGORITHM, seed, 'condition', case['case_id'], rep]))[-1], 16) % 2:
            order.reverse()
        for condition in order:
            command = f'rush comp580-agent --condition {condition} --code-sha256 {code_sha256}'
            replicate = f'final-rep{rep:02d}'
            request = rb.run_request({'payload_sha256': case['plan_sha256']}, case['benchmark_id'], command, replicate)
            rows.append({'position': len(rows) + 1, 'trial_id': f'{case["case_id"]}/{condition}/rep{rep:02d}',
                         'case_id': case['case_id'], 'condition': condition, 'replicate': replicate,
                         'benchmark_id': case['benchmark_id'], 'request': request})
    return rows


def freeze(root, plan_state_pairs, wheel_path, seed, excluded_run_ids, inputs=None):
    root = Path(root).resolve()
    if type(seed) is not int:
        raise ValueError('Seed must be an integer')
    if len(plan_state_pairs) != 5:
        raise ValueError('Exactly five plan/state pairs required')
    cases, common = [], None
    for plan_path, state_path in plan_state_pairs:
        plan_path, state_path = Path(plan_path).resolve(), Path(state_path).resolve()
        plan, state = rb.load(plan_path), rb.load(state_path)
        rb.verify_plan(plan)
        if state['plan_sha256'] != plan['payload_sha256'] or not state.get('publication_verified'):
            raise ValueError('All publications must be verified before freezing')
        bench = state['benchmark']; rb.check_benchmark(plan, bench)
        config = {f: bench[f] for f in ('model', 'endpoint_profile', 'providers', 'limits')}
        if common is not None and config != common:
            raise ValueError('Five publications do not share exactly the same pinned configuration')
        common = config
        cases.append({'case_id': plan['case_id'], 'plan_path': str(plan_path), 'state_path': str(state_path),
                      'plan_file_sha256': rb.digest(plan_path.read_bytes()), 'plan_sha256': plan['payload_sha256'],
                      'prompt_sha256': plan['prompt_sha256'], 'public_file_sha256': plan['public_file_sha256'],
                      'benchmark_id': bench['benchmark_id'], 'benchmark': bench, 'prefix': state['prefix']})
    if len({c['benchmark_id'] for c in cases}) != 5:
        raise ValueError('Each case must have its own benchmark ID')
    wheel = wheel_identity(wheel_path)
    if wheel['package_modules_sha256'] != source_modules(root):
        raise ValueError('Wheel modules differ from current source tree')
    tree = source_tree(root, inputs or DEFAULT_INPUTS)
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    revision = result.stdout.strip() if result.returncode == 0 else None
    rows = schedule_rows(cases, seed, wheel['code_sha256'])
    prior_ids = {r.get('run_id') for _, state_path in plan_state_pairs for r in rb.load(state_path)['runs'].values() if r.get('run_id')}
    if not prior_ids <= set(excluded_run_ids):
        raise ValueError('Every existing smoke/development run must be explicitly excluded')
    frozen = {'schema_version': 1, 'kind': 'comp580-frozen-experiment', 'created_at': rb.now(),
              'project_root': str(root), 'seed': seed, 'randomization': ALGORITHM,
              'logical_trial_count': 50, 'paired_blocks': 25, 'conditions': list(CONDITIONS),
              'source_revision': revision, 'source_tree': tree, 'wheel': wheel, 'configuration': common,
              'source_identity_note': 'Revision may be absent/dirty; tree digest and wheel/module hashes are authoritative. Native agent is command text; attempt.started source_sha256 identifies platform shell, not this package.',
              'excluded_run_ids': sorted(set(excluded_run_ids)), 'cases': cases, 'trials': rows}
    frozen['freeze_sha256'] = rb.digest(rb.canonical(frozen))
    return frozen


def verify_freeze(frozen):
    content = {k: v for k, v in frozen.items() if k != 'freeze_sha256'}
    if frozen.get('kind') != 'comp580-frozen-experiment' or rb.digest(rb.canonical(content)) != frozen['freeze_sha256']:
        raise ValueError('Frozen schedule hash mismatch')
    if frozen['randomization'] != ALGORITHM or frozen['trials'] != schedule_rows(frozen['cases'], frozen['seed'], frozen['wheel']['code_sha256']):
        raise ValueError('Frozen randomization/order mismatch')
    if len(frozen['trials']) != 50 or len({r['request']['idempotency_key'] for r in frozen['trials']}) != 50:
        raise ValueError('Expected fifty unique logical trials')
    if source_tree(frozen['project_root'], frozen['source_tree']['inputs']) != frozen['source_tree']:
        raise ValueError('Frozen source/fixture/validator tree changed')
    if wheel_identity(frozen['wheel']['path']) != frozen['wheel']:
        raise ValueError('Frozen wheel changed')
    for case in frozen['cases']:
        plan = rb.load(case['plan_path'])
        if rb.digest(Path(case['plan_path']).read_bytes()) != case['plan_file_sha256'] or plan['payload_sha256'] != case['plan_sha256']:
            raise ValueError('Frozen plan changed')
        state = rb.load(case['state_path'])
        if state['benchmark'] != case['benchmark'] or state['prefix'] != case['prefix'] or not state.get('publication_verified'):
            raise ValueError('Publication state drift')
        rb.check_benchmark(plan, state['benchmark'])


def telemetry_from_archive(raw):
    """Read only bounded agent run metadata, never extract filesystem paths."""
    import zstandard
    found = {}
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as stream:
        with tarfile.open(fileobj=stream, mode='r|') as archive:
            for member in archive:
                name = member.name[2:] if member.name.startswith('./') else member.name
                parts = PurePosixPath(name).parts
                if len(parts) != 3 or parts[0] != '.comp580_logs' or parts[2] != 'run.json' or not re.fullmatch('[0-9a-f]{32}', parts[1]):
                    continue
                if name in found or not member.isfile() or member.size > 1 << 20:
                    raise ValueError('Ambiguous or unsafe agent telemetry')
                found[name] = json.loads(archive.extractfile(member).read())
    return found


def check_capture(frozen, trial, index_path):
    index_path = Path(index_path); folder = index_path.parent; index = rb.load(index_path)
    for file in index['files']:
        path = Path(file['path'])
        if not path.resolve().is_relative_to(folder.resolve()) or rb.digest(path.read_bytes()) != file['sha256'] or path.stat().st_size != file['bytes']:
            raise ValueError('Captured file hash/size/location mismatch')
    exported = rb.load(folder / 'selected-run.json')
    if exported.get('harness', {}).get('name') != trial['request']['harness']:
        raise ValueError('Exported harness command differs from frozen trial')
    evidence, issues = [], []
    for attempt in exported['attempts']:
        aid = attempt['attempt_id']; attempt_dir = folder / 'attempts' / aid
        actual = rb.load(attempt_dir / 'attempt.json')
        worker_error = (actual.get('execution') or {}).get('status') == 'worker_error'
        archive = attempt_dir / 'workspace.tar.zst'
        metadata = telemetry_from_archive(archive.read_bytes()) if archive.exists() else {}
        if len(metadata) != 1:
            if not worker_error:
                issues.append({'attempt_id': aid, 'issue': 'agent_identity_missing_or_ambiguous'})
        else:
            value = next(iter(metadata.values()))
            if (value.get('code_sha256') != frozen['wheel']['code_sha256'] or
                    value.get('package_modules_sha256') != frozen['wheel']['package_modules_sha256'] or
                    value.get('condition') != trial['condition']):
                issues.append({'attempt_id': aid, 'issue': 'agent_identity_or_condition_drift'})
        events = [json.loads(line) for line in (attempt_dir / 'events.jsonl').read_text().splitlines() if line]
        shell_sources = [e.get('data', {}).get('source_sha256') for e in events if e.get('kind') == 'attempt.started']
        evidence.append({'attempt_id': aid, 'attempt_no': attempt['attempt_no'],
                         'execution': actual.get('execution'), 'verdict': actual.get('verdict'),
                         'agent_metadata': metadata, 'agent_identity_available': len(metadata) == 1,
                         'platform_shell_source_sha256': shell_sources,
                         'native_agent_command': exported.get('agent'),
                         'custom_package_id': None, 'package_id_note': 'No custom package ID in native API; use guarded code/module hashes and host wheel hash.'})
    by_id = {a['attempt_id']: a for a in exported['attempts']}
    for issue in index['capture_issues']:
        status = (by_id[issue['attempt']].get('outcome') or {}).get('status')
        if issue['issue'] == 'workspace_unavailable' and status == 'worker_error':
            continue
        if issue['issue'] == 'workspace_answer_missing' and status not in {'answered'}:
            continue
        issues.append(issue)
    return {'run_id': exported['run_id'], 'logical_trials': 1, 'actual_attempts': len(evidence),
            'identity_and_capture_issues': issues, 'attempts': evidence}


def status(frozen, progress):
    completed = sum(v.get('phase') == 'captured' for v in progress.get('trials', {}).values())
    return {'frozen_logical_trials': 50, 'captured_logical_trials': completed,
            'actual_attempts': sum(v.get('actual_attempts', 0) for v in progress.get('trials', {}).values()),
            'remaining_logical_trials': 50 - completed}


def step(api, frozen, progress, progress_path, evidence, wait_seconds=0):
    verify_freeze(frozen)
    if progress.get('freeze_sha256') != frozen['freeze_sha256']:
        raise ValueError('Progress belongs to another freeze')
    trial = next((t for t in frozen['trials'] if progress['trials'].get(t['trial_id'], {}).get('phase') != 'captured'), None)
    if trial is None:
        return {**status(frozen, progress), 'complete': True}
    row = progress['trials'].setdefault(trial['trial_id'], {'phase': 'intent', 'request': trial['request']})
    if row.get('phase') == 'needs_review':
        return {'trial_id': trial['trial_id'], 'action': 'stopped', 'needs_review': True, 'check': row.get('check'), 'error': row.get('error')}
    if row['request'] != trial['request']:
        raise ValueError('Stored trial intent drift')
    case = next(c for c in frozen['cases'] if c['case_id'] == trial['case_id'])
    plan = rb.load(case['plan_path'])
    # One state protects publication and exact idempotency replay for both one-off helper and this runner.
    with rb.locked(case['state_path']):
        state = rb.open_state(case['state_path'], plan)
        if 'run_id' not in row:
            current = api.json('GET', state['prefix'] + '/benchmark/benchmarks/' + case['benchmark_id'])['benchmark']
            if current != case['benchmark']:
                raise ValueError('Live benchmark differs from frozen publication')
            rb.save(progress_path, progress)
            result = rb.start(api, plan, state, case['state_path'], trial['request']['harness'], trial['replicate'])
            if result['idempotency_key'] != trial['request']['idempotency_key'] or result['run_id'] in frozen['excluded_run_ids']:
                raise ValueError('Run identity collides with frozen/excluded trial')
            row.update(phase='started', run_id=result['run_id'])
            rb.save(progress_path, progress)
            return {'trial_id': trial['trial_id'], 'action': 'started', **result}
        result = rb.collect(api, state, case['state_path'], row['run_id'], evidence, wait_seconds)
    if result.get('pending'):
        row['phase'] = 'running'; rb.save(progress_path, progress)
        return {'trial_id': trial['trial_id'], 'action': 'poll', **result}
    row.setdefault('captures', []).append(result['capture'])
    # Persist captured failures even when provenance checking will stop subsequent trials.
    row['phase'] = 'checking'; rb.save(progress_path, progress)
    try:
        checked = check_capture(frozen, trial, result['capture'])
    except (ValueError, OSError, KeyError) as exc:
        row.update(phase='needs_review', error=f'Capture validation failed: {type(exc).__name__}')
        rb.save(progress_path, progress)
        raise
    check_path = Path(result['capture']).parent / 'trial-check.json'
    rb.preserve(check_path, rb.canonical(checked) + b'\n')
    row.update(phase='needs_review' if checked['identity_and_capture_issues'] else 'captured',
               actual_attempts=checked['actual_attempts'], check=str(check_path))
    rb.save(progress_path, progress)
    return {'trial_id': trial['trial_id'], 'action': 'captured', 'phase': row['phase'],
            'capture': result['capture'], 'issues': len(checked['identity_and_capture_issues'])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('freeze', help='OFFLINE: freeze all fifty trials after reviewed smoke/publications')
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--case', nargs=2, action='append', metavar=('PLAN', 'STATE'), required=True)
    p.add_argument('--wheel', type=Path, required=True); p.add_argument('--seed', type=int, default=580)
    p.add_argument('--exclude-run', action='append', default=[]); p.add_argument('--out', type=Path, required=True)
    for verb in ('status', 'step'):
        p = sub.add_parser(verb); p.add_argument('--freeze', type=Path, required=True)
        p.add_argument('--progress', type=Path, required=True)
        if verb == 'step':
            p.add_argument('--evidence', type=Path, required=True); p.add_argument('--lab', type=Path)
            p.add_argument('--wait-seconds', type=float, default=0)
    args = parser.parse_args(argv)
    if args.command == 'freeze':
        frozen = freeze(args.root, args.case, args.wheel, args.seed, args.exclude_run)
        rb.preserve(args.out, json.dumps(frozen, indent=2, ensure_ascii=False).encode() + b'\n')
        print(json.dumps({'offline': True, 'freeze': str(args.out), 'sha256': frozen['freeze_sha256'], 'logical_trials': 50}))
        return 0
    frozen = rb.load(args.freeze)
    if args.command == 'status':
        progress = rb.load(args.progress) if args.progress.exists() else {}
        if progress and progress.get('freeze_sha256') != frozen['freeze_sha256']:
            raise ValueError('Progress belongs to another freeze')
        print(json.dumps(status(frozen, progress))); return 0
    if not 0 <= args.wait_seconds <= 60:
        parser.error('--wait-seconds must be 0 through 60')
    with rb.locked(args.progress):
        verify_freeze(frozen)  # before credential adapter construction
        progress = rb.load(args.progress) if args.progress.exists() else {'freeze_sha256': frozen['freeze_sha256'], 'trials': {}}
        api = rb.Live(args.lab)
        try:
            result = step(api, frozen, progress, args.progress, args.evidence, args.wait_seconds)
        finally:
            api.close()
    print(json.dumps(result)); return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        raise SystemExit(f'run_experiments: {type(exc).__name__}: {exc}') from None
