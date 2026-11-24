import contextlib
import hashlib
import io
import json
import unittest
from unittest.mock import patch
from comp580_agent.cli import main
from comp580_agent.common import package_fingerprint


class FingerprintTests(unittest.TestCase):
    def test_digest_covers_module_hashes(self):
        value = package_fingerprint()
        self.assertIn('agent.py', value['package_modules_sha256'])
        self.assertIn('tools.py', value['package_modules_sha256'])
        self.assertEqual(value['code_sha256'], hashlib.sha256(json.dumps(
            value['package_modules_sha256'], sort_keys=True, separators=(',', ':')).encode()).hexdigest())

    def test_wrong_package_fails_before_credentials_or_model_access(self):
        output = io.StringIO()
        with patch('comp580_agent.cli.Config.from_env') as env, contextlib.redirect_stderr(output):
            self.assertEqual(main(['--code-sha256', '0' * 64, 'Exact prompt']), 1)
        env.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['code'], 'package_drift')
