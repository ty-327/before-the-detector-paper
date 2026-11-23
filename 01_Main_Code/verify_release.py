#!/usr/bin/env python3
"""Read-only manifest/raw-input check for the packaged COSE testing candidate."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--raw', type=Path, help='Optional exact raw Kaggle ZIP to verify')
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / 'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    failed = []
    for entry in manifest['files']:
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root):
            failed.append(entry['path'] + ': unsafe path'); continue
        if not path.is_file():
            failed.append(entry['path'] + ': missing'); continue
        if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            failed.append(entry['path'] + ': size/hash mismatch')
    if args.raw:
        expected = 'e00557bd8dc6d5e1a09f8da36213039ac23950f9613e245db49c6ef564ce6df7'
        if not args.raw.is_file():
            failed.append('Raw archive: not found')
        elif args.raw.stat().st_size != 901195556 or digest(args.raw) != expected:
            failed.append('Raw archive: not the pinned snapshot')
        else:
            print('PASS: raw archive size and SHA-256')
    else:
        print('Raw archive not supplied to this preflight; verify it before running reproduce.py.')
    print(f"Checked {len(manifest['files'])} packaged files; mismatches: {len(failed)}")
    for message in failed:
        print('FAIL:', message)
    print('No analytical code, settings, outputs or raw data were modified.')
    return 1 if failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
