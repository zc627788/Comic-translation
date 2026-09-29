"""Compare fixed local OCR configurations against private provisional visual annotations."""

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from services.worker.quality_metrics import distance, normalize

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_review(annotation, folder):
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    outputs = {r['variant']: json.loads((folder / r['variant'] / 'ocr.json').read_text('utf-8'))
               for r in summary['results']}
    sections = []
    for index, row in enumerate(annotation['regions']):
        reference = html.escape(row['text'] or '不确定，未计入字符指标')
        items = ''.join(f"<li>{html.escape(name)}：{html.escape(values[index]['text'])}</li>"
                        for name, values in outputs.items())
        sections.append(f"<section><h2>{html.escape(row['id'])}</h2>"
                        f"<img src='/ocr-crops/{row['id']}.png' alt='原图对白裁图'>"
                        f"<p>AI 暂定转录：{reference}</p>"
                        f"<ul>{items}</ul></section>")
    document = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>韩文 OCR 配置对照</title><style>
body{max-width:1050px;margin:40px auto;padding:20px;font:16px 'Microsoft YaHei';background:#f4f6f3}
section{background:white;padding:24px;margin:20px 0;border:1px solid #ddd;border-radius:12px}
img{max-width:100%;height:auto}li,p{line-height:1.8}h1{font-size:28px}
</style><h1>韩文 OCR · 同图四配置对照</h1>
<p>3 页、8 处真实对白，7 处计入指标。AI 视觉暂定转录，尚无人类复核。
这是参考裁图识别比较，不代表自动检测或翻译质量；未选出可靠的新默认配置。</p>
<p>Pepper&amp;Carrot / David Revoy；韩译 Shikamaru “initbar” Yamamoto；校对 Jihoon Kim。
第一话另有 GunChleoc / Hồ Châu 贡献。CC BY 4.0；这里只裁切和缩放原图，无翻译替换。
<a href='https://www.peppercarrot.com/kr/webcomics/peppercarrot.html'>原作</a> ·
<a href='https://www.peppercarrot.com/kr/about/index.html'>许可</a></p>
""" + ''.join(sections) + '</html>'
    (folder / 'review.html').write_text(document, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--run-id', default='comparison-v1')
    args = parser.parse_args()
    if not args.run_id.replace('-', '').isalnum():
        parser.error('Invalid run ID')
    annotation = json.loads(args.annotations.read_text(encoding='utf-8'))
    folder = args.annotations.parent / args.run_id
    folder.mkdir(exist_ok=False)
    rows = annotation['regions']
    variants = [('raw-3x-block', 3, False, 'block'), ('raw-1x-block', 1, False, 'block'),
                ('otsu-3x-block', 3, True, 'block'), ('raw-3x-sparse', 3, False, 'sparse')]
    summary = {'annotation_sha256': digest(args.annotations),
               'annotation_status': 'provisional_ai_visual_not_human_reviewed',
               'regions': len(rows), 'scored_regions': sum(r['legible'] for r in rows),
               'evaluation': 'reference crops only; not end-to-end detector accuracy',
               'candidate_script_sha256': digest(ROOT / 'services/worker/ocr_korean.mjs'),
               'runner_sha256': digest(Path(__file__)), 'results': []}
    for name, scale, binary, mode in variants:
        target = folder / name
        target.mkdir()
        files = []
        for row in rows:
            source = ROOT / 'artifacts/private/quality-v1/images' / (row['page'] + '.png')
            if digest(source) != row['image_sha256']:
                raise ValueError('FROZEN_INPUT_CHANGED')
            with Image.open(source) as image:
                crop = image.convert('RGB').crop(row['box'])
            if scale != 1:
                crop = crop.resize((crop.width * scale, crop.height * scale),
                                   Image.Resampling.LANCZOS)
            if binary:
                gray = np.asarray(ImageOps.grayscale(crop))
                _, pixels = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                crop = Image.fromarray(pixels)
            path = target / (row['id'] + '.png')
            crop.save(path)
            files.append(str(path.resolve()))
        manifest = target / 'crops.json'
        manifest.write_text(json.dumps(files), encoding='utf-8')
        started = time.perf_counter()
        subprocess.run([shutil.which('node') or 'node', 'services/worker/ocr_korean.mjs',
                        str(manifest.resolve()), str((target / 'ocr.json').resolve()), mode],
                       cwd=ROOT, check=True, capture_output=True, timeout=120)
        outputs = json.loads((target / 'ocr.json').read_text(encoding='utf-8'))
        details = []
        for row, output in zip(rows, outputs, strict=True):
            truth = normalize(row['text']) if row['legible'] else None
            predicted = normalize(output['text'])
            details.append({'id': row['id'], 'reference_characters': len(truth) if truth else None,
                            'edit_errors': distance(truth, predicted) if truth else None,
                            'confidence': output['confidence']})
        chars = sum(r['reference_characters'] or 0 for r in details)
        errors = sum(r['edit_errors'] or 0 for r in details)
        record = {'variant': name, 'reference_characters': chars, 'edit_errors': errors,
                  'cer': errors / chars if chars else None, 'per_region': details,
                  'elapsed_ms': round((time.perf_counter() - started) * 1000)}
        summary['results'].append(record)
        print(name, errors, '/', chars, flush=True)
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    render_review(annotation, folder)


if __name__ == '__main__':
    main()
