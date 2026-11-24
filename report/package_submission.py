#!/usr/bin/env python3
"""Package Git-eligible project files with hashes; reject obvious credentials.

Reference checkouts and local continuation files are excluded by .gitignore.
The source ZIP is a fallback artifact, not an automatic Canvas submission.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [re.compile(rb'sk-or-v1-[A-Za-z0-9_-]{30,}'),
            re.compile(rb'Bearer [A-Za-z0-9_.-]{40,}'),
            re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]


def check_bytes(raw, name, depth=0):
    if any(pattern.search(raw) for pattern in PATTERNS):
        raise ValueError('Possible credential in ' + name + '; content withheld')
    if depth >= 2:
        return
    if raw.startswith(b'\x28\xb5\x2f\xfd'):
        import zstandard
        with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as stream:
            with tarfile.open(fileobj=stream, mode='r|') as archive:
                total = 0
                for member in archive:
                    if not member.isfile():
                        continue
                    total += member.size
                    if member.size > 16 << 20 or total > 64 << 20:
                        raise ValueError('Archive review bound exceeded: ' + name)
                    check_bytes(archive.extractfile(member).read(), name + ':' + member.name, depth + 1)
    elif raw.startswith(b'PK\x03\x04'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(m.file_size for m in archive.infolist()) > 64 << 20:
                raise ValueError('ZIP review bound exceeded: ' + name)
            for member in archive.infolist():
                if not member.is_dir():
                    check_bytes(archive.read(member), name + ':' + member.filename, depth + 1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=ROOT/'output/comp580-yw251-source.zip')
    a = p.parse_args()
    progress = json.loads((ROOT/'study/controlled/final/progress.json').read_text())
    if len(progress['trials']) != 50 or any(t.get('phase') != 'captured' for t in progress['trials'].values()):
        raise ValueError('Final package requires all fifty captured trials')
    analysis = json.loads((ROOT/'study/controlled/final/analysis/analysis.json').read_text())
    if analysis['captured_trials'] != 50:
        raise ValueError('Analysis is incomplete')
    if not (ROOT/'output/pdf/comp580-yw251-report.pdf').is_file():
        raise ValueError('Final report PDF is missing')
    names = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    frozen = json.loads((ROOT/'study/controlled/final/freeze.json').read_text())
    missing = set(frozen['source_tree']['files']) - set(names)
    if missing:
        raise ValueError('Frozen input excluded from package: ' + ', '.join(sorted(missing)))
    entries = []
    for name in sorted(set(names) - {''}):
        path = ROOT/name
        if path.resolve() == a.out.resolve():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('Unsafe package path: ' + name)
        if not path.is_file():
            continue
        if any(part in {'references','.venv','.git','__pycache__'} for part in PurePosixPath(name).parts):
            raise ValueError('Excluded path entered package: ' + name)
        raw = path.read_bytes()
        check_bytes(raw, name)
        entries.append((name, raw))
    manifest = {'schema_version':1, 'purpose':'COMP580 source/evidence fallback package',
                'file_count':len(entries), 'files':{name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in entries},
                'credential_review':'Known provider-key, bearer-token and private-key patterns; bounded ZIP/tar.zst members scanned without extraction.'}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in entries:
            archive.writestr('comp580-yw251/'+name,raw)
        archive.writestr('comp580-yw251/PACKAGE_MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(a.out) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity failure')
    print(json.dumps({'package':str(a.out),'files':len(entries),'bytes':a.out.stat().st_size,
                      'sha256':hashlib.sha256(a.out.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
