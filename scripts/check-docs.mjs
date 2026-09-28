import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const errors = [];
const markdownFiles = [];
const textFiles = [];
const decoder = new TextDecoder('utf-8', { fatal: true });

function collect(relative) {
  const absolute = path.join(root, relative);
  if (!fs.existsSync(absolute)) return;
  const stat = fs.lstatSync(absolute);
  if (stat.isSymbolicLink()) {
    errors.push(`Unexpected symbolic link in documentation: ${relative}`);
    return;
  }
  if (stat.isDirectory()) {
    for (const name of fs.readdirSync(absolute)) collect(path.join(relative, name));
  } else {
    textFiles.push(relative);
    if (relative.endsWith('.md')) markdownFiles.push(relative);
  }
}

for (const target of ['README.md', 'AGENTS.md', '.gitattributes', '.editorconfig',
  '.gitignore', '.specify', 'docs', 'specs', 'reports', 'scripts']) collect(target);

const contents = new Map();
for (const file of textFiles) {
  try {
    const text = decoder.decode(fs.readFileSync(path.join(root, file)));
    contents.set(file.split(path.sep).join('/'), text);
    if (text.includes('\uFFFD')) errors.push(`Replacement character found: ${file}`);
    if (!text.endsWith('\n')) errors.push(`Missing final newline: ${file}`);
  } catch (error) {
    errors.push(`Cannot decode UTF-8: ${file}: ${error.message}`);
  }
}

for (const file of markdownFiles) {
  const text = contents.get(file.split(path.sep).join('/')) ?? '';
  for (const match of text.matchAll(/\[[^\]\n]*\]\(([^)\n]+)\)/g)) {
    const target = match[1].trim().replace(/^<|>$/g, '');
    if (/^[a-z][a-z0-9+.-]*:/i.test(target) || target.startsWith('#')) continue;
    const filename = decodeURIComponent(target.split('#')[0]);
    const resolved = path.resolve(root, path.dirname(file), filename);
    const relative = path.relative(root, resolved);
    if (relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
      errors.push(`Link escapes repository: ${file} -> ${target}`);
    } else if (!fs.existsSync(resolved)) {
      errors.push(`Broken file link: ${file} -> ${target}`);
    }
  }
}

const mainDocs = [
  'docs/00-roadmap.md', '.specify/memory/constitution.md',
  ...['spec', 'research', 'plan', 'data-model', 'contracts', 'ux', 'acceptance', 'tasks', 'release']
    .map(name => `specs/001-manga-reader/${name}.md`),
];
for (const [index, file] of mainDocs.entries()) {
  const text = contents.get(file);
  if (!text) { errors.push(`Missing primary document: ${file}`); continue; }
  if (index > 0 && !text.includes('## 上一份完整总结')) {
    errors.push(`Missing incoming handoff: ${file}`);
  }
  if (!text.includes('## 本份完整总结') || !text.includes('可以执行下一步')) {
    errors.push(`Missing outgoing handoff/verdict: ${file}`);
  }
  if (index > 0) {
    const expected = `D${String(index).padStart(2, '0')}`;
    if (!text.includes(`文档编号：${expected}`)) errors.push(`Document ID mismatch: ${file}`);
  }
}

const base = 'specs/001-manga-reader/';
const spec = contents.get(`${base}spec.md`) ?? '';
const tasks = contents.get(`${base}tasks.md`) ?? '';
const acceptance = contents.get(`${base}acceptance.md`) ?? '';
const progress = contents.get('docs/progress.md') ?? '';
const fr = [...spec.matchAll(/\*\*(FR-\d{3})（/g)].map(match => match[1]);
const nfr = [...spec.matchAll(/^\| (NFR-\d{3}) \|/gm)].map(match => match[1]);
const taskDefs = [...tasks.matchAll(/^- \[([ x])\] (T\d{3}) /gm)];
const ac = [...acceptance.matchAll(/^\| (AC-\d{2}) \|/gm)].map(match => match[1]);

function checkSequence(values, prefix, count, width) {
  if (new Set(values).size !== values.length) errors.push(`Duplicate definitions: ${prefix}`);
  const expected = Array.from({ length: count }, (_, index) =>
    `${prefix}${String(index + 1).padStart(width, '0')}`);
  for (const value of expected) if (!values.includes(value)) errors.push(`Missing definition: ${value}`);
  for (const value of values) if (!expected.includes(value)) errors.push(`Unexpected definition: ${value}`);
}
checkSequence(fr, 'FR-', 36, 3);
checkSequence(nfr, 'NFR-', 10, 3);
checkSequence(taskDefs.map(match => match[2]), 'T', 48, 3);
checkSequence(ac, 'AC-', 21, 2);

const knownTasks = new Set(taskDefs.map(match => match[2]));
const knownAc = new Set(ac);
for (const id of [...fr, ...nfr]) {
  const rows = tasks.split('\n').filter(line => line.startsWith(`| ${id} |`));
  if (rows.length !== 1) { errors.push(`Expected one traceability row: ${id}`); continue; }
  const ids = rows[0].match(/T\d{3}/g) ?? [];
  if (!ids.length || ids.some(task => !knownTasks.has(task))) errors.push(`Invalid task mapping: ${id}`);
  const checks = rows[0].match(/AC-\d{2}/g) ?? [];
  if ((id.startsWith('FR-') && !checks.length) || checks.some(item => !knownAc.has(item))) {
    errors.push(`Invalid acceptance mapping: ${id}`);
  }
}

for (const section of tasks.split(/^## (?=P\d{2} )/m).slice(1)) {
  const phase = section.slice(0, 3);
  const state = progress.split('\n').find(line => line.startsWith(`| ${phase} `));
  if (!state) errors.push(`Missing phase state: ${phase}`);
  if (state?.includes('| NOT_STARTED |') && /^- \[x\] T\d{3}/m.test(section)) {
    errors.push(`Completed task inside NOT_STARTED phase: ${phase}`);
  }
}

if (errors.length) {
  for (const error of errors) process.stderr.write(`FAIL: ${error}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`PASS: ${textFiles.length} UTF-8 text files; ${markdownFiles.length} Markdown files; internal file links valid.\n`);
  process.stdout.write(`PASS: ${mainDocs.length} chained primary documents; 36 FR + 10 NFR; 48 tasks; 21 acceptance cases; complete traceability.\n`);
  process.stdout.write('Scope: documentation consistency only. No product, model, payment or deployment tests were run.\n');
}
