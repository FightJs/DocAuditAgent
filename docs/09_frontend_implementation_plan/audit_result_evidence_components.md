# 审核结果与证据组件实施设计

## 1. 目标

本文件定义前端对审核结果、规则评估、规则命中、风险发现、解释、原文定位、依据引用和结果汇总的展示组件与页面层级，作为 P5「风险结果与原文证据查看」、P6「人工审核工作台」、P7「人工决定确认与交付预览」的实现输入。

设计目标：

1. 让用户能区分“规则是否执行”“规则是否命中”“风险是否已处置”和“案件是否获批”。
2. 将每条 `AuditFinding` 绑定到可核验的 `SourceLocator`、`AuthorityReference` 与人可读解释；证据缺失或失效时明确降级，不制造可点击的假定位。
3. 同时支持提交者的授权结果视图和审核者的完整证据包视图；前端不代替后端作权限、质量、适用性或批准判断。
4. 保留文档版本、审核运行、审核基线和 `revision` 上下文，避免把历史结果误当作当前结论。

## 2. 输入

- `docs/08_api_spec/api_spec-v1.0.md`：结果、风险项、定位、人工决定查询接口、权限过滤、并发和错误语义。
- `docs/06_system_architecture/frontend_design_spec-v1.0.md`：P3/P5/P6/P7 页面结构、角色可见性与状态表达。
- `docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md`：服务端权威、最小可见性、前端只发起动作的边界。
- `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`：质量不足、低置信度、无证据、规则冲突进入人工路径的约束。
- `docs/07_data_model/audit_rule_hit_result_model_spec-v1.0.md`：`RuleEvaluation`、`Finding`、`FindingExplanation`、`Suggestion`、`Locator`、`AuditResult` 及其状态和字段。
- `docs/07_data_model/upload_and_task_models.md`：文档版本、解析质量、锚点哈希和跨主题字段。
- 当前仓库后端：仅存在 `backend/.gitkeep`，没有可调用服务、DTO、鉴权实现或测试夹具。

## 3. 术语与数据边界

API 规范使用 `RuleHit` 作为风险项关联名称，数据模型以 `Finding` 为主实体。本设计在 UI 层统一称为“规则命中 / 审核发现（AuditFinding）”，不新增后端实体；适配层应保留原始 `finding_id`、`evaluation_id` 与 `rule_hit` 引用。

- `RuleEvaluation`：某规则在当前运行中是否适用、执行成功、跳过或失败的事实。没有 `finding_ids` 不等于“无风险”；必须同时展示评估状态。
- `RuleHit` / `Finding`：可独立处置的候选风险项，不是批准、法律意见或最终案件状态。
- `FindingExplanation`：给人看的理由、证据摘要、反证和限制；不得展示思维链、隐藏提示或凭据。
- `SourceLocator` / `Locator`：同一文档版本和解析产物中的原文锚点；定位状态由后端返回，前端不能自行推算。
- `AuthorityReference`：规则、模板、政策或外部依据的版本化引用；依据缺失必须显示“依据不足”。
- `AuditResult`：运行级汇总投影；`READY_FOR_DELIVERY` 不等于案件 `approved`，案件批准只由人工决定接口表达。

所有组件都必须携带并显示或内部持有：`case_id`、`document_version_id`/`document_id`、`audit_run_id`/`task_id`、`baseline_version_id`/`ruleset_version`、`is_read_only`、`revision`。历史版本或被替代运行只读，不允许复用当前运行的写操作入口。

## 4. 页面层级与组件树

```text
P3 案件详情
└── AuditContextBanner
    ├── VersionRunIdentity
    ├── AuditStatusSummary
    └── ResultEntry (按 allowed_actions 显示)

P5 风险结果与原文证据
├── AuditContextBanner
├── AuditResultSummaryCard
│   ├── ResultStatusBadge / ConclusionBadge
│   ├── SeveritySummary
│   ├── EvaluationCoverageSummary
│   ├── ReviewGateSummary
│   └── LimitationList
├── FindingFilterBar
├── AuditFindingList
│   └── AuditFindingRow
│       ├── SeverityBadge / ConfidenceBadge
│       ├── FindingStatusBadge
│       ├── LocatorAvailabilityBadge
│       └── SuggestedAction
└── AuditFindingDetailDrawer
    ├── FindingHeader
    ├── RuleEvaluationPanel
    ├── RuleHitEvidencePanel
    ├── FindingExplanationPanel
    ├── SourceLocatorReader
    ├── AuthorityReferenceList
    ├── SuggestionList
    └── FindingHistoryPanel

P6 人工审核工作台
├── AssignmentContextHeader
├── AuditFindingList (可接收/筛选待办)
└── AuditFindingDetailDrawer
    ├── 全部 P5 证据组件（审核者字段扩展）
    ├── ParseQualityPanel
    ├── DecisionPrerequisitePanel
    └── FindingDecisionActions

P7 决定确认与交付预览
├── DecisionContextCheck
├── SelectedFindingEvidenceSummary
├── DeliveryPreview (按服务端可见性投影)
├── DecisionReasonForm
└── DecisionSubmitResult
```

## 5. 组件设计

### 5.1 `AuditContextBanner` / `VersionRunIdentity`

职责：在结果页、详情抽屉和决定确认页固定展示案件、当前文档版本、审核运行、基线/规则集版本及只读/替代状态。

展示字段：`case_reference`、`case_id`、`document_version_id`、版本号、`audit_run_id`、`baseline_version_id`、`ruleset_version`、运行状态、更新时间、`is_current`、`is_read_only`、`result_status`。

规则：

- `is_read_only=true`、`result_status=superseded` 或版本被替代时显示“历史只读”，隐藏决定提交入口。
- 上下文缺任一关键 ID 时显示“上下文不完整，暂不可操作”，不从 URL 或本地缓存补造。
- 后端返回未知枚举时保留原值并降级为“待确认”，不得推断为完成或通过。

### 5.2 `AuditResultSummaryCard`

职责：概览运行级结果及其可信度边界，避免以风险数量代替覆盖率或以 `READY_FOR_DELIVERY` 代替批准。

展示字段：

- `result_status`、`risk_level`、`conclusion`（`CONCLUSION_PENDING` 等）。
- `finding_count_total`、`severity_counts`、`status_counts`。
- `evaluation_counts`、`rule_coverage_ratio`。
- `unresolved_required_count`、`redline_hit_count`、`locator_degraded_count`。
- `limitations`、`delivery_summary`（仅在后端授权返回时显示）。

状态规则：

- `FAILED`：显示处理未完成及服务端行动说明，不显示“无风险”。
- `READY_FOR_HUMAN_REVIEW`：显示“等待人工复核”；列出阻断原因。
- `READY_FOR_DELIVERY`：显示“结果已准备交付”，仍不渲染案件批准徽标。
- `DELIVERED`：仅表示交付快照已生成；案件批准状态仍来自案件/决定接口。
- `SUPERSEDED`：显示被哪个新运行替代（若授权返回），只读查看。

### 5.3 `RuleEvaluationPanel`

职责：解释规则执行事实，防止“没有命中”被误读成“规则通过”。

展示字段：`evaluation_id`、规则名称/`rule_key`、`rule_version`、`ruleset_version`、`evaluation_status`、`applicability_reason`、`failure_summary`、开始/完成时间、`finding_ids` 数量。

映射：

- `EVALUATED`：显示“已评估”，并区分命中/未命中。
- `NOT_APPLICABLE`：显示“不适用”及理由，不计为规则覆盖缺陷。
- `INCONCLUSIVE`：显示“无法判定，需人工确认”。
- `FAILED` / `SKIPPED`：显示“规则未完成/已跳过”，加入结果限制；禁止渲染为通过。

内部规则阈值、检索查询、提示词正文不下发；审核者只见版本和安全摘要。

### 5.4 `AuditFindingRow` / `AuditFindingDetailDrawer`

职责：呈现单个 `Finding` 的风险性质、可信度和处置状态，并进入证据详情。

列表最小字段：`finding_id`（可折叠显示）、`category`、`title`、`summary`、`severity`、`confidence_band`、`finding_status`、`human_review_requirement`、`is_redline`、定位可用性、建议动作。

详情扩展字段：`hit_type`、`confidence_score`（审核者）、`rule_id`/`rule_version`、`ruleset_id`/`ruleset_version`、`evaluation_id`、`revision`、`cluster_key`、`decision_id`、`superseded_by_finding_id`、建议列表和历史决定差异。

展示规则：

- 严重度必须同时用文字、图标和形状编码，不以颜色单独表达。
- `CONFIDENCE_LOW` 或 `CONFIDENCE_UNKNOWN` 配合“需重点核对原文”文案；不能只显示数值。
- `is_redline=true` 显示红线标记并固定置于人工处置区域；不能提供自动放行按钮。
- `finding_status` 是服务端只读投影。前端决策请求只提交 `action`、理由、证据引用和版本，不提交状态值。
- `EVIDENCE_GAP`、`CONFLICT`、无依据或限制非空时，显示“证据/依据不足”，并阻断案件级批准入口（最终由后端裁决）。
- `SUPERSEDED` 仅显示历史关系；不可在当前运行列表中与新 Finding 合并或覆盖。

### 5.5 `FindingExplanationPanel`

职责：把“为什么命中”组织成可审阅的说明，区分解释文本与溯源判据。

展示字段：`reason_text`、`reason_codes`、`evidence_summary`、`extracted_values`、`counter_evidence`、`limitations`、`generated_by`、（审核者）`model_name`/`model_version`/`prompt_version`、`retrieval_refs`、生成时间。

分区：

1. 结论理由：标题、`reason_text`、结构化原因码。
2. 支撑与反证：证据摘要、提取值、反证/例外上下文。
3. 限制：OCR 质量、附件缺失、输入截断、司法辖区未核验等受控项。
4. 溯源（审核者）：规则/规则集版本、模型和提示版本、检索来源版本。

禁止：显示模型逐步思考、系统提示词、内部密钥、未授权检索内容；缺字段时显示“服务端未提供”，不得用客户端生成文本补齐。

### 5.6 `SourceLocatorReader`

职责：展示 `SourceLocator` 返回的摘录和定位，并按定位状态降级。

展示字段：`locator_id`、`quote`/`anchor_text`、`context_excerpt`、`section_path`、`page_number`、`text_start`/`text_end`、`bounding_boxes`、`locator_status`、`content_hash`、文件标识；通过 `GET .../locators/{locator_id}` 获取受授权内容。

定位状态：

- `LOCATOR_VERIFIED`：允许页/段跳转和精确高亮。
- `LOCATOR_APPROXIMATE`：允许页级/段落级跳转，显示“定位需确认”，禁用精确高亮承诺。
- `LOCATOR_STALE`：显示原摘录与后端返回的候选位置；按钮为“人工重新绑定”，不得静默跳转候选。
- `LOCATOR_UNAVAILABLE`：仅显示摘录/解释，明确“无法定位到原文，需人工核验”，不显示伪坐标。

当一个 Finding 的全部定位均为 `STALE`/`UNAVAILABLE` 或为空时，详情顶部固定证据不足警告；与 `AuditResult.locator_degraded_count` 保持一致。定位属于其他版本/运行或 API 返回权限错误时，组件显示“当前用户无权查看定位”或“定位不属于当前版本”，不尝试跨上下文请求。

### 5.7 `AuthorityReferenceList`

职责：展示规则实际使用的版本化依据，帮助审核者复核适用性。

展示字段：`authority_ref_id`、`source_type`、`source_key`、`version`、`citation`、`excerpt`、`applicability_note`。

规则：

- `authority_ref_ids=[]` 时显示“依据不足”，并将 Finding 标为需人工复核。
- 对提交者只展示后端授权后的交付说明或安全化引用；审核者才显示完整引用、版本和适用性备注。
- 不自行拼接外部链接、下载地址或当前规则库内容；引用失效由后端返回状态。

### 5.8 `DecisionPrerequisitePanel` / `DeliveryPreview`

职责：在 P7 提交前复核当前责任、上下文、证据和交付可见性。

复核项：当前操作者与 `allowed_actions`、assignment 状态/责任、`expected_revision`、文档版本、运行/基线、未处置必需 Finding、红线、证据定位、依据和必要授权引用。

规则：

- 仅展示服务端返回的允许动作；隐藏按钮不构成授权。
- `revision_conflict`、`stale_human_task`、`run_superseded`、`evidence_incomplete` 时不展示提交成功，刷新当前上下文并保留用户未提交草稿（不把草稿当决定）。
- `DeliveryPreview` 使用服务端过滤后的 `visible_result`，不从审核者视图裁剪生成提交者视图，不泄露被过滤字段存在性。

## 6. API 接入点

| 前端用途 | API 接入点 | 组件消费者 | 当前实现状态 |
| --- | --- | --- | --- |
| 案件上下文 | `GET /api/v1/cases/{case_id}` | `AuditContextBanner`、P3 | 契约已定义；后端未开发 |
| 运行状态/摘要 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}` | `AuditContextBanner`、异常区 | 契约已定义；后端未开发 |
| 运行汇总 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/result` | `AuditResultSummaryCard` | 契约已定义；后端未开发 |
| 风险列表 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/findings?status=&severity=&cursor=` | `AuditFindingList` | 契约已定义；后端未开发 |
| 风险详情 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/findings/{finding_id}` | 详情抽屉及全部证据子组件 | 契约已定义；后端未开发 |
| 原文定位 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/locators/{locator_id}` | `SourceLocatorReader` | 契约已定义；后端未开发 |
| 人工待办上下文 | `GET /api/v1/cases/{case_id}/assignments/{assignment_id}` | P6/P7 前置复核 | 契约已定义；后端未开发 |
| 接收待办 | `POST /api/v1/cases/{case_id}/assignments/{assignment_id}/accept` | P6 接收动作 | 契约已定义；后端未开发 |
| 提交人工决定 | `POST /api/v1/cases/{case_id}/assignments/{assignment_id}/decisions` | `FindingDecisionActions`、P7 | 契约已定义；后端未开发 |
| 交付快照 | `GET /api/v1/cases/{case_id}/delivery-snapshot`（以 API 规范最终路径为准） | `DeliveryPreview`、提交者视图 | 契约已定义；后端未开发 |

前端联调必须等待真实后端响应后再启用成功态；在后端未开发阶段只实现类型、空态、加载态、错误态和契约校验，不伪造“已批准”“无风险”或“定位成功”的 Mock 路径。

## 7. 质量、定位失效与权限状态矩阵

| 状态 | 结果/证据区表达 | 可用动作 |
| --- | --- | --- |
| 解析质量 `QUALIFIED` | “解析可用于审核” | 依后端 `allowed_actions` 查看/复核 |
| `INSUFFICIENT` / `UNAVAILABLE` | “解析质量不足，证据可能不完整”并显示质量限制 | 禁止前端自行放行；等待补件/人工 |
| 定位 `APPROXIMATE` | “定位需确认” | 页/段跳转，禁精确高亮 |
| 定位 `STALE` | “原定位已失效”+原摘录/候选位置 | 人工重新绑定；不自动采用候选 |
| 定位 `UNAVAILABLE` 或无 locator | “无法定位到原文，需人工核验” | 仅查看解释，后端决定是否可处置 |
| 依据为空 | “依据不足” | 强制人工复核；不可自动批准 |
| Finding 低/未知置信度 | “置信度低/不可用，请核对原文” | 审核者复核 |
| `revision_conflict` | “当前任务已变化，请刷新” | 重新读取，不显示提交成功 |
| `action_not_authorized` / 403 | “当前角色无权执行此操作” | 只读查看或联系责任队列 |
| 字段被可见性过滤 | 不显示占位数量或可推断存在性的错误差异 | 仅展示授权投影 |
| 当前后端未开发/网络不可用 | “审核结果暂不可用” | 加载/重试/返回详情；不生成结果结论 |

## 8. 关键决策

1. **以证据链为主线**：结果页采用“汇总 → Finding → 解释 → 定位/依据”的钻取关系；组件不把摘要当作证据本体。
2. **状态语义严格分层**：`RuleEvaluation`、`Finding.finding_status`、`AuditResult.result_status` 与案件 `approved` 分开显示，避免自动化阶段越权表达。
3. **定位状态由后端权威返回**：前端只渲染 `locator_status`，不通过文本搜索或相似度自行修复锚点。
4. **角色视图同源不同字段**：审核者看到复核所需质量、模型/规则溯源；提交者只看到授权交付结果、限制和待办。
5. **写操作统一走人工决定 API**：不直接恢复 LangGraph checkpoint，不写 `finding_status`、严重度、定位或案件终态。
6. **未知值安全降级**：未知枚举、缺字段、接口错误均进入待确认/不可用状态，不能默认成功。

## 9. 风险与待解决问题

- 后端尚未开发，API 目前只有 Markdown 契约；字段命名（`document_id` 与 `document_version_id`、`task_id` 与 `audit_run_id`、`RuleHit` 与 `Finding`）需在 DTO/Schema 阶段正式收口。
- `AuthorityReference` 的独立查询接口未在 v1.0 API 中单列，当前依赖 Finding 详情嵌入；若权限或分页需求扩大，应新增只读接口并更新契约。
- 受控原文阅读器的访问令牌、分页/附件页码和坐标渲染协议尚未实现，不能在前端提前承诺 PDF 高亮能力。
- 质量比率、限制码与可见性过滤的角色矩阵需要后端提供契约测试，避免提交者通过数量或错误差异推断隐藏风险。
- 人工决定成功后异步恢复运行，前端需要明确轮询/推送策略；在此策略确定前不得假设决定提交后立即得到最终 `AuditResult`。
- 结果汇总的 `evaluation_counts` 为空或缺失时，前端只能显示“覆盖率不可用”，不能把空列表解释成“无风险”。

## 10. 下一阶段交付物

1. 后端：实现结果、Finding、Locator、Assignment、Decision 的 API DTO、授权过滤、`revision` 校验和最小可用测试夹具；明确上述命名映射。
2. 前端：在 `frontend/` 恢复可运行工程后，按本文件组件树实现类型、加载/空/错误/只读状态，再接入真实 API；不得在后端未开发时宣称联调成功。
3. 联调：覆盖成功、无命中但规则未完成、定位 `APPROXIMATE/STALE/UNAVAILABLE`、质量不足、权限过滤、版本替代、并发冲突和人工决定失败路径。
4. 设计验收：为 P5/P6/P7 建立可访问性检查，确保严重度不靠颜色、证据不足有文本提示、提交者与审核者字段隔离。
5. 文档回写：后端 DTO 与 API 路径收口后，更新本文件的字段映射、错误码和“后端未开发”标记，并在阶段测试记录中保留验证证据。

## 11. 自检记录

- [x] 仅新增本文件，未修改 `frontend/`、`backend/` 或其他文档。
- [x] 已明确目标、输入、结论、关键决策、风险和下一阶段交付物。
- [x] 已覆盖 `RuleEvaluation`、`RuleHit/Finding`、`FindingExplanation`、`AuditResult`、`SourceLocator`、`AuthorityReference` 的组件职责与字段展示。
- [x] 已覆盖定位失效、解析质量、权限、版本替代、并发冲突和后端未开发状态。
- [x] 未创建或描述伪造的成功 Mock 路径；没有声称前端依赖安装、启动或联调测试完成。
