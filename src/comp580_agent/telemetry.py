"""Attempt evidence without environment dumps, headers, or bearer credentials."""

from pathlib import Path
import json

from .common import AgentError, json_text, sha256


class Telemetry:
    def __init__(self, directory, *, secrets=()):
        self.directory = Path(directory).resolve()
        self.secrets = tuple(s for s in secrets if s)
        self.directory.mkdir(parents=True, exist_ok=True)
        if any(self.directory.iterdir()):
            raise AgentError("log_directory", "Log directory must be empty to avoid overwriting evidence", fatal=True)

    def clean(self, text):
        for secret in self.secrets:
            # Also cover credentials echoed inside JSON strings with escaped bytes.
            forms = {secret, json.dumps(secret, ensure_ascii=False)[1:-1],
                     json.dumps(secret, ensure_ascii=True)[1:-1]}
            for form in sorted(forms, key=len, reverse=True):
                text = text.replace(form, "[REDACTED_CREDENTIAL]")
        return text

    def save_text(self, name, text):
        safe = self.clean(text)
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(safe)
        data = safe.encode("utf-8")
        return {"path": name, "bytes": len(data), "sha256": sha256(data),
                "credential_redacted": safe != text,
                "original_bytes": len(text.encode("utf-8")),
                "original_sha256": sha256(text.encode("utf-8"))}

    def save_json(self, name, data):
        return self.save_text(name, json_text(data))

    def event(self, data):
        # One compact line is an event envelope, not a model-visible tool result.
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(self.clean(json.dumps(data, ensure_ascii=False, allow_nan=False)) + "\n")
