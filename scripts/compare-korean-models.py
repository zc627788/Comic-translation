"""Compare local models against a versioned source-checked reference, never feed answers to OCR."""

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

from services.worker.korean_paddle import KoreanPaddleOcr, line_boxes
from services.worker.quality_metrics import distance, normalize

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'artifacts/private'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(reference, outputs, original_seven=False):
    details = []
    for row, output in zip(reference, outputs, strict=True):
        if original_seven and not row['previous_legible']:
            continue
        truth, text = normalize(row['text']), normalize(output['text'])
        details.append({'id': row['id'], 'characters': len(truth),
                        'errors': distance(truth, text),
                        'characters_without_spaces': len(truth.replace(' ', '')),
                        'errors_without_spaces': distance(truth.replace(' ', ''),
                                                         text.replace(' ', ''))})
    chars = sum(r['characters'] for r in details)
    errors = sum(r['errors'] for r in details)
    no_space = sum(r['characters_without_spaces'] for r in details)
    return {'regions': len(details), 'characters': chars, 'errors': errors,
            'cer': errors / chars if chars else None,
            'cer_without_spaces': sum(r['errors_without_spaces'] for r in details) / no_space,
            'per_region': details}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='models-v1')
    args = parser.parse_args()
    if not args.run_id.replace('-', '').isalnum():
        parser.error('Invalid run ID')
    base = PRIVATE / 'korean-model-v2'
    annotation_file = base / 'annotations-v2.json'
    annotation = json.loads(annotation_file.read_text('utf-8'))
    rows = annotation['regions']
    folder = base / args.run_id
    folder.mkdir(exist_ok=False)
    crops = []
    for row in rows:
        source = PRIVATE / 'quality-v1/images' / (row['page'] + '.png')
        if digest(source) != row['image_sha256']:
            raise ValueError('FROZEN_INPUT_CHANGED')
        with Image.open(source) as image:
            crop = image.convert('RGB').crop(row['box'])
        crop.save(folder / (row['id'] + '.png'))
        crops.append(crop)
    start = time.perf_counter()
    model = KoreanPaddleOcr()
    init_ms = round((time.perf_counter() - start) * 1000)
    results, provenance = {}, {}
    timings = {}
    for name, split in [('paddle-v5-whole', False), ('paddle-v5-lines', True)]:
        outputs = []
        start = time.perf_counter()
        for crop in crops:
            outputs.append(model.read(crop, split_lines=split))
        timings[name] = round((time.perf_counter() - start) * 1000)
        results[name] = outputs
    # Same automatic line crops for Tesseract: separate the benefit of splitting from the model.
    files, counts = [], []
    for row, crop in zip(rows, crops, strict=True):
        boxes = line_boxes(crop)
        counts.append(len(boxes))
        for index, box in enumerate(boxes):
            path = folder / f"{row['id']}-line-{index}.png"
            crop.crop(box).save(path)
            files.append(str(path))
    manifest = folder / 'line-files.json'
    manifest.write_text(json.dumps(files), encoding='utf-8')
    start = time.perf_counter()
    subprocess.run([shutil.which('node') or 'node', 'services/worker/ocr_korean.mjs',
                    str(manifest), str(folder / 'tesseract-lines.json')], cwd=ROOT,
                   check=True, capture_output=True, timeout=120)
    timings['tesseract-fast-lines'] = round((time.perf_counter() - start) * 1000)
    line_outputs = json.loads((folder / 'tesseract-lines.json').read_text('utf-8'))
    offset, joined = 0, []
    for count in counts:
        joined.append({'text': ' '.join(x['text'] for x in line_outputs[offset:offset + count])})
        offset += count
    if offset != len(line_outputs):
        raise ValueError('OCR_OUTPUT_COUNT_MISMATCH')
    results['tesseract-fast-lines'] = joined
    old = PRIVATE / 'korean-comparison-v1/comparison-v1'
    for name in ['raw-3x-block', 'raw-1x-block', 'otsu-3x-block', 'raw-3x-sparse']:
        file = old / name / 'ocr.json'
        results['tesseract-' + name] = json.loads(file.read_text('utf-8'))
        provenance[str(file.relative_to(ROOT)).replace('\\', '/')] = digest(file)
    summary = {'annotation_sha256': digest(annotation_file),
               'reference_status': 'official SVG + AI raster check; not human reviewed',
               'run_id': args.run_id, 'model_init_ms': init_ms,
               'timing_scope': 'paddle excludes init; tesseract includes worker init; not SLA',
               'reused_output_sha256': provenance,
               'source_sha256': {name: digest(ROOT / name) for name in [
                   'services/worker/korean_paddle.py', 'scripts/compare-korean-models.py',
                    'services/worker/ocr_korean.mjs',
                    'models/korean-ocr-candidates.json', 'uv.lock']},
               'results': []}
    for name, outputs in results.items():
        record = {'variant': name, 'original_seven': score(rows, outputs, True),
                  'all_eight': score(rows, outputs), 'elapsed_ms': timings.get(name),
                  'reused_previous_outputs': name not in timings}
        summary['results'].append(record)
        print(name, record['all_eight']['errors'], '/',
              record['all_eight']['characters'], flush=True)
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    (folder / 'outputs.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n',
                                       encoding='utf-8')
    sections = []
    for index, row in enumerate(rows):
        note = '已修订或补齐' if row['text'] != row['previous_text'] else '原标注已核对'
        candidates = ''.join(f'<li>{html.escape(name)}：{html.escape(output[index]["text"])}</li>'
                             for name, output in results.items())
        sections.append(f'<section><h2>{row["id"]}</h2>'
                        f'<img src="/model-crops/{row["id"]}.png" alt="原图对白裁图">'
                        f'<p>{note} · <a href="{html.escape(row["source"]["url"])}">官方源</a></p>'
                        f'<p>官方源复核：{html.escape(row["text"])}</p><ul>{candidates}</ul></section>')
    table = '<table><tr><th>配置</th><th>字符错误 / 144</th><th>错误率</th></tr>'
    for record in summary['results']:
        metrics = record['all_eight']
        table += (f'<tr><td>{record["variant"]}</td><td>{metrics["errors"]}</td>'
                  f'<td>{metrics["cer"]:.2%}</td></tr>')
    table += '</table>'
    document = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>新韩文模型 · 官方源复核</title><style>
body{max-width:1100px;margin:40px auto;padding:20px;font:16px 'Microsoft YaHei';background:#f4f6f3}
section{background:white;padding:24px;margin:20px 0;border:1px solid #ddd;border-radius:12px}
img{max-width:100%}p,li{line-height:1.8}td,th{text-align:left;padding:8px 18px}
</style><h1>新韩文模型 · 同图对照</h1>
<p>8 处参考裁图，官方 SVG 文本与原图由 AI 交叉复核，不是人工审核或正式质量集。
分行由图像自动推算，不使用答案。整框结果用于展示文本行模型的使用边界。</p>
<p>Pepper&amp;Carrot / David Revoy；韩译 Shikamaru “initbar” Yamamoto；校对 Jihoon Kim；
第一话另有 GunChleoc / Hồ Châu。CC BY 4.0；仅裁图缩放，未翻译。
<a href='https://www.peppercarrot.com/kr/webcomics/peppercarrot.html'>原作</a> ·
<a href='https://www.peppercarrot.com/kr/about/index.html'>许可</a></p>
""" + table + ''.join(sections) + '</html>'
    (folder / 'review.html').write_text(document, encoding='utf-8')


if __name__ == '__main__':
    main()
