"""Explicit six-image live translation probe after the frozen polarity regression passes."""

import argparse
import hashlib
import html
import json
from pathlib import Path

from services.worker.bubble_pipeline import OUTPUT, BubblePipeline

ROOT = Path(__file__).resolve().parents[1]
IDS = ['ko-pc-ep01-1', 'ko-pc-ep01-2', 'ko-pc-ep03-1',
       'fx-ko-plain', 'fx-ko-small', 'fx-ko-seam']


def read(path):
    return json.loads(path.read_text('utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-network', action='store_true')
    args = parser.parse_args()
    if not args.allow_network:
        parser.error('Real translation requires explicit --allow-network')
    corpus = ROOT / 'artifacts/private/quality-v1'
    regression = read(corpus / 'runs/paddle-polarity-v1/summary.json')
    rows = regression['results']
    if len(rows) != 30 or not all(r['state'] == 'completed' for r in rows):
        raise ValueError('REGRESSION_INCOMPLETE')
    if not regression['translation_cache_unchanged']:
        raise ValueError('REGRESSION_CACHE_CHANGED')
    dark = next(r for r in rows if r['id'] == 'fx-ko-dark')
    if dark['gold_metrics']['edit_errors'] != 0:
        raise ValueError('DARK_REGRESSION_NOT_FIXED')
    # Before spending the existing budget, require every other diagnostic text to be unchanged.
    for row in rows:
        if row['id'] == 'fx-ko-dark':
            continue
        old = read(corpus / 'runs/paddle-auto-v1' / row['id'] / 'baseline.json')
        new = read(corpus / 'runs/paddle-polarity-v1' / row['id'] / 'baseline.json')
        if [r['text'] for r in old['diagnostics']['regions']] != [
                r['text'] for r in new['diagnostics']['regions']]:
            raise ValueError('NON_DARK_DIAGNOSTICS_CHANGED')
    samples = {r['id']: r for r in read(corpus / 'manifest.json')['samples']}
    folder = ROOT / 'artifacts/private/paddle-live-v1'
    folder.mkdir(exist_ok=False)
    cache = OUTPUT / 'translation-cache.json'
    before = read(cache)
    pipeline = BubblePipeline(allow_network=True, korean_ocr='paddle-v5', output_root=folder)
    results, sections = [], []
    for sid in IDS:
        source = corpus / samples[sid]['path']
        if hashlib.sha256(source.read_bytes()).hexdigest() != samples[sid]['sha256']:
            raise ValueError('FROZEN_INPUT_CHANGED')
        result = pipeline.process(source, sid, 'ko')
        results.append({key: result[key] for key in [
            'sample_id', 'source_sha256', 'covered', 'preserved', 'elapsed_ms',
            'outside_safe_modified_pixels', 'modified_pixels']})
        results[-1]['regions'] = [{key: r[key] for key in [
            'id', 'status', 'reason', 'cached', 'translation_ms', 'quality', 'render'] if key in r}
            for r in result['regions']]
        items = ''.join(f'<li>{html.escape(r.get("source", ""))} → '
                        f'{html.escape(r.get("translation", r.get("reason", "")))}</li>'
                        for r in result['regions'])
        sections.append(f'<section><h2>{sid}</h2><p>覆盖 {result["covered"]}；'
                        f'保留 {result["preserved"]}。机器译文未人工审核。</p>'
                        f'<div><img src="/live/{sid}/original.png" alt="原图">'
                        f'<img src="/live/{sid}/translated.png" alt="真实翻译结果"></div>'
                        f'<details><summary>逐区域识别、译文及失败</summary><ul>{items}</ul>'
                        '</details></section>')
        print(sid, result['covered'], result['preserved'], flush=True)
    after = read(cache)
    summary = {'provider': 'MyMemory', 'global_attempted_character_cap': 1000,
               'before_attempted_characters': before['attempted_characters'],
               'after_attempted_characters': after['attempted_characters'],
               'new_attempted_characters': after['attempted_characters'] -
                                           before['attempted_characters'],
               'new_successful_cache_entries': len(set(after['entries']) - set(before['entries'])),
               'results': results,
               'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in ['scripts/run-live-paddle.py',
                                              'services/worker/korean_paddle.py',
                                              'services/worker/bubble_pipeline.py']}}
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    document = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>真实翻译覆盖验证</title>
<style>body{max-width:1200px;margin:auto;padding:24px;font:16px 'Microsoft YaHei';
background:#f4f6f3}
section{background:white;padding:20px;margin:24px 0}section div{display:grid;
grid-template-columns:1fr 1fr;gap:12px}img{width:100%}p,li{line-height:1.8}</style>
<h1>六图真实翻译覆盖验证</h1><p>实际调用 MyMemory，失败保留原图；不是人工校对后的成品。</p>
<p>Pepper&amp;Carrot / David Revoy；韩译 Shikamaru “initbar” Yamamoto；校对 Jihoon Kim；
第一话另有 GunChleoc / Hồ Châu。CC BY 4.0；含机器中文替换。
<a href='https://www.peppercarrot.com/kr/webcomics/peppercarrot.html'>原作</a> ·
<a href='https://www.peppercarrot.com/kr/about/index.html'>许可</a>。其余为项目原创测试图。</p>
""" + ''.join(sections) + '</html>'
    (folder / 'review.html').write_text(document, encoding='utf-8')


if __name__ == '__main__':
    main()
