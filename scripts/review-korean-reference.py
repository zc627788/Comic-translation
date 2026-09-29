"""Rebuild the source-assisted reference from reviewed SVG IDs; never from OCR output."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-download', action='store_true')
    args = parser.parse_args()
    index = json.loads((ROOT / 'datasets/korean-reference-v2.json').read_text('utf-8'))
    base = ROOT / 'artifacts/private/korean-model-v2'
    base.mkdir(exist_ok=True)
    original = ROOT / 'artifacts/private/korean-comparison-v1/annotations-v1.json'
    if digest(original.read_bytes()) != index['previous_annotation_sha256']:
        raise ValueError('PREVIOUS_REFERENCE_CHANGED')
    reference = json.loads(original.read_text('utf-8'))
    for row, reviewed in zip(reference['regions'], index['regions'], strict=True):
        if row['id'] != reviewed['id'] or row['box'] != reviewed['box']:
            raise ValueError('REVIEW_ALIGNMENT_CHANGED')
        source = reviewed['source']
        file = base / source['url'].rsplit('/', 1)[-1]
        if not file.exists():
            if not args.allow_download:
                raise ValueError('SOURCE_MISSING: explicit --allow-download required')
            data = urlopen(source['url'], timeout=30).read(2_000_001)
            if digest(data) != source['sha256']:
                raise ValueError('SOURCE_DOWNLOAD_HASH_MISMATCH')
            file.write_bytes(data)
        if digest(file.read_bytes()) != source['sha256']:
            raise ValueError('FROZEN_SVG_CHANGED')
        tree = ET.parse(file)
        elements = {e.attrib.get('id'): ''.join(e.itertext()) for e in tree.iter()}
        row['previous_text'] = row['text']
        row['text'] = ' '.join(' '.join(elements[k].split()) for k in source['element_ids'])
        row['previous_legible'] = row['legible']
        row['legible'] = True
        row['status'] = 'official_svg_cross_checked_with_raster_by_ai'
        row['uncertainty'] = None
        row['source'] = source
        row['review_note'] = ('source element text cross-checked with frozen raster; '
                              'not human-reviewed; original crop unchanged')
    reference['version'] = 2
    reference['previous_annotation_sha256'] = index['previous_annotation_sha256']
    reference['annotator'] = ('official source text + AI raster review; '
                              'not human or independent double review')
    reference['created_before_candidate_outputs'] = True
    # The frozen Windows reference was written with CRLF; preserve its exact byte hash.
    data = (json.dumps(reference, ensure_ascii=False, indent=2) + '\n')
    data = data.replace('\n', '\r\n').encode('utf-8')
    if digest(data) != index['annotation_sha256']:
        raise ValueError('REBUILT_REFERENCE_MISMATCH')
    output = base / 'annotations-v2.json'
    if output.exists() and output.read_bytes() != data:
        raise ValueError('REFUSE_OVERWRITE_REFERENCE')
    if not output.exists():
        output.write_bytes(data)
    print('VERIFIED official-source-assisted reference v2; human review still pending')


if __name__ == '__main__':
    main()
