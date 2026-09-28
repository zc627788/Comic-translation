# 免费翻译实验复现

先读 [实验总结与下一步判断](../reports/P01-free-api-probe.md)。这是 P01 开发工具；主 API 的完整流水线仍返回未就绪，扩展尚不提供自动翻译。系统为 Windows，终端使用 PowerShell，所有文本 UTF-8。

## 直接看本机结果

本机已保存真实结果。项目根目录运行：

```powershell
.venv\Scripts\python.exe -m scripts.serve-probe
```

浏览器打开 `http://127.0.0.1:4175/`。绿色框表示人工提供的区域，不是自动检测。对照页是既有请求的记录，查看页面不会再发送文字给翻译服务。关闭预览终端即可停止本地服务。若端口已被当前预览占用，直接打开页面，不必重复启动。

## 新环境准备

先运行 `scripts/setup.ps1` 安装仓库依赖。模型和漫画不会随 Git 分发，需要按来源单独准备：

1. 从 [官方日文第 1 卷](https://www.densho810.com/free/dl/001bj.zip) 获取样本，先阅读 [适用条款](https://www.densho810.com/free/)。约 328 MiB 压缩包，解出的 PDF 约 338 MiB；保存在 `artifacts/private/free-api-probe/volume-1.pdf`。不要导入其他未经允许的漫画，也不要公开衍生图片。
2. 从 [固定版本的日文竖排模型](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/jpn_vert.traineddata) 下载到 `models/weights/tesseract/jpn_vert.traineddata`。其 [Apache-2.0 许可](https://github.com/tesseract-ocr/tessdata_fast/blob/87416418657359cb625c412a48b6e1d6d41c29bd/LICENSE) 与 SHA256 见实验报告；识别脚本会拒绝不匹配权重。
3. 使用已有 Poppler 的 `pdftoppm.exe` 把 PDF 第 4、6、7 页按最长边 1400 像素渲染为 PNG，名称分别为 `page-004.png`、`page-006.png`、`page-007.png`。本机 bundled Poppler 路径由运行环境提供，不把个人机器路径固定进产品。示例命令如下，将变量换为实际安装位置。

```powershell
& $pdfToPpm -f 4 -l 7 -scale-to 1400 -png artifacts/private/free-api-probe/volume-1.pdf artifacts/private/free-api-probe/page
```

第 5 页没有对白，不属于三张对白样本。原作的页码、哈希、分辨率必须一致，手动区域才能复现。可用 `Get-FileHash -Algorithm SHA256` 检查；本脚本不提供任意网站抓取或绕过付费阅读。

## 识别与翻译分开运行

整页识别不会外发文字；每张图可单独运行。手动区域格式是 `left,top,width,height`，必须诚实保留为人工框选。

```powershell
node scripts/probe-ocr.mjs artifacts/private/free-api-probe/page-007.png artifacts/private/free-api-probe/page-007-ocr.json
node scripts/probe-ocr.mjs artifacts/private/free-api-probe/page-007.png artifacts/private/free-api-probe/page-007-bubble-ocr.json vertical 715,705,125,180
```

本次另两个手动区域：第 4 页 `545,165,265,520`；第 6 页 `426,1040,58,114`。后者实际漏掉了气泡内的人名，保留失败而不是手工补齐。可查看 OCR JSON 的 `rectangle`、`region_source` 和 `source_sha256`。

在同一私有目录建立 `manifest.json`，最小示例：

```json
[
  {
    "image": "page-007.png",
    "ocr": "page-007-bubble-ocr.json",
    "label": "手动框选对照 · 第 7 页",
    "preprocessing": "人工框选；文字由 OCR 自动识别",
    "review": "尚未人工核对"
  }
]
```

先离线生成页面；缺少缓存的文本会显示 NETWORK_NOT_AUTHORIZED，不冒充成功：

```powershell
.venv\Scripts\python.exe -m scripts.probe-free-translation artifacts/private/free-api-probe/manifest.json
```

确实需要调用 MyMemory 时加 `--allow-network`。这将向该服务发送清单内的 OCR 文字，不发送图片。只允许本地有权测试的文本；私密内容的外发和生产保存政策未批准。本工具没有密钥、邮箱增额、付款、自动转收费或写入翻译记忆库功能。

```powershell
.venv\Scripts\python.exe -m scripts.probe-free-translation artifacts/private/free-api-probe/manifest.json --allow-network
```

单次串行会话最多 1,000 字符，失败请求也计入本地上限；每段最多 450 UTF-8 字节。上限不是服务商日额度，多个程序进程不会共享此计数。命中缓存会明确标示，记录的是原网络请求耗时。正式服务需要账户级限流与额度账本，不能直接公开此实验脚本。

## 验证与交接

运行 `scripts/check.ps1` 做离线回归，不需要也不会调用外部翻译接口。模拟响应只用于测试错误处理，真实质量看私有结果和人工核对记录。用户关闭本地预览后，图片与 JSON 仍保存在被 Git 忽略的目录；按项目数据治理要求处理。

本份总结：已有可复现的本地实验入口，清楚区分空白图、整页失败和人工框选对照。**可以继续 P01 的漫画专用检测/OCR 对照；不可以据此进入 P02 或声称扩展覆盖完成。**
