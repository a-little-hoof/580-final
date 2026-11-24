"""Offline boundary/resumption tests; never instantiate live app authentication."""
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / 'rush_benchmark.py'
spec = importlib.util.spec_from_file_location('rush_benchmark', FILE)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
BID = 'c0123456-1234-1234-1234-123456789abc'
RID = 'a0123456-1234-1234-1234-123456789abc'
AIDS = ['b0123456-1234-1234-1234-123456789abc', 'd0123456-1234-1234-1234-123456789abc']
LIMITS = {'wall_time_ms': 180000, 'max_model_calls': 12, 'max_output_tokens_per_call': 32768,
          'max_cost_usd': .05, 'internet_access': False}


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'plugin/case'
        self.folder.mkdir(parents=True)
        self.raw = {'input.json': b'{"visible": [1, 2]}\n', 'prompt.txt': 'Solve case for plugin. Café.'.encode()}
        for name, data in self.raw.items():
            (self.folder / name).write_bytes(data)
        self.entry = {'id': 'plugin/case', 'plugin_id': 'plugin', 'task': 'solve', 'case': 'case',
                      'directory': 'plugin/case', 'source': {'version': '0.1.0'},
                      'files': {n: {'sha256': r.digest(v), 'bytes': len(v)} for n, v in self.raw.items()}}
        self.manifest = self.root / 'manifest.json'
        r.save(self.manifest, {'schema_version': 1, 'cases': [self.entry]})
        self.plan = r.prepare(self.manifest, 'plugin/case', 'comp580-test', LIMITS)
        self.state_path = self.root / 'state.json'
        self.benchmark = {'benchmark_id': BID, 'name': self.plan['payload']['name'],
                          'plugin': {'id': 'plugin', 'version': '0.1.0'}, 'task_id': 'solve',
                          'limits': LIMITS, 'cases': [{'kind': 'answer', 'prompt': self.raw['prompt.txt'].decode(),
                          'prompt_sha256': r.digest(self.raw['prompt.txt']), 'arguments': {'case': 'case'},
                          'fixtures': {'files': self.plan['public_file_sha256']}}]}
        self.state = r.open_state(self.state_path, self.plan)

    def test_payload_exposes_only_public_files_and_exact_prompt(self):
        doc = r.verify_plan(self.plan)
        self.assertEqual(doc['cases'][0]['prompt'].encode(), self.raw['prompt.txt'])
        self.assertEqual(doc['cases'][0]['fixtures'], 'public')
        self.assertEqual(set(self.plan['payload']['files']), {'public/input.json', 'public/prompt.txt'})
        for name, data in self.plan['payload']['files'].items():
            self.assertEqual(base64.b64decode(data), self.raw[Path(name).name])
        self.assertNotIn('reference', self.plan['payload'])
        self.assertEqual(self.plan['payload'], r.prepare(self.manifest, 'plugin/case', 'comp580-test', LIMITS)['payload'])

    def test_dry_run_never_constructs_auth_adapter(self):
        limits_file = self.root / 'limits.json'
        r.save(limits_file, LIMITS)
        with patch.object(r, 'Live', side_effect=AssertionError('auth touched')), patch('sys.stdout', new=io.StringIO()):
            r.main(['prepare', '--fixtures', str(self.manifest), '--case', 'plugin/case',
                    '--namespace', 'comp580-test', '--limits', str(limits_file), '--out', str(self.root / 'plan.json')])
        self.assertTrue((self.root / 'plan.json').exists())

    def test_fixture_tampering_extra_file_and_symlink_fail_closed(self):
        p = self.folder / 'input.json'
        p.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash/size'):
            r.prepare(self.manifest, 'plugin/case', 'comp580-test', LIMITS)
        p.write_bytes(self.raw['input.json'])
        hidden = self.folder / 'answer.json'
        hidden.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            r.prepare(self.manifest, 'plugin/case', 'comp580-test', LIMITS)
        hidden.unlink()
        p.unlink()
        external = self.root / 'outside.json'; external.write_bytes(self.raw['input.json'])
        p.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'Symlinks'):
            r.prepare(self.manifest, 'plugin/case', 'comp580-test', LIMITS)

    def test_path_and_internet_boundary(self):
        with self.assertRaises(ValueError):
            r.child(self.root, '../elsewhere')
        with self.assertRaises(ValueError):
            r.child(self.root, '/absolute')
        for value in (True, None, 0):
            with self.assertRaises(ValueError):
                r.check_limits({**LIMITS, 'internet_access': value})
        with self.assertRaises(ValueError):
            r.check_limits({**LIMITS, 'secret_budget': 3})

    def test_trim_is_never_silent_and_payload_cannot_gain_reference(self):
        data = self.raw['prompt.txt'] + b'\n'
        (self.folder / 'prompt.txt').write_bytes(data)
        self.entry['files']['prompt.txt'] = {'sha256': r.digest(data), 'bytes': len(data)}
        r.save(self.manifest, {'cases': [self.entry]})
        with self.assertRaisesRegex(ValueError, 'surrounding whitespace'):
            r.prepare(self.manifest, 'plugin/case', 'comp580-test', LIMITS)
        altered = copy.deepcopy(self.plan)
        altered['payload']['reference'] = {'answer': 'private'}
        altered['payload_sha256'] = r.digest(r.canonical(altered['payload']))
        with self.assertRaisesRegex(ValueError, 'Unexpected publication'):
            r.verify_plan(altered)

    def test_harness_command_restrictions_and_distinct_conditions(self):
        for good in ('nanoagent', 'rush comp580 --mode=full', 'rush other-cli --option'):
            r.check_harness(good)
        for bad in ('rush help', 'rush forget all', 'rush x;touch bad', 'rush x $(env)', 'python x', 'rush x "hello"'):
            with self.assertRaises(ValueError):
                r.check_harness(bad)
        full = r.run_request(self.plan, BID, 'rush comp580 --mode=full', 'r01')
        self.assertEqual(full, r.run_request(self.plan, BID, 'rush comp580 --mode=full', 'r01'))
        self.assertNotEqual(full['idempotency_key'], r.run_request(self.plan, BID, 'rush comp580 --mode=compact', 'r01')['idempotency_key'])
        self.assertNotEqual(full['idempotency_key'], r.run_request(self.plan, BID, 'rush comp580 --mode=full', 'r02')['idempotency_key'])

    def test_publication_resume_and_hash_verification(self):
        outer = self
        class API:
            calls = []
            def discover(self, plugin, workspace):
                return '/api/workspaces/test', {'id': plugin, 'version': '0.1.0'}
            def json(self, method, path, body=None):
                self.calls.append((method, path))
                return {'benchmark': copy.deepcopy(outer.benchmark)}
        api = API()
        r.publish(api, self.plan, self.state, self.state_path, 'workspace')
        r.publish(api, self.plan, r.load(self.state_path), self.state_path, 'workspace')
        self.assertEqual(sum(m == 'POST' for m, _ in api.calls), 1)
        wrong = copy.deepcopy(self.benchmark)
        wrong['cases'][0]['fixtures']['files']['input.json'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'fixture'):
            r.check_benchmark(self.plan, wrong)

    def test_start_network_loss_resumes_same_idempotency_key(self):
        self.state.update(prefix='/api/workspaces/test', benchmark=self.benchmark, publication_verified=True)
        class API:
            requests = []
            def json(self, method, path, body=None):
                self.requests.append(copy.deepcopy(body))
                if len(self.requests) == 1:
                    raise RuntimeError('simulated lost response')
                return {'replayed': True, 'run': {'run_id': RID}}
        api = API()
        with self.assertRaises(RuntimeError):
            r.start(api, self.plan, self.state, self.state_path, 'rush comp580 --mode=full', 'r01')
        resumed = r.load(self.state_path)
        result = r.start(api, self.plan, resumed, self.state_path, 'rush comp580 --mode=full', 'r01')
        self.assertEqual(api.requests[0], api.requests[1])
        self.assertEqual(result['run_id'], RID)
        r.start(api, self.plan, resumed, self.state_path, 'rush comp580 --mode=full', 'r01')
        self.assertEqual(len(api.requests), 2)

    def test_event_pagination_does_not_drop_retry_records_or_loop(self):
        class API:
            def json(self, method, path, params):
                after = params['after']
                return {'events': [{'cursor': after + 1}], 'has_more': after == 0}
        events, pages = r.fetch_events(API(), '/attempt')
        self.assertEqual([e['cursor'] for e in events], [1, 2])
        self.assertEqual(len(pages), 2)
        class Bad:
            def json(self, *args, **kwargs):
                return {'events': [], 'has_more': True}
        with self.assertRaisesRegex(ValueError, 'did not advance'):
            r.fetch_events(Bad(), '/attempt')

    def test_capture_all_attempts_retains_missing_values_and_original_export(self):
        attempts = [{'attempt_id': aid, 'attempt_no': i + 1, 'sealed': True, 'final_cursor': 1,
                     'execution': {'status': 'worker_error' if i == 0 else 'answered'},
                     'metrics': {'cost_usd': None}, 'coverage': {'model_calls': 'partial'}} for i, aid in enumerate(AIDS)]
        run = {'run_id': RID, 'status': 'complete', 'created_at': '2026-11-23T01:00:00Z',
               'case_set': {'plugin': {'id': 'plugin'}}, 'cases': [{'attempts': attempts}]}
        self.assertTrue(r.complete(run))
        export = {'type': 'run', 'run_id': RID, 'attempts': [{'attempt_id': aid, 'workspace': None} for aid in AIDS]}
        raw = (json.dumps(export) + '\n').encode()
        outer = self
        class API:
            queries = []
            def get_bytes(self, path, params=None):
                self.queries.append((path, params))
                return raw
            def json(self, method, path, body=None, params=None):
                if path.endswith('/events'):
                    return {'events': [{'cursor': 1, 'kind': 'result.read', 'data': {'outcome': {'answer': None}}, 'payload_sha256s': []}], 'has_more': False}
                if path.endswith('/spans'):
                    return {'spans': [], 'links': [], 'truncated': True}
                if path.endswith('/accounting'):
                    return {'calls': [{'cost_usd': None, 'status': 'unsettled'}]}
                if path.endswith('/recording'):
                    return {'terminals': []}
                return {'attempt': next(a for a in attempts if path.endswith(a['attempt_id']))}
        api = API(); record = {}
        result = r.capture(api, {'prefix': '/api/workspaces/test'}, record, run, self.root / 'captures')
        index = r.load(result['capture'])
        captured = Path(result['capture']).parent
        self.assertEqual(index['actual_attempt_count'], 2)
        self.assertEqual(index['logical_trial_count'], 1)
        self.assertEqual((captured / 'native-export.jsonl').read_bytes(), raw)
        self.assertEqual(len(list((captured / 'attempts').iterdir())), 2)
        for aid in AIDS:
            self.assertIsNone(r.load(captured / 'attempts' / aid / 'accounting.json')['calls'][0]['cost_usd'])
        self.assertEqual(len(index['capture_issues']), 4)
        self.assertNotIn('member', api.queries[0][1])
        for f in index['files']:
            self.assertEqual(r.digest(Path(f['path']).read_bytes()), f['sha256'])

    def test_unfinished_runs_wait_and_unowned_runs_rejected(self):
        self.state.update(prefix='/api/workspaces/test', runs={'key': {'run_id': RID, 'request': {'benchmark_id': BID}}})
        class API:
            def json(self, *args, **kwargs):
                return {'run': {'run_id': RID, 'benchmark': {'benchmark_id': BID}, 'status': 'running', 'cases': [{'attempts': [{'sealed': False}]}]}}
        with patch.object(r, 'check_run'), patch.object(r, 'capture', side_effect=AssertionError('inflight capture')):
            self.assertTrue(r.collect(API(), self.state, self.state_path, RID, self.root, 0)['pending'])
        with self.assertRaisesRegex(ValueError, 'Only a run'):
            r.collect(API(), self.state, self.state_path, BID, self.root, 0)

    def test_run_pinned_configuration_must_match(self):
        bench = copy.deepcopy(self.benchmark)
        bench.update(model='pinned-model', endpoint_profile='profile', providers=['provider'])
        bench['cases'][0]['case_id'] = 'plugin-01'
        run = {k: copy.deepcopy(bench[k]) for k in ('model', 'endpoint_profile', 'providers', 'limits', 'cases')}
        run.update(harness={'name': 'rush comp580 --mode=full'}, case_set={'plugin': bench['plugin'], 'task_id': 'solve'})
        state = {'benchmark': bench}
        record = {'request': {'harness': 'rush comp580 --mode=full'}}
        r.check_run(state, record, run)
        run['limits']['internet_access'] = True
        with self.assertRaisesRegex(ValueError, 'pinned configuration'):
            r.check_run(state, record, run)

    def test_workspace_answer_reads_only_root_regular_file_without_extracting(self):
        def make_tar(entries):
            out = io.BytesIO()
            with tarfile.open(fileobj=out, mode='w') as archive:
                for name, data, link in entries:
                    member = tarfile.TarInfo(name)
                    if link:
                        member.type = tarfile.SYMTYPE; member.linkname = 'private'
                        archive.addfile(member)
                    else:
                        member.size = len(data); archive.addfile(member, io.BytesIO(data))
            return out.getvalue()
        fake = types.SimpleNamespace(ZstdDecompressor=lambda: types.SimpleNamespace(stream_reader=lambda stream: stream))
        with patch.dict('sys.modules', {'zstandard': fake}):
            archive = make_tar([('../answer.json', b'wrong', False), ('nested/answer.json', b'wrong', False), ('./answer.json', b'{"ok":true}', False)])
            self.assertEqual(r.workspace_answer(archive), b'{"ok":true}')
            with self.assertRaisesRegex(ValueError, 'regular file'):
                r.workspace_answer(make_tar([('answer.json', b'', True)]))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                r.workspace_answer(make_tar([('answer.json', b'one', False), ('./answer.json', b'two', False)]))

    def test_state_lock_and_evidence_are_not_overwritten(self):
        with r.locked(self.state_path):
            with self.assertRaisesRegex(ValueError, 'locked'):
                with r.locked(self.state_path):
                    pass
        evidence = self.root / 'raw.json'
        r.preserve(evidence, b'first')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            r.preserve(evidence, b'second')
        self.assertEqual(evidence.read_bytes(), b'first')


if __name__ == '__main__':
    unittest.main()
