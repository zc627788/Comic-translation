import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'dist/extension');
const manifest = JSON.parse(fs.readFileSync(path.join(output, 'manifest.json'), 'utf8'));
assert.equal(manifest.manifest_version, 3);
assert.deepEqual(manifest.permissions, ['activeTab', 'scripting', 'sidePanel']);
assert.deepEqual(manifest.host_permissions, ['http://127.0.0.1/*']);
assert.equal(manifest.background.type, 'module');
for (const file of [manifest.background.service_worker, manifest.side_panel.default_path]) {
  assert.ok(fs.existsSync(path.join(output, file)), `Missing extension entry: ${file}`);
}
const html = fs.readFileSync(path.join(output, manifest.side_panel.default_path), 'utf8');
const scripts = [...html.matchAll(/<script[^>]+src="([^"]+)"/g)].map(match => match[1]);
assert.ok(scripts.length > 0, 'No compiled panel script');
assert.ok(!/<script(?![^>]*src=)[^>]*>\s*\S/i.test(html), 'Inline executable code');
for (const source of scripts) {
  assert.ok(!/^https?:/i.test(source), 'Remote extension script');
  assert.ok(fs.existsSync(path.join(output, source)), `Missing panel asset: ${source}`);
}
assert.ok(!manifest.content_scripts, 'No automatic page injection in the foundation build');
process.stdout.write('PASS: MV3 package entries, bundled assets, CSP-compatible scripts, minimal development permissions.\n');
process.stdout.write('Scope: build structure only; not a real-browser extension acceptance test.\n');
