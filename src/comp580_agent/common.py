"""Shared deterministic limits and strict JSON handling."""

import contextlib
import hashlib
import json
import math
import signal
import time
from pathlib import Path

MAX_OUTPUT_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_MODEL_CALLS = 12
TOOL_SECONDS = 10.0
ATTEMPT_SECONDS = 180.0
REQUEST_SECONDS = 60.0


class AgentError(Exception):
    def __init__(self, code, message, *, fatal=False, details=None):
        super().__init__(message)
        self.code = code
        self.fatal = fatal
        self.details = details or {}


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def strict_json(text):
    def invalid(value):
        raise ValueError(f"Nonfinite JSON value {value} is not allowed")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON keys are not allowed")
            result[key] = value
        return result

    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            invalid(value)
        return number
    return json.loads(text, parse_constant=invalid, object_pairs_hook=pairs, parse_float=finite)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def package_fingerprint():
    """Identify the actual installed Python source, independently of version text."""
    modules = {p.name: sha256(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}
    encoded = json.dumps(modules, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"code_sha256": sha256(encoded), "package_modules_sha256": modules}


@contextlib.contextmanager
def time_limit(seconds, code):
    """Interrupt blocking operations on the supported POSIX CLI main thread."""
    if not hasattr(signal, "setitimer"):
        raise AgentError("unsupported_platform", "This baseline requires POSIX interval timers", fatal=True)
    if seconds <= 0:
        raise AgentError(code, "Time limit exceeded", fatal=True)
    previous = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def expired(_signum, _frame):
        raise AgentError(code, "Time limit exceeded", fatal=True)

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, max(.000001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1])
