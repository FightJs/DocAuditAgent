# 文档上传、材料准入与解析任务页面/路由实施计划

## 1. 目标

本计划承接前端页面设计规范与 API v1.0 契约，定义从“创建案件”到“上传材料、材料准入、异步解析、状态追踪、补件/重提”的页面层级、路由、组件职责、客户端状态模型和 API 依赖，供后续前端原型、实现和联调使用。

本计划的边界是用户提交与查看流程，不实现文件准入、解析、审核结论、权限判定或后端任务编排。服务端返回的案件、文档版本、处理任务和错误状态始终是权威来源；前端只负责收集输入、发起明确操作、展示已授权数据并引导下一步。

## 2. 输入

| 输入文档/检查项 | 本计划的使用方式 |
| --- | --- |
| `docs/08_api_spec/api_spec-v1.0.md` | 作为接口路径、请求字段、响应状态、错误码、幂等、版本和权限约束的唯一 API 输入。 |
| `docs/06_system_architecture/frontend_design_spec-v1.0.md` | 继承 P1 案件列表、P2 新建上传、P3 详情时间线、P4 补件/重提的页面层级和状态表达。 |
| `docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md` | 约束服务端权威性、最小可见性、版本不可覆盖和前端不得自行判断终态。 |
| `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md` | 确认解析通过后才可创建审核运行；HITL 恢复、checkpoint 和内部 `thread_id` 不暴露给前端。 |
| `AGENTS.md` | 确认文档目录职责、前后端边界和当前前端未恢复的事实。 |
| 当前仓库检查 | `backend/` 仅包含 `.gitkeep`；`frontend/` 尚无 `package.json`、锁文件或可运行源码。所有接口均标为“未开发”，本计划不声称已完成依赖安装、启动或联调。 |

## 3. 范围与不在范围内

### 3.1 本计划覆盖

- 提交者创建案件、选择审核范围、填写业务上下文。
- 上传批次/文档版本的创建、文件角色选择、文件内容上传和批次提交。
- 上传进度、准入等待、解析状态、质量信号、失败和补件提示。
- 案件详情中的当前版本、版本关系、状态时间线和可执行下一步。
- 通过补件请求创建新上传批次和新文档版本，保留历史只读。
- 路由级权限门禁、组件级 `allowed_actions` 处理、统一错误展示和并发刷新。

### 3.2 明确不覆盖

- 后端文件存储、病毒/安全扫描、实际 MIME 检测、解析器、队列、LangGraph 执行和任务重试策略。
- 审核基线选择、风险生成、Agent 结论、人工批准或交付创建。
- 前端直连对象存储、调用 checkpoint、`Command(resume=...)` 或内部 `thread_id`。
- 用浏览器校验结果替代后端准入；用 `upload_session.status=completed` 替代材料通过；用空风险列表替代批准。

## 4. 结论与整体页面结构

采用案件上下文驱动的路由树。新建/上传与补件页是写入型页面；案件详情是所有异步阶段的稳定落点；状态变化通过刷新详情、时间线和材料详情呈现，不通过页面跳转伪造状态变化。

```text
应用壳
├── /cases                         P1 案件列表
├── /cases/new                     P2 新建案件（步骤 1：范围与上下文）
├── /cases/:caseId/upload          P2 新建案件（步骤 2：材料上传与提交）
├── /cases/:caseId                 P3 案件详情/处理时间线
├── /cases/:caseId/versions/:versionId
│                                  P3 材料与解析详情（详情页内嵌或子路由）
└── /cases/:caseId/supplements/new P4 补件/重提材料
```

建议保留可扩展的占位路由（仅在后续对应计划中实现）：

```text
/cases/:caseId/runs/:runId/findings        P5 风险结果（未在本计划实施）
/review/queues/:queueId                     P6 人工工作台（未在本计划实施）
```

路由命名是实现建议，不代表当前选择了具体路由库。待 `frontend/` 恢复后，先根据实际 `package.json` 和锁文件确定技术方案。

## 5. 路由与页面详细设计

### 5.1 `/cases`：案件列表（P1）

**页面目的**：展示当前主体授权范围内的案件，提供“新建审核案件”入口，并将待补件/处理中案件引导到稳定的详情页。

**页面层级**：

```text
案件列表
├── 页面标题、当前角色和授权范围摘要
├── 新建审核案件（仅后端允许创建时显示）
├── 筛选/检索：案件状态、合同类型、审核范围、当前责任（按返回字段）
├── 案件条目
│   ├── case_reference、contract_type、audit_scope_id
│   ├── 当前状态和面向当前角色的行动提示
│   ├── current_document_version.version_number/status
│   ├── 最近更新时间
│   └── 查看详情
└── 加载、空结果、不可见/无权限、请求失败状态
```

**接口依赖**：

| 接口 | 用途 | 当前实现状态 |
| --- | --- | --- |
| `GET /api/v1/cases`（API v1.0 未定义具体列表契约） | 列表数据、分页和筛选。若后端不补充该契约，前端不得自行拼接或跨案件查询。 | 未开发；待 API 补充 |
| `POST /api/v1/cases` | 创建入口提交后建立案件。 | 未开发；`backend/` 仅 `.gitkeep` |

**权限**：服务端返回案件可见范围；前端不使用 URL 中可猜测的 `case_id` 推断可访问性。隐藏“新建”按钮只改善体验，不能替代 `action_not_authorized` 校验。

### 5.2 `/cases/new`：新建案件（P2 步骤 1）

**组件职责**：

- `CaseCreateForm`：收集 `case_reference`、`audit_scope_id`、`contract_type` 和合同类型所需的 `business_context`。
- `ScopeDescriptionPanel`：展示审核范围、材料要求、隐私/保留提示；内容必须来自服务端配置或明确的静态产品文案，不在客户端推断适用性。
- `CreateCaseSubmitBar`：提交时生成请求级 `Idempotency-Key`；防止重复点击；成功后保存 `case_id`、`revision` 和 `allowed_actions`。
- `ApiErrorNotice`：按统一错误 envelope 展示 `request_id`，不暴露内部堆栈。

**字段展示与校验**：

| 字段 | 展示/客户端校验 | 服务端裁决 |
| --- | --- | --- |
| `case_reference` | 必填、长度/空白检查、重复提交期间禁用按钮。 | 租户内唯一性；冲突返回 `case_reference_conflict`。 |
| `audit_scope_id` | 必填、只显示当前主体可选项。 | 适用性和授权范围；无效返回 `invalid_audit_scope`。 |
| `contract_type` | 选择合同类型，驱动业务上下文字段展示。 | 合同类型有效性和允许字段。 |
| `business_context` | 仅显示该类型的必要字段。 | 字段白名单、权限与业务规则。 |

**成功跳转**：`201` 后导航到 `/cases/:caseId/upload`，并把服务端 `allowed_actions` 作为页面操作上下文；不得把 `status=created` 展示为已接收材料或审核通过。

### 5.3 `/cases/:caseId/upload`：上传材料与提交（P2 步骤 2）

这是上传页面的核心状态机，必须区分“文件字节已上传”和“材料批次已提交/准入处理中”。

**页面层级**：

```text
上传材料
├── 案件摘要：case_id、case_reference、合同类型、审核范围
├── 版本/提交说明：首版或 parent_document_version_id、submission_note
├── 材料角色清单
│   ├── primary_contract（恰有一个）
│   └── supporting_attachment（零个或多个，按服务端限制）
├── 文件行
│   ├── display_name、声明 MIME、字节大小、可见上传进度
│   ├── 客户端预检结果（仅辅助）
│   ├── upload_session.status
│   └── 重传/移除（仅在批次仍可编辑时）
├── 提交前检查摘要
│   ├── 可继续项
│   ├── 缺失正文/角色/未完成上传
│   └── 服务端拒绝前不得伪造“准入通过”
├── 提交批次按钮
└── 提交回执或转到案件详情
```

**上传操作顺序与 API 依赖**：

1. `POST /api/v1/cases/{case_id}/upload-batches` 创建不可变文档版本和各文件 `upload_session_id`。接口未开发。
2. 对每个文件调用 `PUT /api/v1/upload-sessions/{upload_session_id}/content` 上传字节。接口未开发。
3. 所有必需文件返回 `status=completed` 后，调用 `POST /api/v1/upload-batches/{upload_batch_id}/submit`，携带 `expected_revision`、`confirm_submission=true` 和 `Idempotency-Key`。接口未开发。
4. `202` 成功后导航 `/cases/:caseId`，显示 `intake_pending`/`uploading`，随后通过详情或时间线读取权威状态。

**文件字段与前端模型**：

```text
UploadDraft
├── upload_batch_id?           服务端返回
├── document_version_id?       服务端返回
├── parent_document_version_id? 补件/重提时必填
├── submission_note
└── files[]
    ├── file_asset_id?
    ├── display_name
    ├── role: primary_contract | supporting_attachment
    ├── byte_size
    ├── declared_mime_type
    ├── sha256?
    ├── upload_session_id?
    ├── status: local | created | uploading | completed | failed | expired
    └── error(request_id/code)?
```

客户端只能使用 `local/created/uploading/completed/failed/expired` 作为上传 UI 状态。后端准入状态（如 `accepted`、`materials_requested`、`rejected`、`quarantined`、`unreadable`）必须来自查询接口，不能由文件扩展名或浏览器 MIME 推断。

### 5.4 `/cases/:caseId`：案件详情与处理时间线（P3）

该路由是提交、准入、解析、Agent 分流和人工接手期间的稳定页面；所有状态都在此呈现。

**页面层级**：

```text
案件详情
├── 案件摘要
│   ├── case_id、case_reference、contract_type、audit_scope_id
│   ├── 当前 status、updated_at、revision
│   ├── 当前 document_version（版本号、状态、父版本、只读标识）
│   ├── current_audit_run（如有：run、baseline、状态、是否当前）
│   └── 当前角色可执行动作（allowed_actions）
├── 材料与版本卡片
│   ├── 正文/附件角色、文件名、准入状态
│   ├── 版本关系与历史只读入口
│   └── 打开材料/解析详情
├── 处理阶段条
│   ├── 上传接收 → 材料准入 → 解析/质量 → 审核分流 → 人工/交付
│   └── 阶段文案由服务端状态映射，未知枚举降级为“待确认”
├── 当前行动卡
│   ├── 处理中：刷新/有限轮询入口
│   ├── changes_requested：进入补件
│   ├── parse_failed/agent_failed：显示服务端指引
│   └── human_reviewing：仅授权审核者显示待办入口
├── 状态时间线
│   └── GET /timeline 分页、版本/运行关联、异常和人工摘要
└── 结果入口（仅存在且授权时）
```

**接口依赖**：

| 接口 | 页面用途 | 当前实现状态 |
| --- | --- | --- |
| `GET /api/v1/cases/{case_id}` | 摘要、当前版本/运行、责任和 `allowed_actions`。 | 未开发 |
| `GET /api/v1/cases/{case_id}/timeline` | 时间线、异常和版本关系。 | 未开发 |
| `GET /api/v1/cases/{case_id}/document-versions/{document_version_id}` | 材料清单、准入、解析任务、质量和失败摘要。 | 未开发 |
| `GET /api/v1/cases/{case_id}/document-versions/{document_version_id}/material-requests` | 补件项、目的、关联风险、截止时间和响应版本。 | 未开发 |
| `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}` | 仅用于已创建运行的状态/路由摘要；风险结果不在本计划实现。 | 未开发 |

### 5.5 `/cases/:caseId/versions/:versionId`：材料与解析详情

可作为详情页的子视图或独立路由。用于审核者或有授权提交者查看当前版本的材料与解析质量，不提供原始对象存储地址。

**字段展示**：

- `document_version_id`、`version_number`、`parent_document_version_id`、`is_read_only`。
- 每个文件的角色、显示名、服务端准入状态；不展示 `storage_object_ref`、签名 URL 或安全引擎细节。
- 解析任务状态、质量状态、失败/重试安全摘要、可继续/需补件/不可继续说明。
- 对定位不可用、过期或质量不足的状态显示“证据/定位待确认”，不得提供伪造跳转。

**只读规则**：历史版本只能查看；任何替换、补件或修改都返回 `/cases/:caseId/supplements/new` 创建新版本，不能在本页原地编辑。

### 5.6 `/cases/:caseId/supplements/new`：补件/重提材料（P4）

**进入条件**：详情接口返回 `status=changes_requested` 或存在当前用户可见且未完成的 `material_request`。前端不得仅因文件上传失败就自行创建补件请求。

**页面层级**：

```text
补件/重提
├── 当前案件与旧版本摘要（旧版本只读）
├── 待处理 material_request[]
│   ├── request_id、status、missing_items、purpose
│   ├── 关联风险（仅授权可见）
│   ├── due_at/priority（如返回）
│   └── response_document_version_id（如有）
├── 新版本说明 submission_note
├── 新材料上传清单（正文/附件角色）
├── 上传进度与提交前检查
└── 提交回执：新 batch/version、父版本、`intake_pending`
```

**API 顺序**：

1. `GET .../material-requests` 获取当前请求，接口未开发。
2. `POST /api/v1/cases/{case_id}/upload-batches`，必须携带 `parent_document_version_id`，接口未开发。
3. 逐文件 `PUT /api/v1/upload-sessions/{upload_session_id}/content`，接口未开发。
4. `POST /api/v1/upload-batches/{upload_batch_id}/submit`，携带新的 `expected_revision` 和幂等键，接口未开发。
5. 成功后返回详情，明确“新版本处理中，旧版本只读”；不得把旧版本结果复用为新版本结论。

## 6. 状态模型与交互规则

### 6.1 业务状态展示映射

| 服务端状态 | 页面表达 | 可执行动作（以 `allowed_actions` 为准） |
| --- | --- | --- |
| `created` / `uploading` | 正在创建或接收材料 | 继续上传、查看详情 |
| `intake_pending` / `accepted` | 材料已提交，正在准入 | 查看进度；不得显示“已通过审核” |
| `parsing` / `ready` | 正在读取或解析已完成 | 查看材料与质量；等待后续审核 |
| `agent_reviewing` / `agent_completed` / `triaged` | 正在审核或确认分流 | 查看阶段；授权审核者进入待办 |
| `human_reviewing` | 正在人工复核 | 提交者只看状态；当前责任审核者按权限处理 |
| `changes_requested` | 需要补充或修改材料 | 进入补件/重提 |
| `parse_failed` / `agent_failed` | 处理未完成 | 仅按服务端返回选择重试、补件或人工处理 |
| `rejected` | 当前版本/案件未获批准 | 查看授权原因；必要时重提 |
| `approved` / `delivered` | 人工决定已完成/已交付 | 查看授权交付（本计划只预留入口） |
| `resubmitted` | 新材料已收到，正在重新处理 | 查看新版本详情 |
| `archived` | 已归档，只读 | 查看授权历史 |
| 未知枚举 | 待确认 | 禁用高风险写操作并刷新 |

### 6.2 上传与提交状态

- 本地文件读取失败、网络失败、会话过期与服务端拒绝必须分别显示。
- 单文件上传重试复用同一个 `upload_session_id`；若服务端返回冲突/过期，提示重新创建批次，不覆盖旧版本。
- 批次提交重复点击复用同一 `Idempotency-Key`。相同请求可展示原结果；`idempotency_conflict` 必须刷新上下文，不得显示提交成功。
- `202 Accepted` 只代表进入异步处理，不代表准入通过、解析完成、低风险或批准。

### 6.3 轮询/刷新

本计划只允许在收到服务端状态后刷新详情或时间线。轮询间隔、推送协议和最大次数待后端/平台规范确定；前端不得根据 HTTP 码自行推断 `retryable`。若 `processing_unavailable` 或网络失败，保持“信息暂不可用/处理中”语义。

## 7. 异常、补件和并发交互

统一错误 envelope 为：`error.code`、面向角色的 `message`、`details`、`retryable`、`request_id`。页面处理规则如下：

| 错误/异常 | 用户界面行为 |
| --- | --- |
| `invalid_request` / `invalid_action_payload` | 标记字段或上传行，保留用户输入，不重试原请求。 |
| `unauthenticated` | 保存可安全恢复的草稿后重新认证；不显示案件数据。 |
| `action_not_authorized` / `visibility_denied` | 隐藏受限内容/动作，提示无权限；不泄露资源是否存在。 |
| `case_not_found` / `resource_not_found` | 显示不可用/不存在的安全文案，不根据错误差异推断资源存在性。 |
| `upload_incomplete` | 标出未完成文件和缺失 `primary_contract`，允许继续上传。 |
| `materials_requested` | 在详情和补件页展示可行动缺失项；新提交必须创建新版本。 |
| `revision_conflict` | 停止当前写操作，重新获取案件/批次/待办上下文；未确认的提交不可显示成功。 |
| `run_superseded` / `stale_human_task` | 标记旧上下文只读，返回详情读取新版本/运行。 |
| `assignment_already_taken` | 仅对审核工作台预留；本计划不实现领取逻辑。 |
| `rate_limited` | 按 `Retry-After` 有界重试；上传/提交不生成新幂等键。 |
| `processing_unavailable` | 保持处理中/暂不可用，不改写为失败或通过。 |
| `internal_error` | 显示操作未完成并保留 `request_id`，提供安全重试入口。 |

## 8. 权限与可见性边界

### 8.1 提交者（`submitter`）

- 可创建本人授权范围内案件、上传首版或补件、查看本人授权的案件/版本/状态、查看补件请求和授权交付。
- 不展示内部模型轨迹、安全检测细节、隐藏风险、其他案件、未授权人员身份或未核实候选。
- 不提供直接批准、直接交付、修改历史版本或调用 HITL 恢复的入口。

### 8.2 审核者及其他审核角色

- 仅在后端授予案件/队列责任和 `allowed_actions` 时显示解析质量、审核基线、路由/异常摘要及复核所需上下文。
- 本计划不实现人工工作台，但详情页可按 `allowed_actions` 预留进入 P6 的入口。
- 前端按钮、路由守卫和组件禁用均不是授权控制；每次写操作必须依赖后端重新校验。

### 8.3 未知或缺失权限

权限字段缺失、未知角色或未知动作按最小权限处理：只读展示安全摘要，禁用上传/提交/补件写操作，并提示刷新或联系管理员。

## 9. API 依赖总表与当前开发状态

当前后端目录仅有 `backend/.gitkeep`，以下接口没有可运行实现，全部标注“未开发”：

| 业务能力 | 接口 | 依赖页面 | 状态 |
| --- | --- | --- | --- |
| 创建案件 | `POST /api/v1/cases` | `/cases/new` | 未开发 |
| 案件列表 | `GET /api/v1/cases`（规范未收口） | `/cases` | 未开发；需先补契约 |
| 创建上传批次/新版本 | `POST /api/v1/cases/{case_id}/upload-batches` | `/cases/:caseId/upload`、补件页 | 未开发 |
| 上传文件内容 | `PUT /api/v1/upload-sessions/{upload_session_id}/content` | 上传/补件页 | 未开发 |
| 提交批次并触发准入 | `POST /api/v1/upload-batches/{upload_batch_id}/submit` | 上传/补件页 | 未开发 |
| 案件概览 | `GET /api/v1/cases/{case_id}` | 详情页、列表回执 | 未开发 |
| 状态时间线 | `GET /api/v1/cases/{case_id}/timeline` | 详情页 | 未开发 |
| 版本/材料/解析 | `GET /api/v1/cases/{case_id}/document-versions/{document_version_id}` | 材料解析详情 | 未开发 |
| 补件请求 | `GET /api/v1/cases/{case_id}/document-versions/{document_version_id}/material-requests` | 详情页、补件页 | 未开发 |
| 审核运行摘要 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}` | 详情页状态区 | 未开发 |
| 风险/证据/交付 | API v1.0 第 5.5、7.1 节 | 本计划只预留入口 | 未开发；不在本阶段实现 |

在后端接口和字段 schema 未提供前，前端可以建立纯 UI 原型或契约夹具，但必须标明“模拟数据”，不得声称联调、真实上传或任务状态已完成。

## 10. 实施步骤（后续前端阶段）

1. **契约准备**：后端提供 OpenAPI/JSON Schema、鉴权上下文、固定枚举、统一错误 envelope 和测试主体；补齐案件列表查询契约。
2. **页面骨架**：在 `frontend/` 恢复 `package.json` 后确定包管理器，建立应用壳、路由守卫和 P1–P4 页面骨架；不在项目根目录安装依赖。
3. **类型与状态层**：以 `case_id`、`document_version_id`、`upload_batch_id`、`upload_session_id`、`audit_run_id`、`revision` 为显式上下文，处理未知枚举和只读历史。
4. **上传链路**：接入批次创建、文件上传、提交接口；实现进度、会话过期、幂等和禁止重复提交。
5. **详情与异步状态**：接入案件概览、版本详情、时间线和补件查询；实现刷新/轮询适配层，保持服务端状态权威。
6. **补件/重提**：复用上传组件但强制 `parent_document_version_id`，验证旧版本只读和新版本关联。
7. **联调与验收**：依 API 规范第 9 节顺序验证成功、无权限、重复请求、并发冲突、失败、质量不足和补件路径。

## 11. 验证方式

页面实现完成后至少验证：

- 创建案件成功、重复幂等、无效审核范围和无权限。
- 正文/附件角色约束、未完成上传、会话过期、不同内容冲突和重新创建批次。
- `202` 后状态从 `intake_pending`、`parsing`、`ready` 到人工/补件/失败分支的正确文案。
- `materials_requested`、`rejected`、`quarantined`、`unreadable` 不显示为审核通过或无风险。
- 补件创建新 `document_version_id`，父版本只读，旧结果不被覆盖。
- `revision_conflict`、`run_superseded`、未知状态、`request_id` 保留及最小可见性。
- 所有写操作都使用服务端返回的 `expected_revision` 和幂等键；前端不直接调用 checkpoint/HITL 恢复。

由于当前 `frontend/` 无 `package.json`、锁文件或运行源码，当前阶段不执行也不声称 npm 安装、开发服务启动或前端自动化测试已完成。

## 12. 关键决策

1. 以 `/cases/:caseId` 作为所有异步阶段的稳定落点；状态变化不通过跳转冒充完成。
2. 将新建案件和上传拆成两步，确保案件创建成功后才创建上传批次和不可变文档版本。
3. 上传会话完成与材料准入通过严格分离；准入、解析质量和补件只能展示后端返回值。
4. 补件/重提统一走新上传批次和新文档版本，旧版本及旧运行只读保留。
5. `allowed_actions`、角色和案件范围决定动作呈现；服务端始终负责最终授权，前端不复制业务规则。
6. 后端尚未实现时只允许契约原型/夹具，不伪造真实接口、任务状态或批准能力。

## 13. 风险、待解决问题与缓解

| 风险/待解决问题 | 影响 | 缓解/责任 |
| --- | --- | --- |
| 案件列表 `GET /cases` 未在 API v1.0 收口 | P1 无法真实加载 | 后端/API 阶段补充分页、筛选、可见性契约；前端暂不实现真实列表。 |
| 上传是否分片、是否对象存储直传未定 | 上传进度和重试实现可能变化 | 前端只依赖 `upload_session` 语义；待后端确定传输适配，不耦合存储 URL。 |
| 实时推送协议未定 | 详情刷新体验和请求量不确定 | 先实现可替换的状态刷新适配层；不把轮询间隔写死为业务语义。 |
| 文件大小/页数/数量和允许扩展名未收口 | 客户端预检无法完整提示 | 由服务端返回约束/错误；客户端只作辅助检查。 |
| 解析质量字段和状态枚举可能扩展 | 未知状态误导用户 | 所有未知枚举降级为“待确认”，禁用高风险动作并保留原值。 |
| 权限和可见性交付字段按角色过滤 | 页面可能出现过度展示或存在性泄露 | 仅渲染已返回字段；统一安全错误文案；后端补齐角色夹具。 |
| 前后端并发导致旧页面提交 | 误覆盖或错误提示 | 强制 `expected_revision`、幂等键和冲突后刷新；不将本地草稿当权威状态。 |

## 14. 下一阶段交付物

- 后端：上传批次、文件内容、准入、版本详情、时间线、补件查询的可运行 API 和 schema；提供成功/失败/质量不足/补件/并发夹具。
- 前端：路由与页面骨架、类型化 API client、上传状态机、详情状态适配层和 P1–P4 交互实现。
- 联调：按 API v1.0 第 9 节从案件创建到补件/重提完成端到端验收，并记录 `case_id`、`document_version_id`、`upload_batch_id`、`audit_run_id`、`request_id`。
- 文档：补充实际路由库、组件目录、字段 schema、刷新协议和前端测试记录；若新增状态或接口，先更新业务/API 文档及 Plan。

