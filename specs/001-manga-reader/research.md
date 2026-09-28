# 研究记录与验证方案

文档编号：D03；版本：0.1；上游：[D02 需求](spec.md)。

## 上一份完整总结

D02 定义 Windows 桌面 Chrome/Edge、日译简中、普通图片页面和三类使用方式，形成 FR-001～FR-036、NFR-001～NFR-010。全站支持、手机端和出版级修复排除在首版外。账户、额度、沙箱支付、安全与交付属于商业版本必需项。模型质量、成本、目标站点、价格和商用授权未确定；上游放行研究设计，不表示功能完成。

## 证据级别

- FACT：本轮读取的一手公开资料支持，但不等于本项目实测。
- ASSUMPTION：用于推进设计的暂定选择，可通过决策记录修改。
- TO_VALIDATE：必须通过实验、用户输入或正式授权材料确认。

查阅日期：2026-09-28。实施时固定版本并复核条款，不能仅依靠本文件中的历史网页说明。

## 已知事实和影响

| 编号 | 类型 | 事实或暂定判断 | 对方案的影响 |
|---|---|---|---|
| R-01 | FACT | Spec Kit 官方描述先原则、需求、计划和任务，再实施与收敛 | 使用常见规格结构，并增加本项目逐阶段交接 |
| R-02 | FACT | 给出的气泡模型卡目前写 YOLO11n 分割、页面标记 Apache-2.0 | 不按旧 YOLOv8 描述锁定实现，核查完整上游 |
| R-03 | FACT | RT-DETR-v2 候选模型有 bubble/text_bubble/text_free 三类 | 先测统一检测，再比较添加分割模型的收益 |
| R-04 | FACT | manga-ocr 针对日文漫画，覆盖横竖排和振假名等场景 | 可作为日文 OCR 基线，不推定对其他语种同等有效 |
| R-05 | FACT | AnimeMangaInpainting 模型卡提供漫画/动画风格 LaMa 权重 | 作为局部背景修复候选，不承诺恢复真实被遮挡细节 |
| R-06 | FACT | Chrome 内容脚本和扩展侧跨域能力不同，后台会休眠 | 图片读取放在授权边界，任务状态必须持久化 |
| R-07 | FACT | 跨域来源可能使网页 Canvas 无法导出像素 | 不能把网页截图/Canvas 当作万能原图获取方案 |
| R-08 | FACT | Ichigo 与 Torii 有收费图片翻译产品 | 证明存在同类供给，不能据此推断利润或我们的付费转化 |
| R-09 | FACT | Chrome 商店要求用途、数据披露与权限相符 | 本地筛选、显式上传、最小权限和隐私说明进入设计 |
| R-10 | TO_VALIDATE | MangaSense 此次公开访问超时 | 没有实测其质量、速度、费用或内部实现 |

## 模型和依赖授权登记

P01 必须把下面候选表扩为实际采用版本的清单，包含 revision、SHA256、下载来源、运行库、基础权重、训练数据声明、许可原文链接、使用条件、分发条件、审查结论和替代方案。

| 组件 | 当前候选 | 公开页面信息 | 尚需确认 |
|---|---|---|---|
| 文本/气泡检测 | ogkalu/comic-text-and-bubble-detector | 模型卡标记 Apache-2.0 | 具体权重和推理实现、训练来源、声明完整性 |
| 气泡分割 | huyvux3005/manga109-segmentation-bubble | 模型卡标记 Apache-2.0；基于 Ultralytics | 与上游授权条件是否相容；不能由标签单方面下法律结论 |
| 日文 OCR | kha-white/manga-ocr-base | 模型卡标记 Apache-2.0 | 运行依赖、版本、模型卡和权重条款一致性 |
| 局部修复 | dreMaz/AnimeMangaInpainting | 模型卡标记 MIT | 权重、上游 LaMa 和数据来源的使用条件 |
| 翻译服务 | 可配置文本大模型接口 | 未选定服务商 | 商用条款、保存策略、区域、限流、价格和内容限制 |
| 字体 | 待选有明确嵌入/分发许可的中文字体 | 未锁定 | 商用和包内分发许可、字形覆盖 |

Ultralytics 官方对 AGPL 与企业授权的说明和候选模型卡标签存在需要核实的上游问题。转换格式、移到后端或单独进程不能自动消除义务。研究测试也要确认其适用权限；不把“待核实”解释为默认有权使用。首发默认链路优先选授权清楚的组件，必要时替换、获得授权或采用兼容的开放策略。

## P01 实验矩阵

| 实验 | 输入与方法 | 必须记录 | 决策出口 |
|---|---|---|---|
| E-01 图片获取 | 自有测试阅读器＋候选真实站点，包含跨域、响应式和懒加载 | 成功率、权限、来源身份、失败类别 | 首发站点能力清单 |
| E-02 文字检测 | 同一批授权图比较统一检测与检测＋气泡分割 | 正文召回、振假名覆盖、背景误检、耗时 | 是否启用第二模型 |
| E-03 OCR | 横竖排、低清、注音、黑底、空白及艺术字 | 字符错误率、空图幻觉、低置信检测能力 | 主 OCR 与补救策略 |
| E-04 翻译 | 同样 OCR 文本，单区与整页上下文比较 | 盲评、术语一致、漏译、输出结构、token 成本 | 翻译适配器与上下文预算 |
| E-05 擦字排版 | 简单背景和复杂背景分层，不混算 | 字迹残留、背景损坏、溢出、最小字号 | 默认模式与降级阈值 |
| E-06 资源成本 | 冷启动/热启动、单页/长图、串行/有限并发 | CPU/GPU/RAM、传输、延迟分位数、失败重试成本 | 服务硬件和处理上限 |
| E-07 Windows 工程 | 固定运行库版本，在 Windows 新环境复现 | 安装步骤、依赖冲突、CPU/GPU 路径 | 可执行工程基线 |

先用约 30 张授权样本验证技术链路，再构建固定 240 张质量集。30 张试验不能替代最终质量集。模型本身没有校准置信度时，使用一致性、空结果和异常字符等规则形成质量标记，不伪造概率。

## 站点选择和样本来源

默认先做自有阅读器夹具，包括双页、滚动长图、异步换源、带广告示例布局和 CDN 图片。选择真实站点需记录 URL、允许测试范围、登录/付费限制、图片呈现方式与失败复现；本轮没有把任何未知站点写成已支持。

用户提供的图片也必须记录其允许用途。开源代码许可与漫画内容许可不同。测试图不默认上传 GitHub；使用允许再分发的合成夹具和脱敏清单，私有样本路径被 Git 忽略。

## 商业假设与验证

假设读者愿为稳定日译中阅读、少漏字、少残留和易纠错付费。先招募 30～50 名符合目标的读者，观测两周实际使用，再以实际付款而非问卷愿望判断。

记录安装→首张成功→读完一章→次周回访→付款的漏斗；分别看重度与轻度用户。10 名付费用户可作为早期继续投入信号，不能代表规模化成立。访谈明确桌面/手机阅读占比。

单位经济性：每页实际成本 = 检测/OCR/修复计算 + 翻译 token + 传输存储 + 重试摊销。固定空闲资源、支付手续费、退款、客服和获客另计。套餐不能根据最便宜的单页案例设计；先测月消耗分布及高分位用户，再确定额度和价格。首版不承诺无限量。

## 一手来源

- [Spec Kit 官方仓库](https://github.com/github/spec-kit)
- [气泡分割候选](https://huggingface.co/huyvux3005/manga109-segmentation-bubble)
- [文本与气泡检测候选](https://huggingface.co/ogkalu/comic-text-and-bubble-detector)
- [Manga OCR](https://huggingface.co/kha-white/manga-ocr-base)
- [漫画风格局部修复](https://huggingface.co/dreMaz/AnimeMangaInpainting)
- [Ultralytics 授权说明](https://www.ultralytics.com/license)
- [Chrome 跨域请求](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests)
- [Chrome 权限声明](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions)
- [Chrome 后台生命周期](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle)
- [MDN 跨域 Canvas](https://developer.mozilla.org/en-US/docs/Web/HTML/How_to/CORS_enabled_image)
- [Chrome 商店数据限制](https://developer.chrome.com/docs/webstore/program-policies/limited-use)
- [Ichigo 订阅](https://ichigo.moe/subscription)
- [Torii 产品](https://toriitranslate.com/)
- [Torii 计费](https://toriitranslate.com/pricing)

## 本份完整总结

- 已确定：公开资料与本地实测分层，模型为候选而非已批准依赖。
- 已交付：E-01～E-07 实验、授权登记要求、样本来源规则、商业验证和成本公式。
- 未完成：所有实验、授权核实、真实站点测试和用户收费验证；网站访问失败不构成负面质量判断。
- 对下游约束：模型/服务采用可替换接口，处理上限与性能由实验校准，未授权组件不能默认商用。
- 下一份输入：候选组件、待验证风险和首版技术范围。
- 结论：可以执行下一步，编写 D04 技术方案；技术选型仍需 P01 实测后收敛。
