# DocAuditAgent 数据模型汇总规范 v1.0

## 1. 目标、范围与规范地位

本文件汇总 `docs/07_data_model/` 的三份独立数据模型主题规范，作为后续前端、后端、API、持久化和测试设计的共同输入。它不替代来源规范中的字段级定义，不新增业务规则或实现方案；发生字段级疑义时，以第 2 节指定的来源规范为准。

本阶段仅产出规范文档，不包含前端或后端可执行代码、数据库 DDL、ORM、API 路由或密钥配置。

## 2. 输入与主题所有权

| 主题 | 权威来源 | 覆盖的模型边界 |
| --- | --- | --- |
| 上传、材料准入、解析与处理状态 | [`upload_and_task_models.md`](../07_data_model/upload_and_task_models.md) | `audit_case`（上传所需字段）、`upload_batch`、`document_version`、`file_asset`、`upload_session`、`parse_task`、`parse_attempt`、`parse_result`、`parse_quality_assessment`、`status_event`、`material_request`。 |
| 审核规则、命中、解释、结果与原文定位 | [`audit_rule_hit_result_model_spec-v1.0.md`](../07_data_model/audit_rule_hit_result_model_spec-v1.0.md) | `AuditRule`、`RuleEvaluation`、`RuleHit`、`AuditFinding`、`FindingExplanation`、`SourceLocator`、`AuthorityReference`、`AuditResult`。 |
| 人工队列、决定、异议、审计与交付 | [`human_interaction_decision_models.md`](../07_data_model/human_interaction_decision_models.md) | `ReviewQueue`、`ReviewAssignment`、`ResponsibilitySnapshot`、`HumanDecision`、`DecisionEffect`、`SubmitterObjection`、`AuditEvent`、`DeliverySnapshot`。 |

所有模型的字段、含义、类型/约束、前端必须展示和后端必须存储标记均在对应主题来源中完整定义。本文件只提供跨主题可实施的统一关系与交接规则。

## 3. 统一术语与标识映射

| 统一术语 | 来源中的写法 | 规范结论 |
| --- | --- | --- |
| 审核案件 | `audit_case`、`AuditCase`、`Case` | 同一案件生命周期容器，统一以 `case_id`/`audit_case_id` 的 API 语义引用；具体载体主键由后端保持一致。 |
| 文档版本 | `document_version`、`DocumentVersion` | 同一不可变审核材料版本，统一引用为 `document_version_id`。 |
| 审核运行 | `audit_run_id`、`review_run_id` | 同一固定审核执行上下文。后续 API 和持久化规范统一采用 `audit_run_id`；人工交互来源中的 `review_run_id` 映射为该字段，不得建立第二个独立运行对象。 |
| 审核基线 | `baseline_id`、`baseline_version_id` | 同一版本化规则/策略快照。后续 API 统一采用 `baseline_version_id`，其中值为规则主题的 `baseline_id` 所指版本。 |
| 风险项 | `AuditFinding`、`risk_item` | `AuditFinding.finding_id` 是人工模型 `risk_item_id` 的权威引用；不复制风险项事实。 |
| 原文定位 | `SourceLocator`、原文/证据引用 | `SourceLocator.locator_id` 是所有人工决定 `evidence_refs` 中定位引用的权威 ID。 |
| 人工决定 | `HumanDecision`、人工处置 | 追加式决定记录，不能以修改 `AuditFinding`、`RuleHit` 或案件终态字段替代。 |

## 4. 跨主题实体关系

```text
AuditCase
  └─< DocumentVersion ─< FileAsset
        └─< ParseTask ─< ParseAttempt
              └─ ParseResult ─ ParseQualityAssessment

AuditCase + DocumentVersion + BaselineVersion
  └─ AuditRun
       ├─< RuleEvaluation ─< RuleHit ─< SourceLocator
       ├─< AuditFinding >─< RuleHit
       └─ AuditResult

AuditCase + DocumentVersion + AuditRun + BaselineVersion
  ├─< ReviewAssignment ─< ResponsibilitySnapshot
  ├─< HumanDecision ─ DecisionEffect
  ├─< SubmitterObjection
  ├─< AuditEvent
  └─< DeliverySnapshot
```

关系必须满足以下跨主题约束：

1. `AuditRun` 必须固定关联一个 `document_version_id` 和一个 `baseline_version_id`；任何命中、风险项、结果、待办、决定、异议和交付快照均不得跨越该三元上下文。
2. `document_version`、文件材料、解析输出、命中、候选风险、决定和审计事件均保留历史。文本、材料或基线变化必须创建新版本或新运行，不能覆盖旧事实。
3. `AuditFinding.rule_hit_ids` 只能引用同一 `audit_run_id` 的命中；`locator_ids` 只能引用该运行文档版本中的 `SourceLocator`。
4. 人工决定通过 `evidence_refs` 引用风险项、定位、规则和授权，不复制或改写原始 Agent 候选、规则命中和原文证据。
5. `DeliverySnapshot` 只能引用已由有效人工 `approve` 决定支持的当前上下文；自动处理完成、空命中或 `AuditResult.ready_for_delivery` 都不等同于 `approved`。

## 5. 前端必展示信息

前端仅展示服务端按权限过滤后返回的字段，且不得以本地推断代替权威状态。具体字段清单以三份来源的“前端必须展示”列为准；页面和 API 至少覆盖以下信息组：

| 场景 | 必须获得并展示的字段组 | 主要来源 |
| --- | --- | --- |
| 案件与上传 | 案件引用、当前文档版本和版本关系、材料角色/名称/大小、上传与准入状态、安全化原因、补件待办、处理时间与下一步。 | 上传与任务模型 |
| 解析与状态 | 当前解析任务状态、解析质量结论、可行动失败/人工处理说明、版本/状态时间线。 | 上传与任务模型 |
| 审核风险与证据 | 审核版本/运行/基线、风险标题/类别/严重度/置信度/处置状态、规则/依据、解释、限制条件、原文摘录、定位可靠性与可用的页码/章节/坐标。 | 规则与结果模型 |
| 人工工作台 | 队列/责任、路由原因、优先级/期限、当前可执行动作、证据包、历史决定与差异、并发冲突后的当前上下文。 | 人机交互模型 |
| 提交者交付与异议 | 授权后的交付结果、条件、下一步、补件要求、异议状态与可见的处理结果。 | 人机交互模型 |

前端不得展示对象存储引用、下载签名、原始安全检测细节、内部模型轨迹、隐藏提示、未授权人员信息或未授权规则依据。未知枚举值必须降级为待确认状态，不能推断为成功、无风险或已批准。

## 6. 后端必存与权威写入

后端必须持久化各主题来源中标记“后端必须存储”的所有字段，并将下列事实视为不可仅依赖日志、缓存或工作流 checkpoint 的权威记录：

| 事实类别 | 最小权威记录 |
| --- | --- |
| 材料与处理 | 案件/版本关联、文件身份与哈希、受控存储引用、准入结论、上传批次/会话、解析任务及尝试、解析结果与质量、补件与追加式状态事件。 |
| 审核事实 | 固定的运行-版本-基线关联、适用规则评估、规则命中、候选风险、解释、依据、原文定位、结果汇总及其限制。 |
| 人工治理 | 队列和当前责任、决定时授权快照、追加式人工决定、当前处置投影、提交者异议、不可变审计事件与交付快照。 |

每次会改变权威业务状态的写入，后端必须原子校验权限、案件状态、当前责任、`document_version_id`、`audit_run_id`、`baseline_version_id`、乐观并发版本和幂等键，并同时保存对应的状态/处置投影及审计事件。前端不得直接创建或更新解析结果、规则评估、命中、风险候选、定位、决定效果或案件终态。

## 7. 状态、版本与审批边界

| 对象层级 | 权威状态语义 | 禁止的推断 |
| --- | --- | --- |
| 上传/解析 | 文件准入、文档版本和解析任务状态说明材料及处理是否可继续；`ready` 只表示可进入下一阶段。 | `ready`、解析成功或任务完成不表示审核通过。 |
| 规则/结果 | 规则评估、命中、风险项和 `AuditResult` 表达候选审核事实与交付准备。 | 空命中、评估失败或 `ready_for_delivery` 不表示无风险或 `approved`。 |
| 人工处置 | 待办状态表示责任生命周期；`HumanDecision` 追加记录动作；`DecisionEffect` 是当前投影。 | 待办被接收、单个风险已处置或风险接受不表示案件已批准。 |
| 案件交付 | 只有有效、授权的案件级 `approve` 决定后，案件可到 `approved`；通过可见性和完整性校验后才可建立/交付 `DeliverySnapshot`。 | 任何自动化状态或前端本地状态不得直接改变案件终态。 |

版本或基线变化、补件重提、运行失效和交付后更正均通过新增版本、运行、待办、决定或交付快照表达。旧记录只读保留，并由替代/失效关系连接历史。

## 8. 后续实现交接

| 后续工作 | 必须承接的规范输入 |
| --- | --- |
| API 契约 | 统一 ID/三元上下文映射、读模型字段、按角色过滤、写入前置校验、幂等/并发错误、历史查询和安全化失败原因。 |
| 后端持久化 | 来源模型的字段、外键和唯一性约束；追加式记录、当前投影、版本不可覆盖、原子状态与审计写入。 |
| 前端实现 | 第 5 节信息组及来源字段责任；服务端权威状态、未知枚举降级、版本/运行提示、不可直接编辑原始审核事实。 |
| 测试 | 上传与解析失败、质量不足、版本替换、空命中/评估未决、定位失效、人工决定并发、权限失效、异议路由、交付更正和字段级可见性。 |

## 9. 关键风险与待决事项

| 风险 | 后续阶段需要明确的内容 |
| --- | --- |
| 规则与基线治理 | 规则 DSL、基线发布/弃用、适用性与置信度阈值的版本化治理。 |
| 权限与授权 | 审批额度、合同类型/风险等级矩阵、授权失效和多人会签。 |
| 证据与数据保留 | 定位坐标和文本标准化、敏感证据脱敏、审计防篡改、保留期与导出控制。 |
| 并发与恢复 | 乐观锁错误契约、幂等键有效期、事务边界、工作流恢复和重复投递处理。 |
| 对外交付 | 异议是否影响已交付结论、交付更正通知和提交者可见性策略。 |

## 10. 阶段验收记录

- 已汇总三份独立主题规范，且每份均定义模型字段、含义、关系、前端展示责任与后端存储责任。
- 已建立案件、文档版本、审核运行、审核基线、风险项与人工决定的统一术语映射。
- 已明确自动审核、人工批准和对外交付三层语义不可互相替代。
- 本阶段未生成前后端代码；实现必须在后续 API、持久化和前端阶段遵循本规范及其主题来源。
