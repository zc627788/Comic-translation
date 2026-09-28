import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startFixtureServers } from '../../scripts/serve-fixtures.mjs';

test('fixture server isolates asset origin and never serves repository files', async t => {
  const server = await startFixtureServers({ readerPort: 0, assetPort: 0 });
  t.after(() => server.close());
  const reader = await fetch(server.readerOrigin);
  const html = await reader.text();
  assert.equal(reader.status, 200);
  assert.ok(html.includes(server.assetOrigin));
  assert.ok(!html.includes('__ASSET_ORIGIN__'));
  const image = await fetch(`${server.assetOrigin}/assets/page-one.svg`);
  assert.equal(image.status, 200);
  assert.equal(image.headers.get('access-control-allow-origin'), null);
  assert.match(image.headers.get('content-type'), /image\/svg\+xml/);
  for (const route of ['/package.json', '/.env', '/..%2f..%2f.env', '/assets/missing.svg']) {
    assert.equal((await fetch(`${server.readerOrigin}${route}`)).status, 404);
  }
  assert.equal((await fetch(`${server.assetOrigin}/`)).status, 404);
  assert.equal((await fetch(server.readerOrigin, { method: 'POST', body: 'private' })).status, 405);
});
