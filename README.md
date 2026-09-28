# Comic Translation

面向日漫中文读者的浏览器翻译插件：选择网页漫画图片，翻译并覆盖原图，支持原图对照、快捷点击和图片导出。

## 当前状态

当前交付是 v0.1 开发规格，不是可运行产品。尚未实现扩展、推理服务、付款或生产部署。唯一进度来源是 [阶段状态](docs/progress.md)，不得根据文档存在判断功能已经完成。

开发环境固定为 Windows / PowerShell；文本文件使用 UTF-8。首发目标为桌面 Chrome / Edge，日语 → 简体中文。

## 从哪里开始

1. 阅读 [研发路线与交接规则](docs/00-roadmap.md)。
2. 阅读 [项目原则](.specify/memory/constitution.md)。
3. 按 [文档链](docs/00-roadmap.md#文档阅读和编写顺序) 阅读规格；每份文档末尾有完整交接总结和下一步结论。
4. 实施前阅读上一阶段真实总结，再按 [任务清单](specs/001-manga-reader/tasks.md) 开始当前阶段。

## 规格驱动方式

借鉴 [GitHub Spec Kit](https://github.com/github/spec-kit) 的 constitution → specify → plan → tasks → implement → converge 流程，增加逐阶段证据和交接门槛。本仓库本轮未安装 Specify CLI，也不宣称已经执行官方斜杠命令；文档可独立驱动开发，未来可接入官方工具。

## 文档检查

在项目根目录使用 PowerShell 执行 `node scripts/check-docs.mjs`，检查 UTF-8、内部文件链接、需求编号、任务覆盖与文档交接结构。此命令不是软件功能测试。

## 仓库交付

采用 `codex/` 前缀工作分支，完成检查后提交并推送。不得提交密钥、用户漫画、模型大文件或未经允许公开的测试材料。首发是否开源及软件许可证需要在分发前完成决策；不因代码托管在 GitHub 就推定其获得第三方模型的商业授权。
