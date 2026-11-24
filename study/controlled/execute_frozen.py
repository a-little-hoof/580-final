#!/usr/bin/env python3
"""Run the already-frozen schedule sequentially; stop on any review/error state.

All run intents, idempotency, source guards and capture checks live in
run_experiments.step. This wrapper adds no trials or retries of its own.
"""
import argparse
import json
from pathlib import Path

import run_experiments as experiment


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--freeze', type=Path, required=True)
    p.add_argument('--progress', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    a = p.parse_args()
    rb = experiment.rb
    frozen = rb.load(a.freeze)
    experiment.verify_freeze(frozen)
    with rb.locked(a.progress):
        progress = rb.load(a.progress) if a.progress.exists() else {'freeze_sha256': frozen['freeze_sha256'], 'trials': {}}
        api = rb.Live()
        try:
            while True:
                result = experiment.step(api, frozen, progress, a.progress, a.evidence, wait_seconds=30)
                print(json.dumps(result), flush=True)
                if result.get('needs_review') or result.get('phase') == 'needs_review':
                    return 2
                if result.get('complete'):
                    return 0
        finally:
            api.close()


if __name__ == '__main__':
    raise SystemExit(main())
