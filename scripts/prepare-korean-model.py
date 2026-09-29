"""Explicit, bounded download of registered model files with SHA256 verification."""

import argparse
import hashlib
import http.client
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-download', action='store_true')
    args = parser.parse_args()
    registry = json.loads((ROOT / 'models/korean-ocr-candidates.json').read_text('utf-8'))
    weights = (ROOT / 'models/weights').resolve()
    for row in registry['files']:
        path = (weights / row['path']).resolve()
        if not path.is_relative_to(weights) or row['bytes'] > 100_000_000:
            raise ValueError('INVALID_MODEL_REGISTRY')
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']:
            print('VERIFIED', row['path'])
            continue
        if not args.allow_download:
            raise ValueError('MODEL_MISSING_OR_CHANGED: explicit --allow-download required')
        path.parent.mkdir(parents=True, exist_ok=True)
        data = b''
        for attempt in range(8):
            url = row['url'] + f'?download=true&retry={attempt}'
            request = Request(url, headers={'Range': f'bytes={len(data)}-'})
            with urlopen(request, timeout=40) as response:
                partial = (response.status == 206 and response.headers.get(
                    'Content-Range', '').startswith(f'bytes {len(data)}-'))
                try:
                    chunk = response.read(row['bytes'] + 1)
                except http.client.IncompleteRead as exc:
                    chunk = exc.partial
            data = data + chunk if partial else chunk
            if len(data) > row['bytes']:
                raise ValueError('MODEL_DOWNLOAD_TOO_LARGE')
            if len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']:
                temp = path.with_suffix(path.suffix + '.partial')
                temp.write_bytes(data)
                temp.replace(path)
                print('VERIFIED', row['path'])
                break
        else:
            raise ValueError('MODEL_DOWNLOAD_HASH_MISMATCH')


if __name__ == '__main__':
    main()
