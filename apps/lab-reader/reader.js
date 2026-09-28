const $ = id => document.getElementById(id);
const results = new Map();
let samples = [], busy = false, autoApply = false;
const reasonLabels = {OPEN_BUBBLE_BOUNDARY:'气泡边界未闭合', LOW_OCR_CONFIDENCE:'识别置信度不足',
  TRANSLATION_NEEDS_REVIEW:'翻译结果需要核对', TEXT_DOES_NOT_FIT:'译文无法安全放入气泡',
  LOCAL_BUDGET_EXCEEDED:'本地免费实验字符限额已用完'};
function selected() { return samples.find(s => s.id === $('sample').value); }
function show(mode) {
  const sample = selected(), job = results.get(sample.id);
  if (mode !== 'original' && !job) return;
  $('comic').src = mode === 'original' ? `/samples/${sample.id}/original` :
    `/results/${job.id}/${mode === 'detection' ? 'detection' : 'translated'}.png`;
  $('view').textContent = {original:'原图', translated:'中文覆盖 · 机器译文待核对', detection:'绿色：气泡 / 橙色：文字'}[mode];
}
function describe(job) {
  const result = job?.result;
  $('regions').replaceChildren();
  if (!result) { $('regions').textContent = '处理后显示真实结果。'; return; }
  $('metrics').textContent = `已覆盖 ${result.covered} 个气泡 · 保留 ${result.preserved} 个\n` +
    `处理 ${(result.elapsed_ms / 1000).toFixed(1)} 秒 · ${result.tiles.length} 个切片\n` +
    `安全区外改动 ${result.outside_safe_modified_pixels} 像素`;
  for (const r of result.regions) {
    const el = document.createElement('div'); el.className = 'region';
    for (const text of [`气泡 ${r.id + 1} · ${r.status === 'covered' ? '已覆盖 / 待核对' : '保留原文：' + (reasonLabels[r.reason] || r.reason)}`,
      r.source && `识别：${r.source}`, r.translation && `译文：${r.translation}`,
      r.ocr_confidence != null && `OCR 置信度 ${r.ocr_confidence}（不代表实际准确率）`,
      r.cached != null && (r.cached ? '复用之前真实接口结果' : '本次真实接口请求')].filter(Boolean)) {
      const p = document.createElement('p'); p.textContent = text; el.append(p);
    }
    $('regions').append(el);
  }
}
function refresh() {
  const sample = selected(), job = results.get(sample.id);
  $('credit').textContent = sample.credit;
  $('source').hidden = !sample.source;
  if (sample.source) $('source').href = sample.source;
  $('translated').disabled = $('detection').disabled = !job;
  $('download').hidden = !job;
  if (job) $('download').href = `/results/${job.id}/translated.png`;
  $('process').disabled = busy || !sample.available;
  $('metrics').textContent = ''; describe(job);
}
async function run() {
  if (busy || !selected()?.available) return;
  const sampleId = selected().id; busy = true; autoApply = true;
  $('status').textContent = '正在提交处理…';
  document.querySelector('.paper').classList.add('processing'); refresh();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 240000);
  try {
    let response = await fetch('/api/jobs', {method:'POST', signal:controller.signal,
      headers:{'Content-Type':'application/json', 'X-Comic-Lab':'1'},
      body:JSON.stringify({sample_id:sampleId, allow_translation:true})});
    let job = await response.json();
    if (!response.ok) throw new Error(job.detail || '提交失败');
    while (job.state === 'running') {
      $('status').textContent = job.message;
      await new Promise(resolve => setTimeout(resolve, 700));
      response = await fetch(`/api/jobs/${job.id}`, {signal:controller.signal});
      if (!response.ok) throw new Error('无法读取处理状态');
      job = await response.json();
    }
    if (job.state !== 'complete') throw new Error(reasonLabels[job.message] || job.message);
    results.set(sampleId, job);
    $('status').textContent = `处理完成：覆盖 ${job.result.covered} 个，保留 ${job.result.preserved} 个。请核对译文。`;
    refresh();
    if (autoApply && selected().id === sampleId) show('translated');
  } catch (error) {
    $('status').textContent = error.name === 'AbortError' ? '等待超时，本地任务可能仍在处理；原图可继续阅读。' : `处理未完成：${error.message}`;
  } finally {
    clearTimeout(timeout); busy = false;
    document.querySelector('.paper').classList.remove('processing'); refresh();
  }
}
$('sample').addEventListener('change', () => {
  autoApply = false; refresh(); show('original');
  if (!busy) {
    const result = results.get(selected().id)?.result;
    $('status').textContent = result ? `此页已处理：覆盖 ${result.covered} 个，保留 ${result.preserved} 个。` :
      (selected().available ? '准备就绪，可以开始处理此页。' : '该样本尚未准备，请先按说明准备图片。');
  }
});
$('process').addEventListener('click', run);
$('original').addEventListener('click', () => { autoApply = false; show('original'); });
$('translated').addEventListener('click', () => show('translated'));
$('detection').addEventListener('click', () => show('detection'));
$('comic').addEventListener('click', event => {
  if (event.button === 0 && event.ctrlKey && event.shiftKey) { event.preventDefault(); run(); }
});
try {
  const response = await fetch('/api/samples');
  if (!response.ok) throw new Error('样本服务不可用');
  samples = await response.json();
  for (const sample of samples) {
    const option = document.createElement('option'); option.value = sample.id;
    option.textContent = sample.title + (sample.available ? '' : '（尚未准备）');
    $('sample').append(option);
  }
  refresh(); show('original'); $('status').textContent = '准备就绪。处理完成后会直接替换本页图片。';
} catch (error) { $('status').textContent = error.message; $('process').disabled = true; }
