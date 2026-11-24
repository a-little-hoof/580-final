import io
import json
import urllib.error
import unittest
from unittest.mock import patch

from comp580_agent.common import AgentError, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES
from comp580_agent.gateway import Config, Gateway, _NoRedirect


class FakeOpener:
    def __init__(self, body=b'{}', error=None):
        self.body, self.error = body, error
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return io.BytesIO(self.body)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.config = Config("https://gateway.invalid/v1", "scoped-test-key", "pinned/model", 4096)

    def test_wire_request_is_one_json_post_with_secret_only_in_header(self):
        opener = FakeOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            self.assertEqual(Gateway(self.config).complete({"model": "pinned/model"}, timeout=27), b'{}')
        request, timeout = opener.requests[0]
        self.assertEqual(request.full_url, "https://gateway.invalid/v1/chat/completions")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer scoped-test-key")
        self.assertEqual(json.loads(request.data), {"model": "pinned/model"})
        self.assertEqual(timeout, 27)

    def test_http_error_does_not_retry_or_expose_provider_body(self):
        error = urllib.error.HTTPError("https://gateway.invalid", 401, "scoped-test-key", {}, io.BytesIO(b'scoped-test-key'))
        opener = FakeOpener(error=error)
        with patch("urllib.request.build_opener", return_value=opener), self.assertRaises(AgentError) as caught:
            Gateway(self.config).complete({}, timeout=60)
        self.assertEqual(caught.exception.details, {"http_status": 401})
        self.assertNotIn(self.config.api_key, str(caught.exception))
        self.assertEqual(len(opener.requests), 1)

    def test_oversize_response_and_redirect_are_rejected(self):
        with patch("urllib.request.build_opener", return_value=FakeOpener(b'x' * (MAX_RESPONSE_BYTES + 1))), self.assertRaises(AgentError) as caught:
            Gateway(self.config).complete({}, timeout=60)
        self.assertEqual(caught.exception.code, "output_limit")
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    def test_response_limit_is_independent_of_tool_output_limit(self):
        for size in (MAX_OUTPUT_BYTES + 1, MAX_RESPONSE_BYTES):
            with self.subTest(bytes=size):
                body = b"x" * size
                with patch("urllib.request.build_opener", return_value=FakeOpener(body)):
                    self.assertEqual(Gateway(self.config).complete({}, timeout=60), body)

    def test_environment_is_required_and_secret_absent_from_config_repr(self):
        env = {"OPENAI_BASE_URL": "https://gateway.invalid/v1", "OPENAI_API_KEY": "scoped-test-key",
               "RUSH_MODEL": "pinned/model", "RUSH_MAX_OUTPUT_TOKENS": "4096"}
        self.assertEqual(Config.from_env(env), self.config)
        self.assertNotIn("scoped-test-key", repr(self.config))
        for missing in env:
            with self.subTest(missing=missing), self.assertRaises(AgentError):
                Config.from_env({k: v for k, v in env.items() if k != missing})
        for url in ("https://u:p@host/v1", "https://host/v1?key=secret", "file:///tmp/gateway"):
            with self.subTest(url=url), self.assertRaises(AgentError):
                Config.from_env({**env, "OPENAI_BASE_URL": url})


if __name__ == "__main__":
    unittest.main()
