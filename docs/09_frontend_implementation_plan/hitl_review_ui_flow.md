# 人工审核 HITL 前端流程实施计划

## 1. 目标

本计划把人工审核（Human-in-the-loop，HITL）从待办进入、证据复核、风险处置到案件级决定和交付预览收敛为可实施的前端页面、路由、组件、字段、权限和 API 依赖设计。

范围覆盖：

- 人工队列/待办浏览与接收；
- 当前有效文档版本、审核运行、审核基线和证据包展示；
- `approve`、`edit`、`reject`、`request_supplement`、`transfer`、`escalate`、`accept_risk` 等动作；
- 决定确认、风险接受授权、交付预览和审计回执；
- 并发冲突、版本/运行失效、证据缺失、权限变化、异议和更正路径。

本阶段只产出规划文档，不实现前端代码，不实现后端 API，不直接调用 LangGraph `interrupt`、checkpoint 或内部 `thread_id`。

## 2. 输入与现状检查

### 2.1 输入文档

1. `docs/08_api_spec/api_spec-v1.0.md`：人工队列、待办、统一决定入口、异议、交付快照和错误语义。
2. `docs/06_system_architecture/frontend_design_spec-v1.0.md`：P1/P3/P5/P6/P7 页面层级、状态表达和跳转约束。
3. `docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md`：服务端权威性、前端发起/后端裁决、最小可见性和版本不可覆盖边界。
4. `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`：HITL 暂停/恢复边界、版本失效和 checkpoint 不向前端暴露的原则。
5. `docs/04_core_interaction_flows/human_approval_state_flow.md`：人工动作、责任转移、证据包、审计、异议和交付状态规则。

### 2.2 当前实现状态

- `backend/` 当前仅包含 `.gitkeep`，无可运行 API、鉴权、队列、审计或交付服务。
- 下文所有 API 依赖均标记为 **未开发**。接口已在 API 规范中定义，不代表当前可调用。
- 在后端实现前，前端只能完成静态原型、类型/契约准备和错误态设计；不得声称已完成联调、真实队列接收或真实批准。

## 3. 结论与总体流程

HITL 前端以“案件 + 当前文档版本 + 审核运行 + 审核基线 + 人工待办责任”的组合上下文为唯一工作边界。页面负责读取服务端投影、收集人工明确输入、展示确认和提交结果；后端负责权限、责任、证据完整性、版本一致性、状态转换、审计和业务恢复。

```text
队列列表 → 待办详情/接收 → 证据包复核 → 风险项处置
                          ├─ 编辑/确认/误报/accept_risk
                          ├─ 要求补件
                          ├─ 转交/升级
                          └─ 案件级决定
                               → 决定确认与交付预览
                               → approved / rejected / changes_requested / 新责任队列
```

`approved` 只表示有权限人员基于当前有效上下文作出案件级同意；不由 Agent 完成、空风险项、解析成功、前端按钮可见或 `ready_for_delivery` 推断。交付由后端在 `approved` 后生成不可变 `DeliverySnapshot`，前端只能查询预览和结果。

## 4. 路由与页面层级

### 4.1 路由表

| 路由 | 页面 | 主要角色 | 进入条件 | 关键离开路径 |
|---|---|---|---|---|
| `/review/queues/:queueId` | 人工队列/待办列表 | `reviewer`、`expert`、`approver`、授权 `operator` | 具备队列读取权限 | 进入待办详情或返回案件 |
| `/cases/:caseId/assignments/:assignmentId` | 待办详情与接收 | 同上 | 待办仍属于当前案件且未被替代 | 接收后进入工作台；失效时回队列并刷新 |
| `/cases/:caseId/review/:assignmentId` | 人工审核工作台 | 当前责任人或授权接管者 | 已接收/进行中的待办 | 打开决定确认、转交/升级、补件表单 |
| `/cases/:caseId/review/:assignmentId/findings/:findingId` | 风险项证据抽屉/详情 | 有证据包读取权的审核者 | finding 属于同一有效运行 | 返回工作台，提交风险项动作 |
| `/cases/:caseId/review/:assignmentId/decision` | 决定确认与交付预览 | 具备该动作权限的责任人 | 表单通过前端完整性检查 | 成功回案件详情/工作台；冲突留在确认页 |
| `/cases/:caseId/objections/new` | 提交者异议 | `submitter` | 可见的决定/交付存在且主体有权异议 | 提交后回案件详情，显示处理中 |
| `/cases/:caseId/deliveries/:deliveryId` | 交付快照查看 | 有效收件主体 | 交付快照已由后端创建 | 查看更正/替代关系或提交异议 |

案件详情 P3、风险结果 P5 可通过按钮进入上述路由；它们不得以跳转替代状态变更。

### 4.2 页面树

```text
人工审核域
├── 队列列表
│   ├── 筛选/排序/分页
│   ├── 待办行
│   └── 空、无权限、加载失败、过期提示
├── 待办详情
│   ├── 责任与版本三元组
│   ├── 接收确认
│   └── 证据包入口
├── 审核工作台
│   ├── 案件/版本/运行/基线上下文栏
│   ├── 风险项列表
│   ├── 原文定位与证据面板
│   ├── 历史决定与审计时间线
│   ├── 责任操作（转交/升级）
│   └── 案件级处置栏
├── 决定确认与交付预览
│   ├── 动作摘要与影响范围
│   ├── 必填理由/依据/授权
│   ├── 提交者可见预览
│   └── 并发/版本检查结果
└── 提交者异议与交付查看
```

## 5. 组件职责与字段展示

### 5.1 队列列表页

组件：`ReviewQueueHeader`、`AssignmentFilters`、`AssignmentTable`、`AssignmentRow`、`QueueStatusBadge`、`PaginationCursor`、`QueueEmptyState`、`PermissionDeniedState`。

每条待办至少展示：`assignment_id`（可折叠显示）、`case_id/case_reference`、合同类型、当前 `document_version_id`/版本号、`audit_run_id`、`baseline_version_id`、最高严重度、风险计数、路由原因、优先级、等待时长、当前责任显示、`assignment_status`、最近更新时间。

筛选只作为查询参数，不在前端重新计算严重度或责任：队列状态（`queued`/`accepted`/`in_progress`）、严重度、路由原因、合同类型、责任队列和时间范围。未知枚举保留原值并降级为“待确认”。

### 5.2 待办详情与接收

组件：`AssignmentContextCard`、`ResponsibilityCard`、`VersionValidityBanner`、`AllowedActionsPanel`、`AcceptAssignmentButton`、`StaleAssignmentGuard`。

展示字段：`assignment_status`、队列、当前责任、目标/升级队列（如已存在）、原因、期限、`expected_revision`、版本/运行/基线三元组、案件状态、证据包入口、服务端计算的 `allowed_actions`。

接收按钮仅在 `allowed_actions` 包含接收且当前状态允许时显示；点击后必须二次确认“接收不等于批准”。请求携带服务端最新 `expected_revision` 和客户端生成的 `idempotency_key`。成功以服务端返回的责任和新 revision 更新页面；失败不得乐观显示为已接收。

### 5.3 人工审核工作台

组件：`ReviewContextHeader`、`CaseSummaryPanel`、`DocumentVersionPanel`、`AuditRunPanel`、`RoutingReasonPanel`、`FindingList`、`FindingRow`、`EvidenceViewer`、`RuleAuthorityPanel`、`DecisionHistory`、`AuditTimeline`、`ResponsibilityActions`、`CaseDecisionBar`。

上下文栏固定显示：案件标识/合同类型/审核范围、当前文档版本和父版本关系、当前审核运行、审核基线、案件状态、责任人、更新时间和只读/替代标识。版本、运行或基线不匹配时显示阻断横幅，并禁用案件级最终动作。

风险项行展示：`finding_id`、类别、标题、严重度、置信度、处置状态、人工复核要求、红线标记、定位状态、建议动作、既有决定摘要。证据面板展示授权的 `quote`、`context_excerpt`、章节路径、页码/坐标（如有）、`locator_status`、`content_hash`、关联 `RuleHit`、`FindingExplanation`、`AuthorityReference` 和历史差异。定位 `unavailable`/`stale` 时明确标为“证据不足/定位失效”，不绘制伪造跳转。

风险项支持：确认/编辑、误报（通过 `edit` 的处置状态表达）、要求补件、转交、升级、风险接受。每个动作打开结构化表单，保存动作前展示当前风险项、引用证据和前后值；原始 Agent 结果、原文和规则基线只读。

案件级操作区提供同意、驳回、要求补件、转交、升级；按钮可见性仅由 `allowed_actions` 辅助，最终仍由后端裁决。`accept_risk` 不得出现在案件级批准按钮旁作为“批准替代”。

### 5.4 决定确认与交付预览

组件：`DecisionSummary`、`ContextIntegrityCheck`、`ReasonEditor`、`EvidenceReferencePicker`、`AuthorizationReferenceField`、`SupplementItemsEditor`、`HandoffTargetSelector`、`SubmitterDeliveryPreview`、`IrreversibleActionWarning`、`DecisionSubmitResult`。

确认内容按动作动态呈现：

| 动作 | 必填前端字段 | 预览重点 |
|---|---|---|
| `approve` | 案件级理由、条件（可选）、`authorization_ref`（如需）和引用风险/证据 | 当前版本/运行、已处置与未处置项、提交者可见结果与限制；未满足条件时阻断 |
| `edit` | `before_value`、`after_value`、改判理由、风险/证据引用 | 风险项状态和交付说明变化；原始候选保持只读 |
| `reject` | 驳回范围、理由、关联风险/规则、提交者后续说明 | 对外可见驳回文案，不展示内部笔记 |
| `request_supplement` | 材料/修改项、目的、关联风险、优先级/期限（如适用） | `changes_requested`、补件清单、新版本重审说明 |
| `transfer` | 目标主体/队列、原因、`handoff_question` | 原责任结束/新待办待接收，失败时原责任保持 |
| `escalate` | 目标升级层级/队列、原因、`handoff_question`、紧急程度（如适用） | 升级原因和等待更高权限处理；不显示不必要人员信息 |
| `accept_risk` | 风险项、`authorization_ref`、理由、证据引用 | 仅该风险变为 `accepted_with_authorization`，案件仍需其他条件 |

提交前显示不可逆提醒：决定追加写入审计，不覆盖旧决定；已交付结果不能原地修改；新材料/基线变化将创建新版本或新运行。

### 5.5 提交者异议与交付预览

提交者可在交付页或案件详情选择“提出异议”。`ObjectionForm` 字段：异议类型、作用范围、风险项选择、陈述、支持材料版本引用。提交前明确：异议不会直接改变 `approved`/`rejected`/`delivered`，后端会创建新的人工待办；新增材料必须走补件/上传新版本链路。

交付页只展示后端过滤后的 `visible_result`、`visible_conditions`、`next_actions`、交付时间、对应版本/运行/基线和更正/替代关系，不展示内部决定理由、隐藏风险、Agent 轨迹或内部人员讨论。

## 6. API 依赖清单（当前均未开发）

| 前端能力 | API 契约 | 使用方式 | 状态 |
|---|---|---|---|
| 队列列表 | `GET /api/v1/review-queues/{queue_id}/assignments?status=&cursor=` | 列表、筛选、分页 | **未开发** |
| 待办详情 | `GET /api/v1/cases/{case_id}/assignments/{assignment_id}` | 上下文、`expected_revision`、`allowed_actions` | **未开发** |
| 案件概览/时间线 | `GET /api/v1/cases/{case_id}`；`GET /api/v1/cases/{case_id}/timeline` | 返回工作台和决定后的状态/审计摘要 | **未开发** |
| 运行/风险/证据 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}`；`/result`；`/findings`；`/findings/{finding_id}`；`/locators/{locator_id}` | 证据包、有效性、风险处置 | **未开发** |
| 材料与补件 | `GET /api/v1/cases/{case_id}/document-versions/{document_version_id}`；`/material-requests` | 补件原因、版本关系、质量/异常摘要 | **未开发** |
| 接收待办 | `POST /api/v1/cases/{case_id}/assignments/{assignment_id}/accept` | 带 `expected_revision`、`idempotency_key` | **未开发** |
| 统一人工决定 | `POST /api/v1/cases/{case_id}/assignments/{assignment_id}/decisions` | 承接七类核心动作及 `withdraw/correct` | **未开发** |
| 提交者异议 | `POST /api/v1/cases/{case_id}/objections` | 创建异议并路由新人工待办 | **未开发** |
| 交付快照 | `GET /api/v1/cases/{case_id}/deliveries/{delivery_id}` | 查看可见交付结果 | **未开发** |
| 创建交付 | `POST /api/v1/cases/{case_id}/deliveries` | 前端不得调用；后端内部动作 | **未开发（前端不提供按钮）** |

前端必须保留每个请求的 `request_id`，并按统一错误 envelope 处理 `revision_conflict`、`assignment_already_taken`、`run_superseded`、`stale_human_task`、`evidence_incomplete`、`action_not_allowed`、`idempotency_conflict` 等错误。客户端不得按 HTTP 状态自行推断可重试性，只有 `error.retryable=true` 才可提示重试。

## 7. 权限、可见性与动作矩阵

| 角色 | 可见范围 | HITL 动作 | 明确限制 |
|---|---|---|---|
| `submitter` | 本人授权案件、补件、异议、过滤后的交付 | 查看状态、补件、提交异议 | 不得进入人工队列、查看内部证据/笔记、编辑决定或批准 |
| `reviewer` | 授权队列、案件、完整复核证据包 | 接收、编辑/确认、误报、补件、驳回/同意（授权范围内）、转交、升级 | 不得越过风险接受授权或版本校验 |
| `expert`/`approver` | 其授权范围及升级事项 | 风险接受、最终同意/驳回、转交/升级、退回 | 不得改写历史或绕过新版本重审 |
| `policy_owner` | 后续审核基线管理范围 | 不作为案件审批入口 | 不得替代案件审批或改写已完成运行 |
| `operator`/`admin` | 队列和异常运营范围 | 运营查看/分配（以 `allowed_actions` 为准） | 管理权限不等于专业批准权限 |

页面隐藏按钮仅改善体验，不构成授权。所有敏感字段由后端按角色过滤；前端不得利用字段数量、`null`、错误差异或本地缓存推断隐藏信息。

## 8. 关键交互与异常处理

### 8.1 并发冲突

所有写操作携带 `expected_revision` 和幂等键。收到 `revision_conflict`、`assignment_already_taken` 或 `idempotency_conflict` 时：

1. 停止当前提交按钮和乐观成功提示；
2. 保留用户未提交表单为本地草稿，但标记为旧上下文；
3. 重新查询待办详情、案件、运行、风险和责任；
4. 展示差异（责任、风险状态、版本/revision）并要求用户重新确认；
5. 不自动重放可能改变业务状态的决定。

### 8.2 版本、基线或运行失效

收到 `run_superseded`、`stale_human_task` 或当前对象 `is_read_only=true` 时，立即禁用最终动作，显示“当前审核上下文已失效，请查看新版本/新运行”。旧表单不得提交到新上下文；引导回案件详情或新待办。旧版本、旧运行和旧决定只读展示。

### 8.3 证据不完整或定位失效

`evidence_incomplete`、定位状态 `unavailable/stale`、解析质量异常时，风险项显示“待确认/证据不足”；案件级同意和交付预览的确认按钮阻断。可执行下一步仅限服务端允许的补件、转交或升级，不由前端自行判断是否可放行。

### 8.4 权限变化和责任转移

若 `allowed_actions` 变化、责任人被转交或会话过期，刷新权限上下文并撤销本地可提交状态。当前用户只能查看其仍获授权的内容；转交/升级失败必须显示原责任保持，不得把案件置于“无责任”。

### 8.5 失败、重试和重复提交

按钮提交期间显示进行中状态，使用同一幂等键重试；只在服务端返回成功 envelope 后更新状态。失败响应展示安全化 `message`、可行动 `details` 和 `request_id`；不展示内部堆栈、提示词、密钥、对象存储地址或安全引擎细节。

## 9. 关键决策

1. 以 P6/P7 为人工审核核心页面，P1/P3/P5 只提供入口和授权后摘要，避免在多个页面复制审批规则。
2. 以 `allowed_actions`、当前责任和版本三元组驱动 UI；前端不复制后端的风险判定、审批额度或状态转换规则。
3. 所有动作统一进入决定确认流程，使用同一个 API 入口；`accept_risk` 只作用于风险项，不能表现为案件批准。
4. HITL 恢复由后端内部完成；前端只提交业务决定，不接触 `thread_id`、checkpoint 或 `Command(resume=...)`。
5. 交付预览是提交者可见性检查，不是“直接交付”操作；前端不调用创建交付接口。
6. 旧版本、旧运行、旧证据和旧决定只读保留；补件、原文变化或基线变化均导航至新版本/新运行。

## 10. 风险与待解决事项

| 风险 | 影响 | 计划约束/缓解 |
|---|---|---|
| backend 当前为空 | 无法真实联调、鉴权或验证队列状态 | 所有接口标记“未开发”；先做契约、静态态和错误态，不伪造成功 |
| `allowed_actions` 与页面缓存不同步 | 可能出现越权按钮或误导性操作 | 进入页、提交前和错误后重新读取；按钮仅作辅助门控 |
| 中断恢复从节点开头重执行 | 可能重复待办、通知和写入 | 前端只使用幂等键；后端实现阶段必须做副作用去重 |
| 多人并发编辑同一风险项 | 决定覆盖或责任不清 | 强制 revision 校验、差异确认和人工重审 |
| 证据/原文包含敏感信息 | 泄露法务材料或内部策略 | 最小可见性、后端字段过滤、前端不缓存跨案件数据 |
| 审批额度/会签/通知 SLA 未定义 | 最终动作 UI 可能不完整 | 暂不假设自动会签、自动提醒或默认审批额度，待业务规则明确 |
| LangChain SDK 版本未实时核验 | 误把实现细节写入前端契约 | 前端只依赖业务 API；SDK 实施前按官方文档重新核验 |

## 11. 下一阶段交付物

1. 后端实现计划：落实队列查询、责任锁、统一决定入口、版本/revision 校验、审计追加和交付快照。
2. 前端实现阶段：按本计划建立路由、组件和状态类型，先覆盖加载/无权限/错误/过期/并发态，再接真实 API。
3. API 联调测试：覆盖成功、权限拒绝、重复请求、责任被占用、版本失效、证据不足、异议、新版本重审和交付只读场景。
4. 权限与业务规则补充：审批额度、多人会签、补件 SLA、升级层级、异议处理时限和交付更正通知。
5. 视觉与可访问性验收：确保严重度、阻断原因、只读历史和提交者可见范围有清晰且不误导的表达。

## 12. 自检记录

- [x] 仅新增本文件，未修改 `frontend/`、`backend/` 或其他文档。
- [x] 已覆盖队列/待办、证据包、责任、七类人工动作、确认、并发冲突、版本失效、异议和交付预览。
- [x] 已说明页面层级、路由、组件职责、字段展示、权限和 API 依赖。
- [x] 所有后端接口均显式标记“未开发”；创建交付接口明确为前端不提供按钮。
- [x] 未伪造后端实现、Mock 成功结果或 LangGraph 内部调用。
