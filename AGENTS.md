# 项目执行规则

- 系统一直是 Windows；使用 PowerShell，所有文本必须 UTF-8。
- 开始工作先读 `docs/progress.md`、`.specify/memory/constitution.md` 和当前阶段依赖的总结。
- 用户要求按规格逐步落实。每阶段必须有真实结果、验证证据、遗留问题和明确的“可以执行下一步”或“不可以执行下一步”。
- `docs/00-roadmap.md` 定义阶段顺序；`specs/001-manga-reader/tasks.md` 定义任务。不得跨过阻塞项宣称完成。
- 未开始阶段的总结必须标记 NOT_STARTED；计划、示例和模拟结果不作为验收证据。
- 已授权的日常实施、验证、提交及向配置远端推送，不重复索取许可。需要账户、真实支付配置或其他缺失信息时，先完成不依赖该信息的工作。
- 不未经请求部署到付费环境、消耗未知额度或发布扩展商店。Git 推送与生产上线是不同动作。
- 不添加密钥、用户浏览数据、未授权图片或模型权重到 Git。对外只发布脱敏证据。
- 需求变更先更新规格与决策记录，再修改实现和验证；未完成任务不能为了发布而直接删除。
- 不以静态译文、假进度或模拟成功响应冒充真实 OCR、翻译、擦字或导出完成。

<!-- VIBESKILLS:BEGIN managed-block host=codex block=global-vibe-bootstrap version=1 hash=086d84c4c12f190c -->
If the user explicitly invokes `$vibe` or `/vibe`, enter canonical `vibe` before normal execution.
Do not silently continue in ordinary mode first.
If canonical `vibe` cannot be loaded, report blocked instead of falling back silently.
This file is a bootstrap entry surface only; runtime authority remains canonical `vibe`.
Reading this bootstrap block alone is not proof of canonical vibe entry.
Do not preflight-scan the current workspace or repository for canonical proof files before launch.
Canonical launch must run first; only after canonical-entry returns a session root may you validate proof artifacts inside that session root.
Canonical claims require `host-launch-receipt.json`, `runtime-input-packet.json`, `governance-capsule.json`, and `stage-lineage.json` under the launched session root.
<!-- VIBESKILLS:END managed-block -->
