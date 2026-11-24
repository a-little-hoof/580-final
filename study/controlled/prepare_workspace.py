"""Copy exactly the two declared public files into a NEW trial workspace.

Private validator/reference files and researcher artifacts are never copied.
This helper makes no model calls. It is host-side development infrastructure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def prepare(case_id: str, target: Path, fixtures: Path = FIXTURES) -> dict:
    manifest = json.loads((fixtures / 'manifest.json').read_text())
    matches = [case for case in manifest['cases'] if case['id'] == case_id]
    if len(matches) != 1:
        raise ValueError('Expected one declared case')
    case = matches[0]
    if set(case['files']) != {'input.json', 'prompt.txt'}:
        raise ValueError('Public file allowlist must be input.json and prompt.txt')
    relative = Path(case['directory'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid fixture directory')
    source = (fixtures / relative).resolve()
    if fixtures.resolve() not in source.parents:
        raise ValueError('Fixture source escapes fixture root')
    payloads = {}
    for name, spec in case['files'].items():
        path = source / name
        if path.is_symlink():
            raise ValueError('Symlink fixture is forbidden')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != spec['sha256'] or len(data) != spec['bytes']:
            raise ValueError(f'Fixture hash/size mismatch: {name}')
        payloads[name] = data
    target = Path(target)
    # Exclusive directory creation prevents accidental state reuse and overwrites.
    target.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        (target / name).write_bytes(data)
    return {'case_id': case_id, 'workspace': str(target.resolve()),
            'files': case['files'], 'prompt': payloads['prompt.txt'].decode('utf-8')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.case, args.out)
    # Do not print the task contents by default; paths and hashes suffice.
    result.pop('prompt')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
