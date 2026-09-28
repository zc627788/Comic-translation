# 接口与错误契约

文档编号：D06；版本：0.1；上游：[D05 数据模型](data-model.md)。

## 上一份完整总结

D05 定义用户隔离的资源、固定提交快照、原图坐标、独立区域掩膜、任务终态和结果版本。取消按提交竞态决定，不假称请求即完成；账本预留/结算/释放与到期需事务和去重。在线内容保留期限为待验证设计值，账务另行确定。上游允许接口设计，数据库和支付尚未实现。

## 协议约定

- API 前缀 `/v1`，JSON UTF-8，生产 HTTPS。由后续实现生成 OpenAPI，并在 CI 检查客户端契约一致性。
- 认证为短时访问 token；浏览器授权采用标准登录流程、state 与 PKCE 类防护，具体身份提供方在 P05 确定。页面内容脚本不持有刷新凭据。
- 试用也需要隔离的受限会话，不建立完全匿名、无限可用的推理端点。
- 请求携带 request_id；变更请求携带 Idempotency-Key。相同用户/路由/键/载荷返回原结果，不再次处理；同键不同载荷返回 409。
- 通用错误结构：`{error:{code,message,retryable,request_id,details}}`；details 不返回密钥、内部路径、原始供应商响应或其他用户资源信息。
- 所有列表分页和有界查询；状态事件带 sequence，客户端忽略乱序旧事件。枚举遇到未知值时安全降级，不白屏。

## 图片与估价

| 方法与路径 | 输入 | 输出/行为 |
|---|---|---|
| POST /assets/upload-intents | 声明 MIME、bytes、width、height、sha256 | asset_id、上传目标、5 分钟过期时间、大小限制；尚不可信任声明 |
| PUT 上传目标 | 图片字节 | 受限对象接收，不能改变目标 key 或公共访问属性 |
| POST /assets/{id}/finalize | 上传完成标识 | 校验实际格式/大小/像素/哈希，返回 ready/rejected；未就绪不能创建任务 |
| POST /quotes | ordered_asset_ids、语言、模式、版本、补救策略 | quote_id、逐项标准页与最高额度、total_max_credits、10 分钟有效期、pricing_version |
| POST /batches | quote_id、固定图片顺序与参数、Idempotency-Key | batch_id、jobs、reserved_credits；原子预留后持久任务 |

为避免“先偷偷上传再估价”，界面先按本地已解码尺寸和公开价格表显示估算及上传告知；用户选择提交后才上传，服务端实际校验并生成最终 quote。若最终最大额度不高于用户已确认上限且规则未变，可自动创建批次；否则暂停并请用户确认新报价。价格表来源与版本从服务端取得。

标准页初值：每张图 `max(1, ceil(width*height/2,000,000))`，每张独立取整；快速/精细模式系数待成本实验确定。处理费用不得超过确认的 quote 上限；供应商实际超支由服务承担，或在执行额外处理之前取得新的明确预算。

后端接收图片字节而非替用户抓取任意网页地址。扩展读取层须限制消息来源、站点权限及已发现的资源，不提供通用任意 URL 下载代理。

## 任务与结果

| 方法与路径 | 输入 | 输出/行为 |
|---|---|---|
| GET /batches/{id} | owner session | 固定顺序、各项状态、总预留和结算 |
| GET /jobs/{id} | owner session | 主状态、stage、sequence、attempt、可空进度、费用状态、结果版本 |
| POST /jobs/{id}/cancel | Idempotency-Key | cancel_requested/已终结/TOO_LATE；不能直接伪造 cancelled |
| POST /jobs/{id}/retry | 可重试错误、原项引用 | 复用收费身份；需额外处理参数时重新报价 |
| GET /jobs/{id}/result | revision 可选 | 区域、原尺寸、layout、quality_flags、签名资源地址和到期时间 |
| PATCH /jobs/{id}/layout | base_revision、允许字段操作 | 新 revision；版本不匹配 409，不覆盖他处修改 |
| POST /jobs/{id}/supplements | 用户框选原图坐标、目标动作 | 对新增 OCR/翻译先给报价；原资产过期要求重新提供 |
| POST /exports | 结果 ID/版本、有序列表、PNG/JPEG/ZIP | export_id、状态、资源及下载到期时间 |
| GET /exports/{id} | owner session | 导出进度、文件数、失败/警告清单和有效下载入口 |
| DELETE /jobs/{id}/content | Idempotency-Key | delete_request_id、访问撤销时间和最终清除期限 |

任务轮询初始 1 秒、之后最大 5 秒并加抖动；后台/断网暂停，恢复时重取权威状态。后续可选 SSE，但轮询是必须可用的恢复通路。不得仅靠单条长连接维持全部状态。

首次成功结果至少包含：job_id、revision、original_dimensions、pipeline_version、target_language、regions、rendered_asset、warnings、charged_credits。质量警告为结构化枚举，如 LOW_OCR、OVERFLOW、ART_TEXT_ANNOTATED、SCREENSHOT_LOW_RES、CONTEXT_GAP、NO_TEXT。

编辑只允许白名单文本与布局字段，文本长度有界；输出按纯文本/绘图处理，禁止模型或用户译文作为 HTML 执行。不存在可执行“脚本式编辑指令”。

## 账户与商业接口

| 路径组 | 要求 |
|---|---|
| /auth/*, /me | 登录/注销/续期、受限试用升级，跨账户退出后清除本地旧资源引用 |
| /me/credits, /me/usage | 可用/预留/到期额度、按任务的不可变流水分页 |
| /plans | 服务端套餐版本、价格/币种、税费展示策略、有效期和续费说明 |
| /billing/checkout | 创建服务商托管支付会话；服务器选择允许的套餐，不信任前端金额 |
| /billing/portal | 查看/取消续订等服务商管理入口，校验用户归属 |
| /billing/webhooks/{provider} | 原始体验签、重放窗口、事件去重、必要时查询服务商权威状态 |
| /me/deletion | 创建账户删除任务，区分内容清除与必须保留的账务信息 |
| /admin/* | 管理角色、审计和最小字段；额度调整使用补偿账，不直接改数 |
| /health/live, /health/ready | 分别报告进程存活与依赖/模型准备状态，不泄露配置 |

支付、退款和订阅事件可能乱序，不只以接收时间覆盖最新状态。发放额度使用对应交易/账期唯一键；失败重试不能重复发放。

## 错误和用户出口

| code | 典型 HTTP | 是否可重试 | 用户出口 |
|---|---|---|---|
| PERMISSION_REQUIRED | 插件本地错误 | 授权后 | 启用当前站点或使用手动入口 |
| IMAGE_UNREADABLE | 422 | 有条件 | 重试原图/框选可见区域 |
| UNSUPPORTED_FORMAT / IMAGE_TOO_LARGE | 415 / 413 | 否 | 查看支持格式、分图或换图 |
| INVALID_UPLOAD | 422 | 否 | 重新上传有效文件 |
| AUTH_REQUIRED / SESSION_EXPIRED | 401 | 登录后 | 登录，保留本地未提交选择 |
| RESOURCE_NOT_FOUND | 404 | 否 | 不区分其他用户资源与不存在 |
| QUOTE_EXPIRED / QUOTE_CHANGED | 409 | 重新估价后 | 确认新费用，不自动超额 |
| INSUFFICIENT_CREDITS | 402 | 补额度后 | 减少选择或购买额度 |
| RATE_LIMITED | 429 | 是 | Retry-After，有界退避 |
| PROVIDER_UNAVAILABLE / MODEL_NOT_READY | 503 | 是 | 排队或重试，说明当前不可用 |
| OCR_FAILED / TRANSLATION_INVALID | 422 / 502 | 有界 | 手动修正/重试；最终失败释放额度 |
| REVISION_CONFLICT / IDEMPOTENCY_CONFLICT | 409 | 读取最新后 | 保留编辑并提示冲突 |
| RESULT_EXPIRED | 410 | 重新提交后 | 明确历史内容已过期 |
| TOO_LATE | 409 | 否 | 已完成结果仍可查看 |

## 插件消息契约

允许动作：DISCOVER、CANDIDATES_CHANGED、FETCH_SELECTED_ASSET、SUBMIT_SELECTION、JOB_STATUS、APPLY_RESULT、RESTORE_ORIGINAL、OPEN_EDITOR。每条消息有 schema_version、request_id、document_id、candidate_id/generation。跨页面导航后旧 document_id 的应用消息必须丢弃。

扩展后台校验 sender、当前站点授权和预先登记的候选，不能接受页面伪造的任意 URL、任意结果资源或任意服务地址。扫描和覆盖不需要页面主世界持有登录会话。

## 本份完整总结

- 已确定：上传→校验→报价→任务→结果/编辑/导出的接口顺序，用户确认上限和 quote 有效期。
- 已设计：错误出口、幂等、状态序号、取消竞态、付款回调、跨用户隐藏和插件消息身份。
- 未完成：机器可校验 schema、接口实现、真实支付适配与认证提供方选择。
- 对下游约束：UI 不伪造进度、不先上传后告知、不偷偷加价；所有失败都必须有明确下一操作。
- 下一份输入：状态、错误、费用和版本交互。
- 结论：可以执行下一步，编写 D07 用户体验与页面细节；接口尚未实现。
