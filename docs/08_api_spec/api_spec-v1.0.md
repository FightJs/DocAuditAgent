# DocAuditAgent API 规范 v1.0

## 1. 文档定位与收口范围

本规范是文档审核 MVP 的前后端 API 收口契约，供后续前端接入、后端实现、联调和测试使用。它只定义业务接口的输入、输出、权限、状态、错误和调用顺序，不定义数据库表、ORM、对象存储产品、消息队列、解析器、模型提示词或 LangGraph SDK 签名。

覆盖范围：

1. 案件创建、文档上传、材料准入和异步解析任务；
2. 案件、版本、审核运行、风险、证据、状态和交付查询；
3. 人工待办接收、风险处置、案件级决定、转交/升级、补件和提交者异议；
4. 前后端联调接入顺序、幂等、并发、可见性和错误处理。

`approved` 只能由有权限人员基于当前有效文档版本、审核运行、审核基线和证据作出。上传成功、解析成功、Agent 完成、空风险项或 `ready_for_delivery` 均不得被 API 表达为批准。

## 2. 输入依据与文件名说明

本规范基于以下工作区文档：

- [`data_model_spec-v1.0.md`](../06_system_architecture/data_model_spec-v1.0.md)
- [`langchain_hitl_arch-v1.0.md`](../04_core_interaction_flows/langchain_hitl_arch-v1.0.md)
- [`document_audit_business_model.md`](../03_business_problem_modeling/document_audit_business_model.md)
- [`backend_service_architecture_spec-v1.0.md`](../06_system_architecture/backend_service_architecture_spec-v1.0.md)
- [`langchain_hitl_document_audit_arch-v1.0.md`](../06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md)

用户指定的 `docs/06_system_architecture/langchain_hitl_workflow_design-v1.0.md` 与 `docs/06_system_architecture/backend_service_arch-v1.0.md` 在当前工作区不存在。本规范以现存的 HITL 文档审核架构规范和后端服务架构规范作为对应输入；不据此新增未定义的工作流或服务行为。

## 3. 通用 API 约定

### 3.1 协议、路径和媒体类型

- 基础路径：`/api/v1`。
- 请求和 JSON 响应使用 `application/json; charset=utf-8`。
- 文件内容使用 `multipart/form-data` 的逻辑上传接口；若实现采用受控对象存储直传，必须仍返回本规范定义的 `upload_session` 和提交结果，不能改变业务状态语义。
- 时间为 UTC RFC 3339 字符串；标识为不可猜测的不透明字符串。
- 枚举值使用小写 `snake_case`。客户端遇到未知枚举必须保留原值并降级为“待确认”，不得推断成功。
- 所有响应均可包含 `request_id`；前端在错误反馈和联调日志中保留该值。

### 3.2 认证、授权和可见性

每个接口均需要已认证主体；后端根据主体、角色、案件范围、队列责任、合同类型和风险等级重新校验权限。前端隐藏按钮不构成授权控制。

角色语义：

| 角色 | 允许的 API 操作 |
| --- | --- |
| `submitter` | 创建案件、上传/补件、查询本人授权范围、查看补件和授权交付、提交异议。 |
| `reviewer` | 查看证据包、接收待办、编辑/确认风险、要求补件、在授权范围内驳回或同意、转交/升级。 |
| `expert` / `approver` | 处理升级事项、风险接受以及其授权范围内的案件级决定。 |
| `policy_owner` | 仅管理后续审核基线；不得借 API 改写已完成运行。 |
| `operator` / `admin` | 队列和异常运营；不因管理权限替代专业审批。 |

服务端对提交者返回 `DeliverySnapshot.visible_result`、授权补件和异议数据；不返回内部模型轨迹、安全检测细节、未核实候选、其他案件、隐藏人员信息或受限依据。被过滤字段不应通过 `null`、数量或错误差异泄露存在性。

### 3.3 版本、运行与并发上下文

任何审核结果或人工动作都必须带或能解析出以下上下文：

```json
{
  "case_id": "case_01J...",
  "document_version_id": "docv_01J...",
  "audit_run_id": "run_01J...",
  "baseline_version_id": "baseline_2026_01"
}
```

后端拒绝跨上下文读取或写入。文档补件/修改创建新 `document_version_id`；基线变化创建新 `audit_run_id`；旧版本、旧运行、旧决定和旧 checkpoint 只读保留。

所有改变当前业务状态的写接口都必须携带：

- `idempotency_key`：调用方生成，按主体、资源和动作形成幂等范围；相同键和相同请求摘要返回原结果，不同摘要返回冲突；
- `expected_revision`：客户端最近一次读取的待办、案件或风险投影版本；不匹配返回 `revision_conflict`；
- 明确动作和理由（人工动作必需）。

### 3.4 统一成功与错误 envelope

成功响应直接返回 `data`，列表响应增加 `page`；错误统一为：

```json
{
  "error": {
    "code": "revision_conflict",
    "message": "当前任务已发生变化，请刷新后重试",
    "details": {
      "current_revision": 8,
      "resource_type": "review_assignment",
      "resource_id": "assignment_01J..."
    },
    "retryable": false,
    "request_id": "req_01J..."
  }
}
```

错误 `message` 面向当前角色安全可展示；内部堆栈、提示词、密钥、对象存储地址和安全引擎细节永不通过 API 返回。

## 4. 案件创建与文档上传接口

### 4.1 创建审核案件

`POST /api/v1/cases`

角色：`submitter`。幂等：请求头 `Idempotency-Key` 必填。

请求：

```json
{
  "case_reference": "contract-2026-001",
  "audit_scope_id": "scope_nda_v1",
  "contract_type": "nda",
  "business_context": {
    "counterparty_name": "Example Co.",
    "purpose": "合作洽谈"
  }
}
```

字段约束：`case_reference` 在授权租户内唯一；`audit_scope_id` 必须是当前主体可用的审核范围；业务上下文只接受该合同类型所需字段，不能以客户端字段绕过权限或适用性校验。

响应 `201 Created`：

```json
{
  "data": {
    "case_id": "case_01J...",
    "case_reference": "contract-2026-001",
    "status": "created",
    "audit_scope_id": "scope_nda_v1",
    "revision": 1,
    "created_at": "2026-08-14T08:00:00Z",
    "allowed_actions": ["create_upload_batch"]
  },
  "request_id": "req_01J..."
}
```

错误：`invalid_audit_scope`、`case_reference_conflict`、`action_not_authorized`。

### 4.2 创建上传批次与文档版本

`POST /api/v1/cases/{case_id}/upload-batches`

角色：`submitter`。用于首版上传、补件或重提；不得覆盖历史版本。补件时请求应显式带 `parent_document_version_id`。

请求：

```json
{
  "submission_note": "补充签署页和附件 A",
  "parent_document_version_id": "docv_01J...",
  "files": [
    {
      "display_name": "contract.pdf",
      "role": "primary_contract",
      "byte_size": 182736,
      "declared_mime_type": "application/pdf",
      "sha256": "optional-client-checksum"
    },
    {
      "display_name": "annex-a.pdf",
      "role": "supporting_attachment",
      "byte_size": 82736,
      "declared_mime_type": "application/pdf"
    }
  ]
}
```

服务端返回预创建的不可变版本和每个文件的上传会话：

```json
{
  "data": {
    "upload_batch_id": "batch_01J...",
    "document_version_id": "docv_01J...",
    "version_number": 2,
    "parent_document_version_id": "docv_01J...",
    "status": "draft",
    "files": [
      {
        "file_asset_id": "file_01J...",
        "role": "primary_contract",
        "upload_session_id": "ups_01J...",
        "status": "created",
        "expected_byte_size": 182736,
        "expires_at": "2026-08-14T09:00:00Z"
      }
    ],
    "revision": 1
  }
}
```

约束：每个提交版本最终必须恰有一个 `primary_contract`；文件角色、哈希和内容提交后不可原地改写。错误包括 `case_not_found`、`version_conflict`、`materials_not_allowed`、`file_count_exceeded`、`upload_batch_duplicate`。

### 4.3 上传文件内容

`PUT /api/v1/upload-sessions/{upload_session_id}/content`

角色：已获案件访问权的上传主体。请求为文件字节，支持 `Content-Length`；实现若采用分片，分片序号和范围必须保持同一 `upload_session_id` 的幂等语义。

响应 `200 OK`：

```json
{
  "data": {
    "upload_session_id": "ups_01J...",
    "status": "completed",
    "received_byte_size": 182736,
    "file_asset_id": "file_01J..."
  }
}
```

`completed` 只表示字节接收完成，不表示准入通过。重复提交同一内容返回当前结果；不同内容或过期会话返回 `upload_session_conflict` 或 `upload_session_expired`。

### 4.4 提交上传批次并触发准入

`POST /api/v1/upload-batches/{upload_batch_id}/submit`

角色：`submitter`。幂等：`Idempotency-Key` 必填。

请求：

```json
{
  "expected_revision": 3,
  "confirm_submission": true
}
```

成功响应 `202 Accepted`：

```json
{
  "data": {
    "case_id": "case_01J...",
    "upload_batch_id": "batch_01J...",
    "document_version_id": "docv_01J...",
    "document_version_status": "intake_pending",
    "case_status": "uploading",
    "next_action": "poll_case_status"
  }
}
```

服务端随后执行实际类型、大小/页数/数量、安全性、可打开性、材料角色、完整性和审核范围校验。失败时不返回“审核不通过”的泛化语义，而返回安全化的 `materials_requested`、`rejected`、`quarantined` 或 `unreadable` 状态及可行动原因。错误：`upload_incomplete`、`revision_conflict`、`submission_not_allowed`。

## 5. 状态与审核查询接口

### 5.1 查询案件概览

`GET /api/v1/cases/{case_id}`

角色：有案件访问权的主体。

响应至少包含：

```json
{
  "data": {
    "case_id": "case_01J...",
    "case_reference": "contract-2026-001",
    "contract_type": "nda",
    "audit_scope_id": "scope_nda_v1",
    "status": "human_reviewing",
    "current_document_version": {
      "document_version_id": "docv_01J...",
      "version_number": 2,
      "status": "ready",
      "parent_document_version_id": "docv_01J...",
      "is_read_only": false
    },
    "current_audit_run": {
      "audit_run_id": "run_01J...",
      "baseline_version_id": "baseline_2026_01",
      "status": "triaged",
      "is_current": true
    },
    "assignment_summary": {
      "assignment_id": "assignment_01J...",
      "queue_code": "legal_review",
      "assignment_status": "in_progress",
      "assignee_display": "当前审核者"
    },
    "allowed_actions": ["view_findings", "submit_decision"],
    "revision": 8,
    "updated_at": "2026-08-14T08:40:00Z"
  }
}
```

提交者只能看到授权后的责任和摘要；审核者可见完成处置所需的队列、路由和证据包。

### 5.2 查询案件状态时间线

`GET /api/v1/cases/{case_id}/timeline?cursor=...&limit=50`

返回按 `occurred_at` 倒序的状态事件、版本关系、解析/审核异常和人工动作摘要。事件中的 `prior_state`、`next_state`、主体类别和当前版本/运行必须与后端审计事实一致。分页响应：

```json
{
  "data": [
    {
      "event_id": "evt_01J...",
      "event_type": "state_changed",
      "occurred_at": "2026-08-14T08:40:00Z",
      "document_version_id": "docv_01J...",
      "audit_run_id": "run_01J...",
      "prior_state": "triaged",
      "next_state": "human_reviewing",
      "summary": "已进入人工复核"
    }
  ],
  "page": {"next_cursor": null}
}
```

### 5.3 查询材料、解析和质量

`GET /api/v1/cases/{case_id}/document-versions/{document_version_id}`

返回版本说明、父子版本关系、材料清单、每个文件的准入状态、解析任务状态、失败/重试安全摘要、解析质量状态和开放补件。不得返回 `storage_object_ref`、签名 URL 或安全引擎细节。

`GET /api/v1/cases/{case_id}/document-versions/{document_version_id}/material-requests`

返回 `material_request` 的 `id`、状态、缺失项、目的、关联风险、截止时间和响应版本。补件完成必须通过新上传批次，不允许直接修改补件对象为已满足。

### 5.4 查询审核运行和结果

`GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}`

返回运行状态、固定的 `document_version_id`、`baseline_version_id`、运行时间、路由原因、异常摘要、替代关系和结果摘要。若运行已被替代，仍可按显式历史请求读取，但响应必须标记 `is_read_only: true`、`result_status: superseded`。

`GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/result`

返回 `AuditResult`、`evaluation_summary`、`severity_summary`、`review_summary`、限制项和按角色过滤的风险项引用。`ready_for_delivery` 不得包含案件级 `approved` 字段。

### 5.5 查询风险项、解释和原文证据

`GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/findings?status=&severity=&cursor=`

列表项至少包含 `finding_id`、类别、标题、严重度、置信度、处置状态、人工复核要求、红线标记、定位可用性和建议动作（按角色过滤）。

`GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/findings/{finding_id}`

返回当前风险项、关联 `RuleHit`、规则评估状态、`FindingExplanation`、`AuthorityReference`、`SourceLocator` 和历史决定差异。定位 `unavailable`/`stale` 时必须明确显示证据不足，不得伪造可跳转位置。

`GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/locators/{locator_id}`

返回经授权的 `quote`、`context_excerpt`、`section_path`、页码/坐标（如有）、`locator_status` 和 `content_hash`。后端校验定位属于同一版本和运行；不允许仅凭 `locator_id` 跨案件访问。

## 6. 人工审核与 HITL 接口

### 6.1 查询人工队列和待办

`GET /api/v1/review-queues/{queue_id}/assignments?status=queued&cursor=...`

角色：`reviewer`、`expert`、`approver`、`operator`（按授权）。返回案件摘要、当前文档版本、运行/基线、最高严重度、风险计数、路由原因、优先级、等待时间和当前责任。提交者不能调用。

`GET /api/v1/cases/{case_id}/assignments/{assignment_id}`

返回完整待办上下文：`assignment_status`、队列、责任、路由原因、期限、版本/运行/基线三元组、当前 `expected_revision`、可执行动作和证据包入口。后端据当前权限动态计算 `allowed_actions`。

### 6.2 接收待办

`POST /api/v1/cases/{case_id}/assignments/{assignment_id}/accept`

请求：

```json
{
  "expected_revision": 4,
  "idempotency_key": "accept-assignment-uuid"
}
```

成功响应 `200 OK` 返回新的责任人、`assignment_status: accepted` 或 `in_progress`、`expected_revision` 和可执行动作。接收待办不等于任何风险确认或案件批准。

错误：`assignment_not_found`、`assignment_already_taken`、`assignment_not_authorized`、`revision_conflict`、`assignment_superseded`。

### 6.3 提交人工决定（统一入口）

`POST /api/v1/cases/{case_id}/assignments/{assignment_id}/decisions`

角色：当前责任人或有明确接管权限的审核者。统一入口承接 `approve`、`edit`、`reject`、`request_supplement`、`transfer`、`escalate`、`accept_risk`、`withdraw`、`correct`。请求公共字段：

```json
{
  "action": "edit",
  "document_version_id": "docv_01J...",
  "audit_run_id": "run_01J...",
  "baseline_version_id": "baseline_2026_01",
  "risk_item_id": "finding_01J...",
  "expected_revision": 12,
  "idempotency_key": "decision-uuid",
  "reason": "该条款满足例外条件，需调整风险等级",
  "evidence_refs": [
    {"type": "locator", "id": "locator_01J..."},
    {"type": "rule_hit", "id": "hit_01J..."}
  ],
  "payload": {}
}
```

公共校验：后端重新校验身份、队列责任、权限快照、案件状态、版本/运行/基线一致性、证据归属、`expected_revision` 和幂等键；前端提交的 `severity`、`locator`、原始候选或案件终态不是权威写入。

#### `approve`

仅允许案件级决定。`payload` 可含 `conditions`、`authorization_ref`。后端必须确认所有必处置风险已完成、证据可复核、必要风险接受授权齐备；成功后案件进入 `approved`，但不直接代表 `delivered`。缺证据、低置信度未处置、红线未处理或版本过期返回 `action_not_allowed` 或 `evidence_incomplete`。

#### `edit`

风险项或案件意见均可编辑。`payload` 必须含 `before_value` 和 `after_value`；后端追加 `HumanDecision`，形成新的 `DecisionEffect`，不得覆盖 `RuleHit`、原始解释、原文或历史决定。

#### `reject`

仅案件级。`payload` 必须含驳回范围、关联风险/规则和面向提交者的后续说明；成功后案件进入 `rejected`。

#### `request_supplement`

`payload.requested_supplements` 必须列出材料/修改项、目的、关联风险和优先级/期限（如适用）；后端建立 `material_request`，案件进入 `changes_requested`。提交者补件必须创建新版本和新运行。

#### `transfer` / `escalate`

`payload` 必须含目标队列或主体、原因和 `handoff_question`。后端先追加后继 `ReviewAssignment`，再结束/替代原待办；失败时保持原责任不变并记录审计。

#### `accept_risk`

仅风险项级，必须携带 `authorization_ref`、理由和证据；成功只将风险项标记为 `accepted_with_authorization`，不自动批准案件。

#### `withdraw` / `correct`

必须引用 `previous_decision_id`，用于未交付决定的受控撤回或更正。已交付结果不得原地修改，应创建新决定、必要时新运行和新的 `DeliverySnapshot`。

成功响应 `201 Created`：

```json
{
  "data": {
    "decision_id": "decision_01J...",
    "decision_status": "accepted",
    "action": "edit",
    "case_status": "human_reviewing",
    "finding_projection": {
      "finding_id": "finding_01J...",
      "status": "modified"
    },
    "assignment_revision": 13,
    "audit_event_id": "evt_01J..."
  }
}
```

### 6.4 HITL 恢复边界

人工决定接口是业务权威入口；前端不得直接调用 `Command(resume=...)`、checkpoint 存储或内部 `thread_id`。后端在决定成功落库、生成审计事件和更新投影后，才按当前有效上下文恢复图执行。恢复必须使用同一审核运行的受控内部标识。

若文档版本、审核基线、运行、责任、权限或关键证据变化，后端拒绝恢复旧暂停流程，返回 `run_superseded` 或 `stale_human_task`，并要求前端重新查询新上下文。中断节点从开头重执行导致的待办、通知和写入必须由后端幂等和去重保护。

### 6.5 提交者异议

`POST /api/v1/cases/{case_id}/objections`

角色：`submitter`。请求：

```json
{
  "decision_id": "decision_01J...",
  "delivery_id": "delivery_01J...",
  "document_version_id": "docv_01J...",
  "audit_run_id": "run_01J...",
  "baseline_version_id": "baseline_2026_01",
  "objection_type": "evidence_dispute",
  "scope_type": "risk_items",
  "risk_item_ids": ["finding_01J..."],
  "statement": "该段落引用范围不完整",
  "supporting_document_version_ids": []
}
```

后端验证提交者权限和被异议对象归属，创建 `SubmitterObjection`，路由新的人工待办；异议本身不直接改变 `approved`、`rejected` 或 `delivered`。新增材料必须重新走上传准入和新版本链路。

## 7. 交付查询接口

### 7.1 获取交付快照

`GET /api/v1/cases/{case_id}/deliveries/{delivery_id}`

只有有效收件主体可读。返回 `delivery_id`、批准决定引用、文档版本/运行/基线、`delivery_status`、`visible_result`、`visible_conditions`、`next_actions`、交付时间和更正/替代关系。响应不得包含内部决定理由、隐藏风险或原始 Agent 轨迹。

### 7.2 创建交付（内部业务动作）

`POST /api/v1/cases/{case_id}/deliveries`

仅服务端在案件为 `approved`、交付完整性/可见性检查通过后调用；前端不应提供“直接交付”按钮来绕过批准。请求至少引用 `approved_decision_id`、当前文档版本、审核运行和可见性策略。重复调用必须幂等，生成一个不可变 `DeliverySnapshot`。

## 8. 错误码与 HTTP 映射

| HTTP | `error.code` | 适用情形 | 前端处理 |
| --- | --- | --- | --- |
| 400 | `invalid_request` / `invalid_action_payload` | 字段缺失、枚举非法、动作载荷不完整。 | 定位表单字段，不重试原请求。 |
| 401 | `unauthenticated` | 会话无效或过期。 | 重新认证。 |
| 403 | `action_not_authorized` / `visibility_denied` | 无案件、队列或动作权限。 | 不显示受限数据，提示无权限。 |
| 404 | `case_not_found` / `resource_not_found` | 资源不存在或不可见。 | 使用安全的“不可用/不存在”文案。 |
| 409 | `revision_conflict` / `idempotency_conflict` / `run_superseded` / `assignment_already_taken` | 并发、重复键冲突或上下文过期。 | 刷新当前上下文；不要将提交显示为成功。 |
| 422 | `upload_incomplete` / `materials_requested` / `evidence_incomplete` / `action_not_allowed` | 业务前置条件不满足。 | 展示可行动原因和下一步。 |
| 429 | `rate_limited` | 请求频率超过限制。 | 按 `Retry-After` 有界重试。 |
| 500 | `internal_error` | 未预期服务错误。 | 显示操作未完成；使用 `request_id` 联系后端。 |
| 503 | `processing_unavailable` | 异步处理或依赖暂不可用。 | 保持处理中/不可用语义，不改写为失败或通过。 |

`retryable=true` 只由服务端返回；客户端不得按 HTTP 状态自行推断可重试性。上传、提交和人工决定的重试必须复用同一幂等键。

## 9. 前后端联调接入顺序

联调必须按业务依赖顺序进行，前端不得跳过上游状态直接开发终态页面：

| 阶段 | 后端先提供 | 前端接入与验收 |
| --- | --- | --- |
| 0. 契约准备 | OpenAPI/JSON Schema 或等价字段定义、统一错误 envelope、鉴权上下文、测试主体和固定枚举。 | 校验生成客户端/类型、未知枚举降级、错误展示和 `request_id` 透传。 |
| 1. 案件创建 | `POST /cases`、案件概览读接口、案件权限夹具。 | 创建案件、展示 `case_id`/状态/允许动作；验证重复幂等和无权限。 |
| 2. 上传与准入 | 上传批次、上传会话、文件内容、提交接口；返回准入/补件/拒绝状态。 | 上传进度、失败/过期重试、材料角色、提交回执；不得把 `completed` 当作通过。 |
| 3. 异步解析 | 版本详情、状态时间线、解析任务质量和补件查询；提供可控成功/失败/质量不足夹具。 | 轮询或服务端推送后刷新权威状态；验证新版本、失败、重试、补件和只读历史。 |
| 4. 审核查询 | 审核运行、结果、风险列表/详情、解释、依据和原文定位；提供版本/运行替代夹具。 | 风险列表、证据阅读器、定位失效提示、权限过滤；验证空命中不显示“无风险”。 |
| 5. 人工队列 | 队列/待办查询、接收接口、证据包和 `allowed_actions`。 | 待办领取、责任/并发提示、动作入口；验证已被他人领取和过期任务。 |
| 6. 人工决定 | 统一决定入口及六类核心动作（含风险接受、撤回/更正）、审计事件和投影。 | `approve/edit/reject/request_supplement/transfer/escalate` 表单与确认；验证幂等、版本冲突、权限拒绝和不可覆盖历史。 |
| 7. 交付与异议 | 交付快照查询、异议提交、补件新版本关联。 | 展示授权交付、条件、下一步和异议状态；验证内部字段不可见、交付后更正走新快照。 |
| 8. 端到端回归 | 贯通状态事件、审计、异步任务和可控异常注入。 | 从创建到上传、解析、风险、人工决定、交付/补件全链路验收。 |

每阶段完成条件是：成功路径、权限失败、过期/并发冲突、重复请求和至少一个异常路径均已验证，并能从响应中的 `case_id`、`document_version_id`、`audit_run_id`、`assignment_id` 和 `request_id` 关联日志。

## 10. 非目标与后续输入

本规范不规定实时推送协议、具体分页大小、对象存储签名算法、LangGraph checkpoint 表结构、模型供应商、规则 DSL、审批额度矩阵或外部签署集成。上述内容只能在对应架构、权限或实现规范中补充，并不得改变本规范的版本不可覆盖、人工批准边界、审计追加和可见性约束。

后续实现必须将本规范与三份主题数据模型共同作为输入；如需新增接口或状态，先更新业务模型、数据模型及本 API 规范，再进入代码实现和联调。

## 11. 验收记录

- 已覆盖文档上传、材料准入、异步解析、审核查询、风险/证据、人工审核、补件、转交/升级、异议和交付查询。
- 已为写接口定义权限、版本/运行/基线、责任、幂等、并发和审计约束。
- 已明确 HITL 恢复由后端内部控制，前端只提交业务人工决定。
- 已给出按依赖顺序执行的前后端联调接入阶段。
- 本阶段只生成 API 规范文档，未生成前后端代码或 Agent Team。
