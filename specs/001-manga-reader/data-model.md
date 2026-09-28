# 数据模型与状态

文档编号：D05；版本：0.1；上游：[D04 技术方案](plan.md)。

## 上一份完整总结

D04 采用轻量扩展、API、持久数据库/队列、推理 worker 和私有对象存储，所有组件尚待 P01 锁定版本。流水线将文字范围、气泡、掩膜、安全区分开，并明确坐标变换、长图合并、上下文和低质量降级。缓存默认用户隔离，计费需事务与幂等，后台休眠后从服务端恢复。上游放行数据建模，没有声称软件已运行。

## 统一约定

- 对外 ID 使用不可预测 UUID；时间 UTC ISO 8601，界面按用户时区显示。
- 金额使用整数最小货币单位＋currency；credits 使用非负整数。不得用浮点累计金额。
- 图像坐标采用解码并校正方向后的原图坐标，左上为原点，x 向右、y 向下，单位 pixel。
- box 为 `[x, y, width, height]`；polygon 为顶点数组；所有坐标满足原图边界。归一化坐标仅作为明确标注的派生值。
- 所有缩放/裁剪/分块记录正逆变换与 tile offset。界面展示变换不反写原图坐标。
- 字符串 UTF-8，原文与展示译文分开保存；不在日志里默认记录文本正文。

## 核心实体

| 实体 | 必要字段 | 约束与用途 |
|---|---|---|
| User | id, status, locale, created_at, deleted_at | 试用身份可升级；停用不得读取任务 |
| Session | id, user_id, token_hash, expires_at, revoked_at | 保存摘要而非明文长期凭据 |
| SitePreference（本地） | origin, enabled, shortcut, scan_policy | 不存全浏览历史；和浏览器真实授权分别核对 |
| ImageCandidate（本地） | local_id, tab_id, frame_id, document_id, element_generation, source_fingerprint, dimensions, selection, reason | 网页图片身份；页内复用节点时 generation 递增 |
| Asset | id, user_id, sha256, kind, width, height, bytes, storage_key, expires_at, deleted_at | 原图/结果/掩膜类别分开；后端解码校验，资源始终用户隔离 |
| Batch | id, user_id, ordered_job_ids, source_order, created_at | 固定提交顺序，不因完成先后变化 |
| Quote | id, user_id, asset_descriptors_hash, options_hash, pricing_version, max_credits, expires_at | 绑定处理参数与预算；过期重新确认 |
| Job | id, user_id, batch_id, asset_id, input_hash, options_hash, quote_id, status, stage, progress_seq, cancel_requested, attempt_count, lease_until | 终态不可由旧事件倒退；状态按版本乐观锁/事务更新 |
| JobOptions | source_language, target_language, mode, glossary_revision, context_hash, pipeline_version, allowed_fallbacks | 运行中不可偷偷改变计费输入 |
| Region | id, job_id, type, reading_order, text_box, bubble_polygon, mask_asset_id, safe_polygon, direction, source_text, translated_text, quality_flags | 检测框与擦字掩膜独立；没有实测概率时 confidence=null |
| ResultRevision | id, job_id, revision, parent_id, asset_id, layout_hash, edit_operations, quality_flags, created_at | 乐观并发；撤销创建可追溯版本或指向明确前版 |
| Glossary | id, user_id, work_label, revision, entries | 作品标记由用户设置；不自动上传整站 URL |
| UsageMetric | job_id, pipeline_version, stage_durations, tokens, gpu_seconds, estimated_cost_minor, cost_currency | 成本可空/估算，标注估算依据；不伪造精确账单 |
| CreditAccount | user_id, available, reserved, version | 数据库事务更新；available/reserved 均不小于 0 |
| CreditEntry | id, user_id, kind, amount, reference_type, reference_id, idempotency_key, created_at | 不可变流水，唯一去重键；修正用补偿分录 |
| CreditLot | id, user_id, source, remaining, reserved, expires_at | 分开试用/订阅/购买额度，确定抵扣顺序与到期行为 |
| PaymentEvent | id, provider, provider_event_id, object_id, status, payload_digest, processed_at | 唯一(provider,event_id)；完整敏感载荷不长期保存 |
| Subscription | id, user_id, provider_id, plan_version, status, period_end, cancel_at_period_end | 不用单一 paid 布尔表示所有订阅状态 |
| DeleteRequest | id, user_id, scope, requested_at, status, completed_at, retention_exceptions | 追踪原图、结果、缓存、文本、备份例外 |
| AuditEvent | id, actor_id, action, resource_id, reason, created_at | 管理修改、退款和查看权限留痕，避免内容正文 |

## Job 状态机

```text
queued -> running -> succeeded
   |         |----> succeeded_with_warnings
   |         |----> failed
   |         |----> cancelled
   +--------------> cancelled
```

`stage` 独立于主状态：validate、detect、ocr、translate、erase、inpaint、typeset、verify、store。当前阶段无可靠百分比则 progress=null。无文字可成为 succeeded_with_warnings，warning=NO_TEXT，费用为零，结果不冒充已翻译。

`cancel_requested` 是请求标志，不是终态。终止前检查发布/结算事务；若成功已先提交，则取消返回 TOO_LATE，结果保持可用。若取消先赢得状态更新，则不发布成功结果且释放预留，后台已发生的供应商成本由服务承担。

重试使用原 job 的 attempt 记录或有显式 parent 的后续 job，始终复用原项计费去重标识；超自动重试上限才允许用户明确重试。重试成功只结算一次。

## 账本不变量

1. 提交事务校验 available >= quoted_max，转入 reserved，并创建 RESERVE 流水。
2. 成功事务校验任务未结算，将实际费用从 reserved 消耗，多余部分返还 available，分别写 CAPTURE/RELEASE。
3. 失败、取消、无文本释放全部预留。重绘/排版编辑沿用成功结果且不消耗新的翻译额度。
4. 批次逐项预留/结算，额度不足时整次提交拒绝并返回新估价；不悄悄只执行一部分。
5. 同一 reference 下每类财务动作唯一，数据库约束与应用校验共同防重。余额由流水可重建并定期对账。
6. 到期额度若正在预留则保持至任务终结；释放时已到期部分记 EXPIRE，不变成新的有效额度。
7. 退款/拒付可回收未用额度。已使用不足以抵扣的部分记应收/限制账户策略，不把 available 变负数或删除旧账。
8. 套餐版本、价格版本和汇率依据固定在交易上，后改套餐不能重写历史。

## 初始保留策略（设计值）

| 数据 | 默认期限 | 用户删除 |
|---|---|---|
| 上传原图与中间掩膜 | 任务结束后最多 24 小时 | 撤销访问立即生效，在线对象 24 小时内清除 |
| 译图与可编辑文本/布局 | 默认 7 天 | 同上；清除后不保证可继续编辑 |
| 本地缓存 | 有界 LRU，最多 7 天且有容量上限 | 设置页可立即清空 |
| 脱敏运行日志 | 默认 14 天 | 不含原图/正文/完整 URL；按运营策略清理 |
| 加密备份中的内容数据 | 最长 30 天轮替 | 删除墓碑保证恢复后再次清理；到期清除 |
| 账户、交易与账本 | 按实际经营地区义务单独确定 | 明示必要保留类别，不声称与内容同时消失 |

这是需求设计而非已执行隐私承诺。P05/P06 根据实际供应商和存储验证，无法兑现时先修改披露与产品设置。签名 URL 需短时有效；撤销后通过权限代理禁止继续签发，无法撤销的既有 URL 剩余 TTL 必须受上限约束并说明。

## 本份完整总结

- 已确定：统一 ID/时间/金额/坐标约定，图片身份与原图内容身份分离，主要实体及约束。
- 已设计：任务终态、取消竞态、结果版本、账本预留/结算/释放、额度到期和删除策略。
- 未完成：数据库迁移、事务实现、运行验证和经营地区账务保留决策。
- 对下游约束：API 必须暴露明确的状态、版本、预算和错误；旧任务不能覆盖新图，重复事件不能重复收费。
- 下一份输入：实体字段、不变量和保留边界。
- 结论：可以执行下一步，编写 D06 接口契约；数据结构仍属于规格。
