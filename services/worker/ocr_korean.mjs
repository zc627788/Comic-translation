import { createWorker, PSM } from 'tesseract.js';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';

const [manifestPath, outputPath, mode = 'block'] = process.argv.slice(2);
if (!['block', 'sparse'].includes(mode)) throw new Error('INVALID_OCR_MODE');
const files = JSON.parse(await readFile(manifestPath, 'utf8'));
const modelDir = resolve('models/weights/tesseract');
const hash = createHash('sha256').update(await readFile(resolve(modelDir, 'kor.traineddata'))).digest('hex');
if (hash !== '6b85e11d9bbf07863b97b3523b1b112844c43e713df8b66418a081fd1060b3b2') {
  throw new Error('MODEL_HASH_MISMATCH');
}
const worker = await createWorker('kor', 1, {langPath: modelDir, gzip: false, cacheMethod: 'none'});
try {
  await worker.setParameters({tessedit_pageseg_mode: mode === 'block' ? PSM.SINGLE_BLOCK : PSM.SPARSE_TEXT,
    user_defined_dpi: '150'});
  const results = [];
  for (const file of files) {
    const {data} = await worker.recognize(file);
    results.push({text: data.text.replace(/\s+/g, ' ').trim(), confidence: data.confidence});
  }
  await writeFile(outputPath, JSON.stringify(results, null, 2), 'utf8');
} finally { await worker.terminate(); }
