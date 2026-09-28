import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Candidate = { index: number; width: number; height: number; loaded: boolean };
type Scan = { images: Candidate[]; truncated: boolean };

// executeScript serializes this function: keep it independent of external bindings.
function inspectImages(): Scan {
  const images = Array.from(document.images);
  return {
    images: images.slice(0, 200).map((image, index) => ({
      index: index + 1,
      width: image.naturalWidth,
      height: image.naturalHeight,
      loaded: image.complete && image.naturalWidth > 0,
    })),
    truncated: images.length > 200,
  };
}

function App() {
  const [scan, setScan] = useState<Scan | null>(null);
  const [scanning, setScanning] = useState(false);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState('点击浏览器工具栏中的插件图标后，可以扫描当前页。');
  const [service, setService] = useState('尚未检查');

  async function scanPage() {
    setScanning(true);
    setScan(null);
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id === undefined) throw new Error('No active tab');
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, func: inspectImages,
      });
      const result = results[0]?.result;
      if (!result) throw new Error('No scan result');
      setScan(result);
      setMessage(`发现 ${result.images.length} 张图片。只读取尺寸，未上传图片内容。`);
    } catch {
      setMessage('此页暂时无法扫描。请切换到普通网页，再点击工具栏插件图标后重试。');
    } finally {
      setScanning(false);
    }
  }

  async function checkService() {
    setChecking(true);
    try {
      const response = await fetch('http://127.0.0.1:8765/health/live', {
        signal: AbortSignal.timeout(3000), cache: 'no-store', credentials: 'omit',
      });
      const body: unknown = await response.json();
      if (!response.ok || typeof body !== 'object' || body === null
        || !('service' in body) || body.service !== 'comic-translation-api'
        || !('status' in body) || body.status !== 'alive') throw new Error('Invalid health');
      setService('本地服务已启动；翻译模型尚未接入。');
    } catch {
      setService('未连接到本地服务。请先运行后端启动脚本。');
    } finally {
      setChecking(false);
    }
  }

  return <main>
    <header><span className="badge">P01 · 开发验证</span><h1>漫画翻译</h1>
      <p>先验证图片读取与本地服务连接。</p></header>
    <section aria-labelledby="scan-title">
      <h2 id="scan-title">当前页面</h2>
      <p>扫描只在你的浏览器中进行。本版本不读取图片像素，也不会上传图片或调用付费服务。</p>
      <button onClick={() => void scanPage()} disabled={scanning}>
        {scanning ? '正在扫描…' : '扫描当前页图片'}
      </button>
      <p role="status">{message}</p>
      {scan && <><ol className="images">{scan.images.map(image => <li key={image.index}>
        <span>图片 {image.index}</span><span>{image.loaded ? `${image.width} × ${image.height}` : '尚未加载或读取失败'}</span>
      </li>)}</ol>{scan.truncated && <p>本次最多列出 200 张图片。</p>}</>}
    </section>
    <section aria-labelledby="service-title">
      <h2 id="service-title">本地处理服务</h2>
      <button className="secondary" onClick={() => void checkService()} disabled={checking}>
        {checking ? '正在检查…' : '检查服务连接'}
      </button>
      <p role="status">{service}</p>
    </section>
    <section className="notice"><h2>翻译尚未开放</h2>
      <p>文字识别、擦字和翻译将在模型验证后接入。目前没有翻译结果，也不会扣除额度。</p>
      <button disabled>模型接入后可翻译</button>
    </section>
  </main>;
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<App />);
