# 本地气泡实验模型登记

本轮登记用于 P01 局部研究，不能替代 T009 完整商业授权审查。权重不进入 Git；固定下载 URL、revision 和每个文件 SHA256 见 [清单](bubble-lab.json)。本轮加载不启用远程代码。

| 资源 | 来源与用途 | 当前核查状态 |
|---|---|---|
| RT-DETR-v2 r50vd int8 | [comic-text-and-bubble-detector](https://huggingface.co/ogkalu/comic-text-and-bubble-detector)，文字/气泡统一检测 | 模型卡标 Apache-2.0，描述包含漫画与 webtoon；训练图片权利未独立审计 |
| manga-ocr int8 ONNX | [ogkalu 转换](https://huggingface.co/ogkalu/manga-ocr-onnx)，日文识别 | 转换卡标 Apache-2.0，但说明较少；[原始模型](https://huggingface.co/kha-white/manga-ocr-base) 及原代码同声明，转换完整溯源仍待登记 |
| tessdata_fast kor | [官方固定版本](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd)，韩文识别 | 官方 Apache-2.0；本地校验后加载，无网络模型回退 |
| Tesseract.js 7.0.0 | npm 锁文件固定的本地 WASM OCR | 包内 Apache-2.0；对手写体质量有限 |
| ONNX Runtime / OpenCV / Pillow | CPU 推理、掩膜修复、排版；版本见 uv.lock | ONNX Runtime MIT，OpenCV Apache-2.0，Pillow HPND；分发通知清单仍待完善 |
| Windows 字体 | 本机 `msyh.ttc`、`malgun.ttf` | 仅调用本机已安装字体，不复制字体文件；服务器与产品分发需单独选择/核实字体 |

替代尝试：tessdata_best kor revision `e12c65a915945e4c28e237a9b52bc4a8f39a0cec`，SHA256 `f888d4038348a0c3d25151e7f452bda0d74ca275b18cab146798bcbb94084fff`。下载完整后，本机 Tesseract.js 7.0.0 在浮点模型初始化报缺少 `DotProductSSE`，未纳入最终管线。没有把失败尝试算成准确率改善。

样本与署名详见 [实验报告](../reports/P01-bubble-overlay.md)。当前不分发任何漫画图片、完整识别文本、原始译文或模型权重。
