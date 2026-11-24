"""One-request, no-retry OpenAI-compatible Chat Completions transport."""

import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .common import AgentError, MAX_RESPONSE_BYTES, json_text


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    max_output_tokens: int

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        names = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "RUSH_MODEL", "RUSH_MAX_OUTPUT_TOKENS")
        if any(not env.get(name) for name in names):
            raise AgentError("configuration", "Required Harness gateway environment variables are missing", fatal=True)
        url = urllib.parse.urlsplit(env["OPENAI_BASE_URL"])
        if (url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise AgentError("configuration", "Gateway URL must be HTTP(S) without embedded credentials, query, or fragment", fatal=True)
        try:
            cap = int(env["RUSH_MAX_OUTPUT_TOKENS"])
        except (TypeError, ValueError) as error:
            raise AgentError("configuration", "RUSH_MAX_OUTPUT_TOKENS must be a positive integer", fatal=True) from error
        if cap <= 0:
            raise AgentError("configuration", "RUSH_MAX_OUTPUT_TOKENS must be a positive integer", fatal=True)
        return cls(env["OPENAI_BASE_URL"].rstrip("/"), env["OPENAI_API_KEY"], env["RUSH_MODEL"], cap)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward the scoped bearer credential to a redirected destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Gateway:
    def __init__(self, config):
        self.config = config

    def complete(self, payload, *, timeout):
        request = urllib.request.Request(
            self.config.base_url + "/chat/completions",
            data=json_text(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.config.api_key})
        try:
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            # Provider error bodies and exception strings may contain credentials.
            raise AgentError("http_error", "Gateway rejected the request", fatal=True,
                             details={"http_status": error.code}) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AgentError("transport_error", "Gateway request failed; no retry was attempted", fatal=True) from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise AgentError("output_limit", "Gateway response exceeded 2 MiB; no truncated response was used",
                             fatal=True, details={"source": "gateway", "capture_complete": False})
        return body
