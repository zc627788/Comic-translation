import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../tests/fixtures/reader');
const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/reader.css', ['reader.css', 'text/css; charset=utf-8']],
  ['/reader.js', ['reader.js', 'text/javascript; charset=utf-8']],
  ...['page-one', 'page-two', 'long-page', 'ad', 'icon'].map(name =>
    [`/assets/${name}.svg`, [`assets/${name}.svg`, 'image/svg+xml; charset=utf-8']]),
]);

async function listen(server, port) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => { server.removeListener('error', reject); resolve(); });
  });
  return `http://127.0.0.1:${server.address().port}`;
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.closeAllConnections();
    server.close(error => error ? reject(error) : resolve());
  });
}

export async function startFixtureServers({ readerPort = 4173, assetPort = 4174 } = {}) {
  let assetOrigin = '';
  function createHandler(assetsOnly) {
    return async (request, response) => {
      response.setHeader('X-Content-Type-Options', 'nosniff');
      response.setHeader('Cache-Control', 'no-store');
      if (!['GET', 'HEAD'].includes(request.method)) {
        response.writeHead(405, { Allow: 'GET, HEAD' }); response.end(); return;
      }
      // Exact allowlist: never resolve a user-controlled URL into a filesystem path.
      const urlPath = request.url?.split('?')[0];
      const entry = files.get(urlPath);
      if (!entry || (assetsOnly && !urlPath.startsWith('/assets/'))) {
        response.writeHead(404); response.end('Fixture not found'); return;
      }
      try {
        let data = await fs.readFile(path.join(directory, entry[0]), 'utf8');
        if (urlPath === '/') data = data.replaceAll('__ASSET_ORIGIN__', assetOrigin);
        response.writeHead(200, { 'Content-Type': entry[1] });
        response.end(request.method === 'HEAD' ? undefined : data);
      } catch {
        response.writeHead(500); response.end('Fixture unavailable');
      }
    };
  }
  const assetServer = http.createServer(createHandler(true));
  const readerServer = http.createServer(createHandler(false));
  assetOrigin = await listen(assetServer, assetPort);
  let readerOrigin;
  try { readerOrigin = await listen(readerServer, readerPort); }
  catch (error) { await close(assetServer); throw error; }
  return {
    readerOrigin, assetOrigin,
    close: async () => { await Promise.all([close(readerServer), close(assetServer)]); },
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const fixture = await startFixtureServers();
  process.stdout.write(`Reader: ${fixture.readerOrigin}\nCross-origin assets: ${fixture.assetOrigin}\n`);
  process.stdout.write('Local fixtures only. No uploads, model calls, or paid services. Ctrl+C to stop.\n');
  let closing = false;
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => {
    if (closing) return;
    closing = true;
    await fixture.close();
  });
}
