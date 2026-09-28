// Local CPU OCR baseline only. Does not fetch images or send text to any service.
import { createWorker, PSM } from 'tesseract.js';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const [imagePath, outputPath, mode = 'auto', rectangleArg] = process.argv.slice(2);
if (!imagePath || !outputPath || !['auto', 'vertical'].includes(mode)) {
  throw new Error('Usage: node scripts/probe-ocr.mjs <image> <output.json> [auto|vertical]');
}
const modelDir = resolve('models/weights/tesseract');
const model = await readFile(resolve(modelDir, 'jpn_vert.traineddata'));
const digest = createHash('sha256').update(model).digest('hex');
if (digest !== 'bf1e2640954691797e2dc14f38533e601b59ee37958698ae0f0b81dc6f09c71b') {
  throw new Error('Japanese model SHA256 does not match the reviewed model');
}
const begin = performance.now();
let rectangle;
if (rectangleArg) {
  const values = rectangleArg.split(',').map(Number);
  if (values.length !== 4 || values.some(n => !Number.isInteger(n) || n < 0)
      || values[2] === 0 || values[3] === 0) throw new Error('Expected left,top,width,height');
  const [left, top, width, height] = values;
  rectangle = { left, top, width, height };
}
const worker = await createWorker('jpn_vert', 1, {
  langPath: modelDir, gzip: false, cacheMethod: 'none',
});
try {
  await worker.setParameters({
    tessedit_pageseg_mode: mode === 'auto' ? PSM.AUTO : PSM.SINGLE_BLOCK_VERT_TEXT,
    user_defined_dpi: '150',
  });
  const { data } = await worker.recognize(resolve(imagePath), { rectangle }, { text: true, blocks: true });
  const evidence = {
    engine: 'tesseract.js@7.0.0', model: 'tessdata_fast/jpn_vert', model_sha256: digest,
    mode, rectangle: rectangle ?? null,
    region_source: rectangle ? 'MANUAL_REGION' : 'FULL_IMAGE',
    source_sha256: createHash('sha256').update(await readFile(imagePath)).digest('hex'),
    elapsed_ms: Math.round(performance.now() - begin),
    text: data.text, confidence: data.confidence, blocks: data.blocks,
  };
  await writeFile(outputPath, JSON.stringify(evidence, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify({ elapsed_ms: evidence.elapsed_ms, characters: data.text.length }));
} finally {
  await worker.terminate();
}
