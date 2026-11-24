"""Treatment invariants: only JSON presentation changes; no provider calls."""
import copy
import json
import random
import tempfile
import unittest
from pathlib import Path

from comp580_agent.agent import Agent
from comp580_agent.common import AgentError, MAX_OUTPUT_BYTES
from comp580_agent.gateway import Config
from comp580_agent.tools import format_tool_result
from test_agent import FakeGateway, completion


class CompactTests(unittest.TestCase):
    def test_unicode_whitespace_types_and_key_order_roundtrip(self):
        data = {'z': ['雪', '  keep\tall\nwhitespace  ', '"\\', None, True, False,
                      2 ** 100, -0.0, 0.25], 'a': {'nested': []}, 'empty': {}}
        full = format_tool_result(data, 'full')
        compact = format_tool_result(data, 'compact')
        self.assertEqual(json.dumps(json.loads(compact), ensure_ascii=False, indent=2, allow_nan=False), full)
        self.assertEqual(list(json.loads(compact)), ['z', 'a', 'empty'])
        self.assertEqual(json.loads(compact)['z'][1], data['z'][1])
        self.assertLess(len(compact.encode()), len(full.encode()))

    def test_deterministic_nested_json_roundtrips(self):
        rng = random.Random(580)
        atoms = [None, False, True, 0, -17, 0.00001, -0.0, '', '\n\t  ', '🙂 café']
        def value(depth):
            if depth == 0 or rng.randrange(3) == 0:
                return rng.choice(atoms)
            if rng.randrange(2):
                return [value(depth - 1) for _ in range(rng.randrange(6))]
            return {f'key {i}': value(depth - 1) for i in range(rng.randrange(6))}
        for _ in range(100):
            data = value(4)
            compact = format_tool_result(data, 'compact')
            self.assertEqual(json.dumps(json.loads(compact), ensure_ascii=False, indent=2, allow_nan=False),
                             format_tool_result(data, 'full'))
            self.assertEqual(compact, format_tool_result(data, 'compact'))

    def test_nonfinite_and_unknown_condition_fail(self):
        for condition in ['full', 'compact']:
            for data in [float('nan'), {'x': float('inf')}]:
                with self.assertRaises(ValueError):
                    format_tool_result(data, condition)
        with self.assertRaises(AgentError):
            format_tool_result({}, 'preview')

    def run_condition(self, root, condition, payload='{"x":[1,2],"text":" keep  spaces "}', oversize=False):
        workspace = root / condition
        workspace.mkdir()
        (workspace / 'input.json').write_text(payload)
        if oversize:
            (workspace / 'large.txt').write_text('\t' * (MAX_OUTPUT_BYTES // 2))
        responses = [completion([('read_file' if oversize else 'read_json',
                                  {'path': 'large.txt' if oversize else 'input.json'})]),
                     completion([('write_answer', {'answer': {'done': True}})])]
        fake = FakeGateway(responses)
        result = Agent(Config('https://gateway.invalid/v1', 'test-key', 'fixed/model', 32768),
                       workspace, root / f'{condition}-logs', gateway=fake).run('Exact task request', condition=condition)
        return result, fake

    def test_requests_differ_only_in_tool_content_presentation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            full, a = self.run_condition(root, 'full')
            compact, b = self.run_condition(root, 'compact')
            self.assertEqual(full['status'], 'completed')
            self.assertEqual(compact['status'], 'completed')
            self.assertEqual(a.requests[0], b.requests[0])
            aa, bb = copy.deepcopy(a.requests[1]), copy.deepcopy(b.requests[1])
            a_tool, b_tool = aa['messages'][-1], bb['messages'][-1]
            self.assertNotEqual(a_tool['content'], b_tool['content'])
            self.assertEqual(json.loads(a_tool['content']), json.loads(b_tool['content']))
            a_tool['content'] = b_tool['content'] = '<same parsed JSON>'
            self.assertEqual(aa, bb)
            self.assertEqual((root / 'full/answer.json').read_bytes(), (root / 'compact/answer.json').read_bytes())

    def test_same_full_form_output_ceiling_in_both_conditions(self):
        with tempfile.TemporaryDirectory() as folder:
            for condition in ['full', 'compact']:
                result, fake = self.run_condition(Path(folder), condition, oversize=True)
                self.assertEqual(result['failure']['code'], 'output_limit')
                self.assertEqual(len(fake.requests), 1)
                self.assertFalse((Path(folder) / f'{condition}-logs/tools/001.visible.txt').exists())


if __name__ == '__main__':
    unittest.main()
