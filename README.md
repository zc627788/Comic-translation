# Comic Translation

面向日漫、韩漫中文读者的浏览器翻译插件：选择网页漫画图片，翻译并覆盖原图，支持原图对照、快捷点击和图片导出。

## 当前状态

当前处于 P01：独立实验阅读器已经跑通自动检测、日文/韩文 OCR、免费翻译、擦字、气泡内嵌字和原位替换，可恢复原图、导出 PNG、快捷点击处理。两张真实语言页和一张原创韩文长条有实测，韩文错字和误译仍需改善。浏览器扩展已有开发面板，但尚未接通此流程；计费和生产部署未实现。唯一进度来源是 [阶段状态](docs/progress.md)。

[查看免费接口实验结论](reports/P01-free-api-probe.md) · [实验复现方法](docs/free-api-experiment.md)。图片、权重和原始译文仅保存在本机，不随仓库分发。

新增：[气泡覆盖实测与限制](reports/P01-bubble-overlay.md) · [运行覆盖阅读器](docs/bubble-overlay-experiment.md)。本机实验地址 `http://127.0.0.1:4176/`。

开发环境固定为 Windows / PowerShell；文本文件使用 UTF-8。首发目标为桌面 Chrome / Edge，日语、韩语 → 简体中文。

## 从哪里开始

1. 阅读 [研发路线与交接规则](docs/00-roadmap.md)。
2. 阅读 [项目原则](.specify/memory/constitution.md)。
3. 按 [文档链](docs/00-roadmap.md#文档阅读和编写顺序) 阅读规格；每份文档末尾有完整交接总结和下一步结论。
4. 实施前阅读上一阶段真实总结，再按 [任务清单](specs/001-manga-reader/tasks.md) 开始当前阶段。

## 规格驱动方式

借鉴 [GitHub Spec Kit](https://github.com/github/spec-kit) 的 constitution → specify → plan → tasks → implement → converge 流程，增加逐阶段证据和交接门槛。本仓库本轮未安装 Specify CLI，也不宣称已经执行官方斜杠命令；文档可独立驱动开发，未来可接入官方工具。

## 本地开始

按照 [本地启动说明](docs/development.md) 安装锁定依赖、启动阅读器和 API、构建并加载开发扩展。当前不需要 API 密钥，模型未就绪会明确提示。

```powershell
.\scripts\setup.ps1
.\scripts\check.ps1
npm run fixtures
```

另一终端可运行 `.\scripts\start-api.ps1`。开发插件构建输出为 `dist/extension`，不是可翻译的正式发布包。

## 文档检查

在项目根目录使用 PowerShell 执行 `node scripts/check-docs.mjs`，检查 UTF-8、内部文件链接、需求编号、任务覆盖与文档交接结构。此命令不是软件功能测试。

## 仓库交付

采用 `codex/` 前缀工作分支，完成检查后提交并推送。不得提交密钥、用户漫画、模型大文件或未经允许公开的测试材料。首发是否开源及软件许可证需要在分发前完成决策；不因代码托管在 GitHub 就推定其获得第三方模型的商业授权。
