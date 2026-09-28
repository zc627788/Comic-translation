import { build } from 'vite';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const extension = path.join(root, 'apps/extension');
const outDir = path.join(root, 'dist/extension');

await build({
  configFile: false,
  root: extension,
  base: './',
  build: {
    outDir, emptyOutDir: true, target: 'chrome116',
    rollupOptions: { input: path.join(extension, 'sidepanel.html') },
  },
});
await build({
  configFile: false,
  root: extension,
  publicDir: false,
  build: {
    outDir, emptyOutDir: false, target: 'chrome116',
    lib: {
      entry: path.join(extension, 'src/background.ts'),
      formats: ['es'], fileName: () => 'background.js',
    },
  },
});
