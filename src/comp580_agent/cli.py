"""CLI accepting an exact explicit prompt or Harness-appended final argument."""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from .agent import Agent
from .common import AgentError, package_fingerprint
from .gateway import Config


def parser():
    result = argparse.ArgumentParser(description="Original COMP580 agent with lossless JSON formatting conditions")
    result.add_argument("--condition", choices=["full", "compact"], default="full")
    result.add_argument("--prompt", dest="explicit_prompt")
    result.add_argument("--workspace", type=Path, default=Path(os.environ.get("RUSH_WORKSPACE", ".")))
    result.add_argument("--log-dir", type=Path)
    result.add_argument("--code-sha256", help="Require this installed-source fingerprint before any model request")
    result.add_argument("prompt", nargs="?", help="Exact user prompt appended by Harness")
    return result


def main(argv=None):
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if (args.explicit_prompt is None) == (args.prompt is None):
        argument_parser.error("Supply the exact prompt either with --prompt or as the final argument")
    prompt = args.explicit_prompt if args.explicit_prompt is not None else args.prompt
    log_dir = args.log_dir or args.workspace / ".comp580_logs" / uuid.uuid4().hex
    try:
        if args.code_sha256 is not None and package_fingerprint()["code_sha256"] != args.code_sha256:
            raise AgentError("package_drift", "Installed source does not match the frozen study", fatal=True)
        config = Config.from_env()
        result = Agent(config, args.workspace, log_dir).run(prompt, condition=args.condition)
    except (AgentError, OSError) as error:
        code = error.code if isinstance(error, AgentError) else "local_error"
        print(json.dumps({"status": "failed", "code": code}), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "error_code": (result["failure"] or {}).get("code"),
                      "model_calls": len(result["model_calls"]), "tool_calls": result["tool_calls"]}))
    return 0 if result["status"] == "completed" else 1
