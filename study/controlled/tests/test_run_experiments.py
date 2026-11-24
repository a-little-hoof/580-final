"""Offline frozen-schedule, provenance and crash-replay tests."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
import zipfile

PATH = Path(__file__).resolve().parents[1] / 'run_experiments.py'
spec = importlib.util.spec_from_file_location('run_experiments', PATH)
x = importlib.util.module_from_spec(spec); spec.loader.exec_module(x)
r = x.rb
LIMITS = {'wall_time_ms': 180000, 'max_model_calls': 12, 'max_output_tokens_per_call': 32768,
          'max_cost_usd': .05, 'internet_access': False}


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pkg = self.root / 'src/comp580_agent'; pkg.mkdir(parents=True)
        for name in ('__init__.py', 'cli.py', 'agent.py'):
            (pkg / name).write_text('# frozen test module ' + name)
        self.wheel = self.root / 'agent.whl'
        with zipfile.ZipFile(self.wheel, 'w') as wheel:
            for p in pkg.iterdir():
                wheel.write(p, 'comp580_agent/' + p.name)
        entries = []
        for i in range(5):
            folder = self.root / f'fixtures/p{i}/case'; folder.mkdir(parents=True)
            (folder / 'input.json').write_text('{}')
            (folder / 'prompt.txt').write_text(f'Solve case with p{i}.')
            entries.append({'id': f'p{i}/case', 'plugin_id': f'p{i}', 'task': 'solve', 'case': 'case',
                            'directory': f'p{i}/case', 'source': {'version': '0.1.0'},
                            'files': {p.name: {'sha256': r.digest(p.read_bytes()), 'bytes': p.stat().st_size} for p in folder.iterdir()}})
        manifest = self.root / 'fixtures/manifest.json'; r.save(manifest, {'cases': entries})
        self.pairs = []
        for i, entry in enumerate(entries):
            plan = r.prepare(manifest, entry['id'], 'comp580-test', LIMITS)
            pp, sp = self.root / f'plan{i}.json', self.root / f'state{i}.json'
            doc = r.verify_plan(plan)
            bench = {'benchmark_id': str(uuid.UUID(int=i + 1)), 'name': plan['payload']['name'],
                     'plugin': {'id': f'p{i}', 'version': '0.1.0', 'sha256': 'package'}, 'task_id': 'solve',
                     'model': 'shared-model', 'endpoint_profile': 'endpoint', 'providers': ['provider'], 'limits': LIMITS,
                     'cases': [{'case_id': f'p{i}-01', 'kind': 'answer', 'prompt': doc['cases'][0]['prompt'],
                                'prompt_sha256': plan['prompt_sha256'], 'arguments': {'case': 'case'},
                                'fixtures': {'sha256': 'archive', 'files': plan['public_file_sha256']}}]}
            r.save(pp, plan)
            r.save(sp, {'schema_version': 1, 'plan_sha256': plan['payload_sha256'], 'prefix': '/api/workspaces/test',
                        'publication_verified': True, 'benchmark': bench, 'runs': {}})
            self.pairs.append((pp, sp))
        self.frozen = x.freeze(self.root, self.pairs, self.wheel, 580, [], inputs=['src', 'fixtures'])
        self.progress = {'freeze_sha256': self.frozen['freeze_sha256'], 'trials': {}}
        self.progress_path = self.root / 'progress.json'

    def test_seed_balances_fifty_trials_and_keeps_pairs_adjacent(self):
        rows = self.frozen['trials']
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({t['request']['idempotency_key'] for t in rows}), 50)
        for start in range(0, 50, 2):
            a, b = rows[start:start + 2]
            self.assertEqual((a['case_id'], a['replicate'], a['benchmark_id']), (b['case_id'], b['replicate'], b['benchmark_id']))
            self.assertEqual({a['condition'], b['condition']}, {'full', 'compact'})
        self.assertEqual(rows, x.schedule_rows(self.frozen['cases'], 580, self.frozen['wheel']['code_sha256']))
        self.assertNotEqual(rows, x.schedule_rows(self.frozen['cases'], 581, self.frozen['wheel']['code_sha256']))
        self.assertTrue(all('--code-sha256 ' + self.frozen['wheel']['code_sha256'] in t['request']['harness'] for t in rows))

    def test_freeze_verifies_package_and_all_input_drift(self):
        x.verify_freeze(self.frozen)
        (self.root / 'src/comp580_agent/agent.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'tree changed'):
            x.verify_freeze(self.frozen)
        with self.assertRaisesRegex(ValueError, 'Wheel modules differ'):
            x.freeze(self.root, self.pairs, self.wheel, 580, [], inputs=['src'])

    def test_plan_and_order_drift_stop(self):
        wrong = copy.deepcopy(self.frozen); wrong['trials'].reverse()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            x.verify_freeze(wrong)
        plan_path = self.pairs[0][0]; plan = r.load(plan_path); plan['boundary'] = 'edited'
        r.save(plan_path, plan)
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            x.verify_freeze(self.frozen)

    def test_smoke_must_be_explicitly_excluded_and_configuration_shared(self):
        sp = self.pairs[0][1]; state = r.load(sp); smoke = str(uuid.uuid4())
        state['runs']['smoke'] = {'run_id': smoke}; r.save(sp, state)
        with self.assertRaisesRegex(ValueError, 'explicitly excluded'):
            x.freeze(self.root, self.pairs, self.wheel, 580, [], inputs=['src'])
        frozen = x.freeze(self.root, self.pairs, self.wheel, 580, [smoke], inputs=['src'])
        self.assertEqual(frozen['excluded_run_ids'], [smoke])
        state['benchmark']['model'] = 'different'; r.save(sp, state)
        with self.assertRaisesRegex(ValueError, 'same pinned configuration'):
            x.freeze(self.root, self.pairs, self.wheel, 580, [smoke], inputs=['src'])

    def test_step_starts_only_one_trial_and_crash_replays_same_key(self):
        trial = self.frozen['trials'][0]
        case = next(c for c in self.frozen['cases'] if c['case_id'] == trial['case_id'])
        bench = case['benchmark']; run_id = str(uuid.uuid4())
        class API:
            requests = []
            def json(self, method, path, body=None):
                if method == 'GET':
                    return {'benchmark': bench}
                self.requests.append(copy.deepcopy(body))
                if len(self.requests) == 1:
                    raise RuntimeError('lost response')
                return {'replayed': True, 'run': {'run_id': run_id}}
        api = API()
        with self.assertRaises(RuntimeError):
            x.step(api, self.frozen, self.progress, self.progress_path, self.root / 'evidence')
        resumed = r.load(self.progress_path)
        result = x.step(api, self.frozen, resumed, self.progress_path, self.root / 'evidence')
        self.assertEqual(result['run_id'], run_id)
        self.assertEqual(api.requests, [trial['request'], trial['request']])
        self.assertEqual(len(resumed['trials']), 1)
        with patch.object(r, 'collect', return_value={'pending': True, 'run_id': run_id, 'status': 'running'}) as collect:
            result = x.step(api, self.frozen, resumed, self.progress_path, self.root / 'evidence', 0)
        self.assertEqual(result['action'], 'poll'); self.assertEqual(len(api.requests), 2)
        collect.assert_called_once()

    def test_capture_keeps_failed_trial_and_stops_identity_drift(self):
        trial = self.frozen['trials'][0]; run_id = str(uuid.uuid4())
        self.progress['trials'][trial['trial_id']] = {'phase': 'started', 'request': trial['request'], 'run_id': run_id}
        target = self.root / 'capture'; target.mkdir()
        checked = {'actual_attempts': 3, 'identity_and_capture_issues': [{'issue': 'agent_identity_or_condition_drift'}], 'attempts': []}
        with patch.object(r, 'collect', return_value={'capture': str(target / 'capture.json')}), patch.object(x, 'check_capture', return_value=checked):
            result = x.step(object(), self.frozen, self.progress, self.progress_path, self.root)
        self.assertEqual(result['phase'], 'needs_review')
        self.assertEqual(self.progress['trials'][trial['trial_id']]['actual_attempts'], 3)
        with patch.object(r, 'start', side_effect=AssertionError('started next trial')), patch.object(r, 'collect', side_effect=AssertionError('auto retry capture')):
            result = x.step(object(), self.frozen, self.progress, self.progress_path, self.root)
        self.assertTrue(result['needs_review'])
        self.assertEqual(len(self.progress['trials']), 1)

    def test_native_failure_is_captured_and_not_replaced(self):
        trial = self.frozen['trials'][0]; run_id = str(uuid.uuid4())
        self.progress['trials'][trial['trial_id']] = {'phase': 'started', 'request': trial['request'], 'run_id': run_id}
        target = self.root / 'capture'; target.mkdir()
        checked = {'actual_attempts': 2, 'identity_and_capture_issues': [], 'attempts': [{'verdict': 'fail'}, {'verdict': 'fail'}]}
        with patch.object(r, 'collect', return_value={'capture': str(target / 'capture.json')}), patch.object(x, 'check_capture', return_value=checked):
            result = x.step(object(), self.frozen, self.progress, self.progress_path, self.root)
        self.assertEqual(result['phase'], 'captured')
        self.assertEqual(x.status(self.frozen, self.progress)['captured_logical_trials'], 1)
        self.assertEqual(x.status(self.frozen, self.progress)['actual_attempts'], 2)


if __name__ == '__main__':
    unittest.main()
