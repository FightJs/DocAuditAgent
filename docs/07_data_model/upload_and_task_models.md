# 文档上传与任务状态数据模型规范

| 项 | 内容 |
| --- | --- |
| 文档目的 | 定义文档上传、材料准入、解析产物锚点、审核任务与任务步骤、异常记录的逻辑数据模型，作为前后端实现（表结构、API 请求/响应、界面字段）的直接输入。 |
| 版本 | v1.0 |
| 日期 | 2026-08-04 |
| 主题归属 | 数据模型规范阶段 Teammate 1（上传与任务状态） |
| 上游输入 | `docs/03_business_problem_modeling/document_audit_business_model.md`、`docs/04_core_interaction_flows/upload_intake_validation_parsing_task_flow.md`、`docs/04_core_interaction_flows/processing_status_and_exception_handling.md`、`docs/06_system_architecture/backend_service_architecture_spec-v1.0.md`、`docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md` |
| 下游消费方 | Teammate 2（审核规则/命中项/原文定位）、Teammate 3（人机交互决策）、Lead 汇总规范 `docs/06_architecture_design/data_model_spec-v1.0.md`、后续 API 规范与前后端实现计划 |
| 非目标 | 不定义对象存储/队列/解析器/OCR 引擎实现、不定义 API 路径与错误码、不定义审核规则与人工决定的内部字段、不包含任何可执行代码。 |

`READY` 只表示材料与解析结果可进入下一阶段，绝不表示审核通过、无风险或已交付。

## 1. 通用约定

| 约定 | 要求 |
| --- | --- |
| 标识符 | 所有主键为不透明字符串（UUID / UUIDv7）。客户端不得从文件名、哈希、数组下标推导标识。 |
| 时间字段 | 统一 `*_at` 后缀，UTC ISO-8601 带时区（例：`2026-08-04T09:12:33Z`）。`created_at`、`updated_at` 非空。 |
| 枚举值 | 统一大写下划线，如 `PARSE_FAILED`。客户端遇到未知枚举必须降级为“状态更新中”，禁止推断为成功或通过。 |
| 不可变性 | 已提交的 `document_version`、其 `file_object`、解析产物与状态事件不可原地改写。补件、替换正文、修改内容均创建新版本。 |
| 并发控制 | 写操作必须携带服务端返回的 `revision`（正整数，乐观锁）。不匹配时后端返回冲突并拒绝写入。 |
| 幂等 | 创建上传会话、提交上传批次、创建任务均带幂等键，见第 4.3 节。 |
| 权限 | 「前端必须展示」只表示已授权用户界面必须能取得该事实，不代表客户端可写。所有权威字段由后端裁决。 |

### 1.1 枚举定义

| 枚举 | 值 | 含义 |
| --- | --- | --- |
| `DocumentRole` | `PRIMARY_CONTRACT`、`SUPPORTING_ATTACHMENT` | 材料角色。每个可提交版本恰有 1 个正文。 |
| `UploadSessionStatus` | `CREATED`、`UPLOADING`、`COMPLETED`、`EXPIRED`、`CANCELLED`、`FAILED` | 字节传输会话状态，不等于准入结果。 |
| `FileIntakeStatus` | `PENDING`、`RECEIVING`、`RECEIVED`、`VALIDATING`、`ACCEPTED`、`REJECTED`、`QUARANTINED`、`UNREADABLE` | 单文件接收与安全/可读性准入结果。 |
| `DocumentStatus` | `DRAFT`、`UPLOADING`、`INTAKE_PENDING`、`ACCEPTED`、`MATERIALS_REQUESTED`、`PARSING`、`MANUAL_INTAKE_REVIEW`、`PARSE_FAILED`、`READY`、`REJECTED`、`SUPERSEDED` | 文档版本的材料与解析可用性，不承担案件级审批语义。 |
| `TaskType` | `PARSE`、`AUDIT` | 任务类型。`PARSE` 由本主题编排；`AUDIT` 的内部结果字段属于 Teammate 2。 |
| `TaskStatus` | `QUEUED`、`RUNNING`、`RETRYING`、`SUCCEEDED`、`FAILED`、`BLOCKED`、`CANCELLED` | 异步任务执行状态。`SUCCEEDED` 仍须由质量门槛决定文档是否 `READY`。 |
| `TaskStepStatus` | `PENDING`、`RUNNING`、`SUCCEEDED`、`FAILED`、`SKIPPED` | 任务内阶段状态。 |
| `ParseQualityStatus` | `NOT_EVALUATED`、`QUALIFIED`、`INSUFFICIENT`、`UNAVAILABLE` | 解析质量结论。仅 `QUALIFIED` 允许 `READY`。 |
| `ParseSourceType` | `NATIVE_TEXT`、`OCR`、`MIXED` | 文本来源，影响证据可信度。 |
| `ActorType` | `USER`、`SYSTEM`、`SERVICE`、`REVIEWER`、`SCHEDULER` | 状态变更触发主体类别。 |
| `ErrorSeverity` | `INFO`、`WARNING`、`ERROR`、`FATAL` | 异常严重度，用于运营监控与展示分级。 |
| `ErrorCategory` | `TRANSPORT`、`VALIDATION`、`SECURITY`、`PARSE`、`QUALITY`、`ORCHESTRATION`、`AUTHORIZATION`、`POLICY` | 异常归类，决定是否可自动重试。 |
| `ReasonCode` | `MATERIALS_INCOMPLETE`、`FILE_TYPE_INVALID`、`FILE_LIMIT_EXCEEDED`、`SECURITY_QUARANTINED`、`FILE_UNREADABLE`、`FILE_PASSWORD_PROTECTED`、`SCOPE_INVALID`、`PARSE_TRANSIENT_FAILURE`、`PARSE_OUTPUT_INVALID`、`PARSE_QUALITY_INSUFFICIENT`、`MANUAL_REVIEW_REQUIRED`、`SUPERSEDED_BY_RESUBMISSION`、`USER_CANCELLED`、`POLICY_CHANGED`、`UPLOAD_INCOMPLETE`、`IDEMPOTENCY_CONFLICT` | 面向系统的受控原因码。提交者可见文案由后端映射，不暴露安全检测细节。 |
| `MaterialRequestStatus` | `OPEN`、`FULFILLED`、`CANCELLED`、`EXPIRED` | 补件待办状态。 |

`SUPERSEDED` 仅表示已有后续版本成为当前处理对象；历史版本保留其准入结论、解析产物与事件。案件级状态（`AGENT_REVIEWING`、`HUMAN_REVIEWING`、`APPROVED`、`DELIVERED`、`ARCHIVED`）不由本模型写入，属于 Teammate 2/3 与案件编排模型。

## 2. 实体清单

### 2.1 `UploadSession`（上传会话，可续传的单文件传输）

短生命周期技术对象，一对一绑定一个预创建的 `FileObject`。完成传输不等于通过准入。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `upload_session_id` | string(UUID) | 是 | 不可变 | 主键，客户端续传引用。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属审核案件。 |
| `upload_batch_id` | string(UUID) | 是 | 外键 → `UploadBatch` | 所属提交批次。 |
| `file_object_id` | string(UUID) | 是 | 外键 → `FileObject`，1:1 | 目标文件记录。 |
| `status` | enum | 是 | `UploadSessionStatus` | 传输状态。 |
| `expected_byte_size` | int64 | 是 | ≥ 0 | 客户端声明大小，用于进度与完整性核对。 |
| `received_byte_size` | int64 | 是 | `[0, expected_byte_size]` | 已接收字节数。 |
| `checksum_algorithm` | string | 是 | 固定 `SHA256` | 校验算法。 |
| `expected_checksum` | string(hex64) | 否 | 64 位小写十六进制 | 客户端提供时由后端核验。 |
| `chunk_count_received` | int32 | 否 | ≥ 0 | 分片上传的已接收片数。 |
| `expires_at` | timestamp | 是 | UTC | 未完成会话必须到期，防止悬挂资源。 |
| `completed_at` | timestamp | 否 | UTC | 传输完成时间。 |
| `created_at` / `updated_at` | timestamp | 是 | UTC | 记录时间。 |

### 2.2 `UploadBatch`（上传批次，一次提交意图）

将一组材料、提交说明与幂等语义绑定到一个目标文档版本。不保存文件字节。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `upload_batch_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属案件。 |
| `document_id` | string(UUID) | 是 | 外键 → `Document`，提交后不可变 | 本批次的目标文档版本。 |
| `idempotency_key` | string | 是 | 1–128 字符；`(submitted_by_user_id, case_id, "UPLOAD_BATCH")` 唯一 | 调用方生成的幂等键。 |
| `submission_note` | string | 否 | 0–2000 字符 UTF-8 | 提交者版本说明。 |
| `client_file_count` | int32 | 是 | ≥ 0 | 客户端声明文件数，仅用于接收核对。 |
| `status` | enum | 是 | `CREATED`、`UPLOADING`、`SUBMITTED`、`ABANDONED`、`FAILED` | 批次状态。 |
| `submitted_by_user_id` | string(UUID) | 是 | 主体标识 | 提交者。 |
| `submitted_at` | timestamp | 否 | UTC；仅 `SUBMITTED` 后非空 | 提交时间。 |
| `created_at` / `updated_at` | timestamp | 是 | UTC | 记录时间。 |

### 2.3 `Document`（文档版本，不可变审核材料版本）

跨主题主键 `document_id`。一个 `Document` 记录代表某案件的一个不可变材料版本，含 1 个正文与 0..N 个附件。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `document_id` | string(UUID) | 是 | 不可变 | 主键。Teammate 2/3 统一以此引用被审文档版本。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属案件。 |
| `version_number` | int32 | 是 | ≥ 1；`(case_id, version_number)` 唯一且单调递增 | 案件内版本序号。 |
| `parent_document_id` | string(UUID) | 否 | 外键 → `Document`，同案件 | 首版为空；重提/替换指向来源版本。 |
| `superseded_by_document_id` | string(UUID) | 否 | 外键 → `Document`，同案件 | 被哪个新版本替代。 |
| `status` | enum | 是 | `DocumentStatus` | 版本当前状态，见第 4.1 节状态机。 |
| `audit_scope_id` | string(UUID) | 是 | 提交时固定，须在案件授权范围内 | 审核范围（合同类型/交易背景）。 |
| `contract_type_code` | string | 是 | 受控字典，如 `NDA`、`STANDARD_PURCHASE` | 合同类型，供基线匹配。 |
| `intake_policy_version` | string | 是 | 非空版本串 | 准入策略快照版本。 |
| `submitted_by_user_id` | string(UUID) | 是 | 主体标识 | 提交者。 |
| `submitted_at` | timestamp | 否 | UTC；提交后不可变 | 提交完成时间。 |
| `current_parse_task_id` | string(UUID) | 否 | 外键 → `Task` | 当前有效解析任务。 |
| `status_reason_code` | enum | 否 | `ReasonCode` | 当前状态原因。 |
| `revision` | int32 | 是 | ≥ 1 | 乐观并发版本号。 |
| `created_at` / `updated_at` | timestamp | 是 | UTC | 记录时间。 |

有效性约束：进入 `ACCEPTED`、`PARSING`、`MANUAL_INTAKE_REVIEW` 或 `READY` 前，必须存在恰好 1 个 `PRIMARY_CONTRACT` 且所有必需文件均 `ACCEPTED`；进入 `READY` 还须存在 `ParseQuality.status = QUALIFIED`。

### 2.4 `FileObject`（文档版本内的受控文件与存储引用）

每条记录代表一个原始上传文件。字节存于受控对象存储，本模型只保存不透明引用与元数据。Teammate 2 的 `SourceLocator.source_file_id` 引用本表主键。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `file_object_id` | string(UUID) | 是 | 不可变 | 主键。对外即 `source_file_id`。 |
| `document_id` | string(UUID) | 是 | 外键 → `Document` | 所属版本。 |
| `role` | enum | 是 | `DocumentRole`；每版本 `PRIMARY_CONTRACT` 恰 1 个 | 材料角色。 |
| `display_name` | string | 是 | 1–255 字符，已净化 | 展示文件名。 |
| `declared_mime_type` | string | 否 | MIME | 客户端声明类型，不可信。 |
| `detected_mime_type` | string | 否 | MIME | 服务端识别类型，准入判据。 |
| `byte_size` | int64 | 是 | ≥ 0 | 实测大小，接收完成后不可变。 |
| `page_count` | int32 | 否 | ≥ 0 | 实测页数，用于策略上限与定位校验。 |
| `sha256` | string(hex64) | 是 | 64 位小写十六进制；接收完成后不可变 | 原件完整性摘要，参与重复检测与幂等。 |
| `storage_object_ref` | string | 是 | 不透明引用，非公开 URL | 受控存储位置。禁止返回前端。 |
| `intake_status` | enum | 是 | `FileIntakeStatus` | 单文件准入结果。 |
| `intake_reason_code` | enum | 否 | `ReasonCode` | 准入原因码。 |
| `received_at` | timestamp | 否 | UTC | 完整接收时间。 |
| `quarantined_at` | timestamp | 否 | UTC；仅 `QUARANTINED` 时非空 | 隔离时间。 |
| `created_at` / `updated_at` | timestamp | 是 | UTC | 记录时间。 |

后端不得向前端返回 `storage_object_ref`、下载签名或安全检测细节。预览/下载须由后端基于案件授权另发短期受控访问能力。

### 2.5 `ParsedDocument`（解析产物根，原文定位锚点载体）

一个成功解析任务最多产生一个当前有效 `ParsedDocument`。它是 Teammate 2 `locator` 的锚点基座。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `parsed_document_id` | string(UUID) | 是 | 不可变 | 主键。Teammate 2 的 `SourceLocator.parsed_document_id` 引用此键。 |
| `document_id` | string(UUID) | 是 | 外键 → `Document` | 所属文档版本。 |
| `task_id` | string(UUID) | 是 | 外键 → `Task`，1:1 | 产生该产物的解析任务。 |
| `content_ref` | string | 是 | 受控引用 | 标准化全文内容存储引用，不返回前端。 |
| `normalized_text_length` | int64 | 是 | ≥ 0 | 标准化文本总字符数，`text_start`/`text_end` 的上界。 |
| `normalized_text_hash` | string(hex64) | 是 | SHA-256 | 标准化文本完整性摘要，`locator` 用它判定锚点是否 `STALE`。 |
| `page_count` | int32 | 是 | ≥ 0 | 解析后总页数。 |
| `detected_language` | string | 否 | BCP 47，如 `zh-CN` | 识别语言。 |
| `source_type` | enum | 是 | `ParseSourceType` | 文本来源。 |
| `parser_version` | string | 是 | 非空版本串 | 解析器/OCR 能力版本。 |
| `completed_at` | timestamp | 是 | UTC | 解析完成时间。 |
| `created_at` / `updated_at` | timestamp | 是 | UTC | 记录时间。 |

### 2.6 `ParsedPage`（页级锚点）

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `parsed_page_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `parsed_document_id` | string(UUID) | 是 | 外键 → `ParsedDocument` | 所属解析产物。 |
| `file_object_id` | string(UUID) | 是 | 外键 → `FileObject` | 该页所属源文件（区分正文/附件）。 |
| `page_number` | int32 | 是 | ≥ 1；`(parsed_document_id, file_object_id, page_number)` 唯一 | 从 1 开始的原文件页码，`locator.page_number` 对应此值。 |
| `text_start` | int64 | 是 | `[0, normalized_text_length)` | 该页在标准化文本中的起始偏移（0 起始）。 |
| `text_end` | int64 | 是 | 半开区间，> `text_start` | 该页结束偏移。 |
| `width_px` / `height_px` | int32 | 否 | > 0 | 页面渲染尺寸，用于归一化坐标换算。 |
| `page_image_ref` | string | 否 | 受控引用 | 页图引用，供阅读器高亮，不直接返回前端。 |
| `is_empty` | boolean | 是 | 默认 `false` | 是否空页/无可提取文本，参与质量评估。 |
| `ocr_confidence` | decimal(5,4) | 否 | `[0,1]` | 该页 OCR 置信度。 |

### 2.7 `ParsedBlock`（段/块级锚点）

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `parsed_block_id` | string(UUID) | 是 | 不可变 | 主键。`locator` 可用它作为稳定块锚点。 |
| `parsed_document_id` | string(UUID) | 是 | 外键 → `ParsedDocument` | 所属解析产物。 |
| `parsed_page_id` | string(UUID) | 否 | 外键 → `ParsedPage` | 起始页；跨页块指向首页。 |
| `parent_block_id` | string(UUID) | 否 | 外键 → `ParsedBlock` | 层级父块，表达条/款/项嵌套。 |
| `block_type` | enum | 是 | `HEADING`、`PARAGRAPH`、`LIST_ITEM`、`TABLE`、`TABLE_CELL`、`FOOTER`、`HEADER`、`SIGNATURE_BLOCK`、`UNKNOWN` | 块类型。 |
| `order_index` | int32 | 是 | ≥ 0；同层唯一 | 阅读顺序。 |
| `section_path` | string[] | 是（可为空数组） | 例 `["第5条","责任限制"]` | 章节层级，供 `locator.section_path` 直接使用。 |
| `text_start` | int64 | 是 | `[0, normalized_text_length)` | 块在标准化文本中的起始偏移。 |
| `text_end` | int64 | 是 | 半开区间，> `text_start` | 块结束偏移。 |
| `bounding_box` | object | 否 | `{page_number, x, y, width, height}`，各值 `[0,1]` 归一化 | 页面坐标框，供 `locator.bounding_boxes` 使用。 |
| `text_snippet_hash` | string(hex64) | 是 | SHA-256 | 块文本摘要，供 `locator.content_hash` 校验锚点未漂移。 |
| `confidence` | decimal(5,4) | 否 | `[0,1]` | 结构提取置信度。 |

`ParsedPage` 与 `ParsedBlock` 是本主题对外承诺的锚点最小集合：页码、字符偏移半开区间、归一化坐标、章节路径、文本摘要哈希。Teammate 2 的 `locator` 只组合这些锚点，不自行定义新的原文坐标体系。

### 2.8 `ParseQuality`（解析质量评估）

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `parse_quality_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `parsed_document_id` | string(UUID) | 是 | 外键 → `ParsedDocument`，1:1 | 被评估的解析产物。 |
| `status` | enum | 是 | `ParseQualityStatus` | 质量结论。仅 `QUALIFIED` 允许文档 `READY`。 |
| `text_coverage_ratio` | decimal(5,4) | 否 | `[0,1]` | 可提取文本覆盖率。 |
| `ocr_confidence_ratio` | decimal(5,4) | 否 | `[0,1]`；非 OCR 可空 | 平均 OCR 置信度。 |
| `unreadable_page_ratio` | decimal(5,4) | 否 | `[0,1]` | 空页/乱码页占比。 |
| `anchor_coverage_ratio` | decimal(5,4) | 否 | `[0,1]` | 可定位锚点覆盖率，直接影响证据可用性。 |
| `structure_completeness_ratio` | decimal(5,4) | 否 | `[0,1]` | 结构（条款层级/表格）提取完整度。 |
| `quality_policy_version` | string | 是 | 非空版本串 | 阈值策略快照版本。阈值不硬编码于客户端或本模型。 |
| `reason_code` | enum | 否 | `ReasonCode` | 质量不达标原因。 |
| `evaluated_at` | timestamp | 是 | UTC | 评估时间。 |

### 2.9 `Task`（审核任务/作业）

跨主题主键 `task_id`。本主题定义 `PARSE` 任务的完整编排；`AUDIT` 任务在此登记状态与生命周期，其规则、命中与结果字段由 Teammate 2 定义。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `task_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属案件。 |
| `document_id` | string(UUID) | 是 | 外键 → `Document` | 被处理的文档版本，创建时固定。 |
| `task_type` | enum | 是 | `TaskType` | 任务类型。 |
| `status` | enum | 是 | `TaskStatus` | 执行状态，见第 4.2 节状态机。 |
| `idempotency_key` | string | 是 | `(document_id, task_type, input_manifest_hash)` 唯一 | 任务级幂等键，防止并行覆盖。 |
| `input_manifest_hash` | string(hex64) | 是 | SHA-256 | 基于参与处理的 `file_object_id + sha256 + role + 排序` 生成的输入快照摘要。 |
| `audit_run_id` | string(UUID) | 否 | 由 Teammate 2 定义 | `AUDIT` 任务对应的审核运行；`PARSE` 任务为空。 |
| `engine_version` | string | 是 | 非空版本串 | 解析器/Agent 能力版本。 |
| `attempt_count` | int32 | 是 | ≥ 0，等于关联 `TaskAttempt` 数 | 已尝试次数。 |
| `max_attempts` | int32 | 是 | ≥ 1，创建时从策略快照固定 | 有界重试上限。 |
| `priority` | int32 | 否 | 默认 0，越大越先执行 | 队列优先级。 |
| `queued_at` | timestamp | 是 | UTC | 入队时间。 |
| `started_at` | timestamp | 否 | UTC | 首次开始执行时间。 |
| `finished_at` | timestamp | 否 | UTC；终态时非空 | 结束时间。 |
| `next_retry_at` | timestamp | 否 | UTC；`RETRYING` 时非空 | 下次重试时间（退避）。 |
| `failure_reason_code` | enum | 否 | `ReasonCode` | 失败原因码。 |
| `revision` | int32 | 是 | ≥ 1 | 乐观并发版本号。 |
| `created_at` / `updated_at` | timestamp | 是 | UTC | 记录时间。 |

约束：同一 `document_id` + `task_type` + `input_manifest_hash` 下最多一个活动任务（`QUEUED`、`RUNNING`、`RETRYING`、`BLOCKED`）。

### 2.10 `TaskStep`（任务步骤/阶段）

用于向审核者与运营呈现阶段级进度和失败点，也是重试定位依据。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `task_step_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `task_id` | string(UUID) | 是 | 外键 → `Task` | 所属任务。 |
| `step_code` | enum | 是 | `PARSE` 任务：`FETCH_SOURCE`、`SANITIZE`、`TEXT_EXTRACTION`、`OCR`、`STRUCTURE_EXTRACTION`、`ANCHOR_BUILD`、`QUALITY_EVALUATION`、`PERSIST_RESULT`；`AUDIT` 任务：`BASELINE_BINDING`、`RULE_EVALUATION`、`EVIDENCE_BINDING`、`TRIAGE` | 阶段标识。 |
| `step_order` | int32 | 是 | ≥ 1；`(task_id, step_code)` 唯一 | 阶段顺序。 |
| `status` | enum | 是 | `TaskStepStatus` | 阶段状态。 |
| `attempt_number` | int32 | 是 | ≥ 1 | 该阶段所属尝试序号。 |
| `progress_ratio` | decimal(5,4) | 否 | `[0,1]` | 阶段进度，供进度条使用。 |
| `started_at` / `finished_at` | timestamp | 否 | UTC | 阶段时间。 |
| `failure_reason_code` | enum | 否 | `ReasonCode` | 阶段失败原因。 |

### 2.11 `TaskAttempt`（任务尝试，有界重试记录）

可恢复故障通过新增尝试表达，不新建相互覆盖的任务。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `task_attempt_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `task_id` | string(UUID) | 是 | 外键 → `Task` | 所属任务。 |
| `attempt_number` | int32 | 是 | ≥ 1；`(task_id, attempt_number)` 唯一递增 | 尝试序号。 |
| `status` | enum | 是 | `QUEUED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`CANCELLED` | 尝试结果。 |
| `worker_ref` | string | 否 | 不透明执行者标识 | 运维排障用，不返回提交者。 |
| `started_at` / `finished_at` | timestamp | 否 | UTC | 尝试时间。 |
| `failure_reason_code` | enum | 否 | `ReasonCode` | 失败原因码。 |
| `error_record_id` | string(UUID) | 否 | 外键 → `ErrorRecord` | 关联异常记录。 |

### 2.12 `ErrorRecord`（错误/异常记录）

统一承载传输、准入、安全、解析、质量、编排类异常，供审核者接手与运营监控。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `error_record_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属案件。 |
| `document_id` | string(UUID) | 否 | 外键 → `Document` | 关联文档版本。 |
| `task_id` | string(UUID) | 否 | 外键 → `Task` | 关联任务。 |
| `task_step_id` | string(UUID) | 否 | 外键 → `TaskStep` | 关联阶段。 |
| `file_object_id` | string(UUID) | 否 | 外键 → `FileObject` | 关联文件。 |
| `category` | enum | 是 | `ErrorCategory` | 异常类别。 |
| `severity` | enum | 是 | `ErrorSeverity` | 严重度。 |
| `reason_code` | enum | 是 | `ReasonCode` | 受控原因码。 |
| `is_retryable` | boolean | 是 | 仅 `TRANSPORT`、`ORCHESTRATION` 及部分 `PARSE` 瞬时故障为 `true` | 是否允许自动重试。内容性问题必须为 `false`。 |
| `submitter_message_key` | string | 是 | 受控文案键 | 提交者可见安全文案的映射键，不含安全引擎细节。 |
| `internal_detail` | object(JSON) | 否 | 受访问控制；禁止存原文全文、凭据、安全规则 | 最小诊断信息。 |
| `correlation_id` | string | 否 | 追踪 ID | 跨服务链路关联。 |
| `occurred_at` | timestamp | 是 | UTC，不可变 | 异常发生时间。 |
| `resolved_at` | timestamp | 否 | UTC | 通过重试成功、补件或人工处理后关闭时间。 |

### 2.13 `MaterialRequest`（补件待办）

把「需要补件」的可行动事实从笼统状态中独立出来。

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `material_request_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属案件。 |
| `document_id` | string(UUID) | 是 | 外键 → `Document` | 触发补件的版本。 |
| `status` | enum | 是 | `MaterialRequestStatus` | 待办状态。 |
| `items` | array | 是 | 每项含 `role`、`requirement_code`、安全化 `instruction` | 需补/需替换材料清单。 |
| `reason_code` | enum | 是 | `ReasonCode` | 补件原因。 |
| `origin_decision_id` | string(UUID) | 否 | 由 Teammate 3 定义 | 若由人工决定触发，指向该决定。 |
| `created_by_actor_type` | enum | 是 | `ActorType` | 创建主体类别。 |
| `created_by_actor_id` | string(UUID) | 否 | 主体标识 | 创建主体。 |
| `due_at` | timestamp | 否 | UTC | 截止时间（策略要求时）。 |
| `fulfilled_by_document_id` | string(UUID) | 否 | 外键 → `Document` | 响应本待办的新版本。 |
| `created_at` / `updated_at` | timestamp | 是 | UTC | 记录时间。 |

### 2.14 `StatusEvent`（状态时间线，追加式）

| 字段名 | 类型 | 必填 | 取值域/枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `status_event_id` | string(UUID) | 是 | 不可变 | 主键。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属案件。 |
| `document_id` | string(UUID) | 否 | 外键 → `Document` | 版本上下文；上传链路事件应非空。 |
| `task_id` | string(UUID) | 否 | 外键 → `Task` | 任务上下文。 |
| `object_type` | enum | 是 | `DOCUMENT`、`FILE_OBJECT`、`UPLOAD_SESSION`、`TASK`、`TASK_STEP`、`MATERIAL_REQUEST` | 状态所属对象类型。 |
| `object_id` | string(UUID) | 是 | 对应对象主键 | 状态所属对象。 |
| `from_status` | string | 否 | 对应枚举；创建事件可空 | 原状态。 |
| `to_status` | string | 是 | 对应枚举 | 目标状态。 |
| `reason_code` | enum | 否 | `ReasonCode` | 迁移原因。 |
| `actor_type` | enum | 是 | `ActorType` | 触发主体类别。 |
| `actor_id` | string(UUID) | 否 | 主体标识 | 触发主体。提交者仅见类别。 |
| `occurred_at` | timestamp | 是 | UTC，不可变 | 事件发生时间，不能用查询时间替代。 |
| `correlation_id` | string | 否 | 追踪 ID | 链路关联。 |

`StatusEvent` 只追加，不更新、不删除。展示可按权限过滤，但记录不可因展示限制而丢弃。

## 3. 实体关系

### 3.1 关系图

```text
AuditCase (案件，生命周期容器；本主题只引用)
├── 1:N UploadBatch                      FK upload_batch.case_id
│        └── 1:1 Document                FK upload_batch.document_id（提交后不可变）
├── 1:N Document                         FK document.case_id
│        ├── 1:N FileObject              FK file_object.document_id
│        │        └── 1:1 UploadSession   FK upload_session.file_object_id
│        ├── 1:N Task                     FK task.document_id（PARSE 与 AUDIT 各自活动任务唯一）
│        │        ├── 1:N TaskStep         FK task_step.task_id
│        │        ├── 1:N TaskAttempt      FK task_attempt.task_id
│        │        └── 0:1 ParsedDocument   FK parsed_document.task_id（仅 PARSE 且 SUCCEEDED）
│        │                 ├── 1:N ParsedPage    FK parsed_page.parsed_document_id
│        │                 │        └── 1:N ParsedBlock (via parsed_page_id)
│        │                 ├── 1:N ParsedBlock   FK parsed_block.parsed_document_id
│        │                 │        └── 自引用层级 parent_block_id (1:N)
│        │                 └── 1:1 ParseQuality  FK parse_quality.parsed_document_id
│        ├── 自引用 1:N parent_document_id / superseded_by_document_id（版本链）
│        └── 1:N MaterialRequest          FK material_request.document_id
├── 1:N ErrorRecord                      FK error_record.case_id（可选关联 document/task/step/file）
└── 1:N StatusEvent                      FK status_event.case_id（可选关联 document/task）
```

跨主题（只出引用，不在本主题定义表结构）：

```text
Document.document_id      ←── Teammate 2: AuditRun / SourceLocator.document_version_id
ParsedDocument.parsed_document_id ←── Teammate 2: SourceLocator.parsed_document_id
FileObject.file_object_id ←── Teammate 2: SourceLocator.source_file_id
ParsedPage / ParsedBlock  ←── Teammate 2: locator 的 page_number / text_start / text_end /
                                bounding_boxes / section_path / content_hash 锚点来源
Task.task_id (AUDIT)      ←──→ Teammate 2: audit_run_id (1:1)
Document.document_id      ←── Teammate 3: HumanDecision.document_version_id
MaterialRequest.origin_decision_id ──→ Teammate 3: decision_id
```

### 3.2 基数与生命周期依赖

| 关系 | 基数 | 外键 | 生命周期与级联 |
| --- | --- | --- | --- |
| `AuditCase` — `Document` | 1:N | `document.case_id` | 案件先创建。案件归档后版本只读保留，不物理删除。保留期到期按策略整案清理。 |
| `Document` — `FileObject` | 1:N | `file_object.document_id` | 版本先创建（可为 `DRAFT`），文件记录随后预创建。版本被清理时其文件随之清理。 |
| `FileObject` — `UploadSession` | 1:1 | `upload_session.file_object_id` | 文件记录先创建。会话是短生命周期对象，`COMPLETED`/`EXPIRED` 后可按策略清理，不影响文件记录。 |
| `UploadBatch` — `Document` | N:1（实践中 1:1） | `upload_batch.document_id` | 批次与目标版本同批创建；批次 `SUBMITTED` 后目标版本不可改。批次可比版本先清理。 |
| `Document` — `Task` | 1:N | `task.document_id` | 版本 `ACCEPTED` 后才创建 `PARSE` 任务；`READY` 后由审核编排创建 `AUDIT` 任务。任务随版本保留，不随重提删除。 |
| `Task` — `TaskStep` / `TaskAttempt` | 1:N | `task_id` | 随任务创建、随任务清理。步骤与尝试均只追加，不回写覆盖。 |
| `Task` — `ParsedDocument` | 1:0..1 | `parsed_document.task_id` | 仅 `PARSE` 且 `SUCCEEDED` 的任务可有产物。产物随文档版本生命周期保留。 |
| `ParsedDocument` — `ParsedPage` / `ParsedBlock` | 1:N | `parsed_document_id` | 与产物同事务创建，随产物删除（级联）。 |
| `ParsedPage` — `ParsedBlock` | 1:N | `parsed_block.parsed_page_id` | 块可为空页码（跨页/无页概念格式），故该外键可空。 |
| `ParsedBlock` — `ParsedBlock` | 1:N 自引用 | `parent_block_id` | 表达条/款/项层级，删除父块必须级联子块。 |
| `ParsedDocument` — `ParseQuality` | 1:1 | `parse_quality.parsed_document_id` | 质量评估在产物落库后同一编排内生成；无产物不得有质量记录。 |
| `Document` — `MaterialRequest` | 1:N | `material_request.document_id` | 待办依附触发版本；新版本 `SUBMITTED` 且满足清单后置 `FULFILLED`，不删除历史待办。 |
| `Document` — `Document` | 1:N 自引用 | `parent_document_id`、`superseded_by_document_id` | 新版本创建后旧版本转 `SUPERSEDED`；旧版本及其文件、任务、产物、事件全部只读保留，禁止级联删除。 |
| `Task` — `ErrorRecord` | 1:N | `error_record.task_id` | 异常记录独立留存，任务终态后仍保留，供审核者与运营追溯。 |
| 全部对象 — `StatusEvent` | 1:N | `object_type` + `object_id` | 事件永不随对象状态变化而修改；只在整案保留期结束时随案清理。 |

创建顺序：`AuditCase` → `Document`(`DRAFT`) → `FileObject` → `UploadSession` → `UploadBatch` 提交 → `FileObject` 准入 → `Task`(`PARSE`) → `TaskStep`/`TaskAttempt` → `ParsedDocument` → `ParsedPage`/`ParsedBlock` → `ParseQuality` → `Document`(`READY`)。任一环节异常写 `ErrorRecord` + `StatusEvent`，必要时写 `MaterialRequest`。

## 4. 状态机

### 4.1 文档状态机（`Document.status`）

```text
DRAFT
  → UPLOADING
      → INTAKE_PENDING
          → ACCEPTED
              → PARSING
                  → READY                      （终态之一：可进入审核准备）
                  → MANUAL_INTAKE_REVIEW
                  → MATERIALS_REQUESTED
                  → PARSE_FAILED
          → MATERIALS_REQUESTED
          → REJECTED
      → REJECTED

MANUAL_INTAKE_REVIEW → ACCEPTED | MATERIALS_REQUESTED | REJECTED | READY
MATERIALS_REQUESTED  → SUPERSEDED（提交者以新版本响应）
PARSE_FAILED         → PARSING（人工发起受控重解析，同一输入快照）| SUPERSEDED
任意非 SUPERSEDED 状态 → SUPERSEDED
DRAFT | UPLOADING    → REJECTED（用户取消或会话过期，reason=USER_CANCELLED）
```

| 迁移 | 触发方 | 守卫条件 |
| --- | --- | --- |
| `DRAFT → UPLOADING` | 用户 | 案件有创建版本权限；`audit_scope_id` 在授权范围内。 |
| `UPLOADING → INTAKE_PENDING` | 系统 | `UploadBatch` 已提交且全部 `UploadSession = COMPLETED`；未完成传输不可提交。 |
| `INTAKE_PENDING → ACCEPTED` | 系统（准入器） | 全部必需 `FileObject.intake_status = ACCEPTED`；恰 1 个 `PRIMARY_CONTRACT`；范围一致。 |
| `INTAKE_PENDING → MATERIALS_REQUESTED` | 系统 / 人工决策 | 材料、说明或范围缺失；必须同时创建 ≥ 1 条 `MaterialRequest`。 |
| `INTAKE_PENDING → REJECTED` | 系统（准入器） | 存在 `REJECTED`/`QUARANTINED`/`UNREADABLE` 的必需文件；写安全化原因码。 |
| `ACCEPTED → PARSING` | 系统（编排器） | 版本未被替代、无未解决补件/隔离；`PARSE` 任务按幂等键创建成功。 |
| `PARSING → READY` | 系统（编排器） | `Task = SUCCEEDED`、存在 `ParsedDocument`、`ParseQuality.status = QUALIFIED`。 |
| `PARSING → MANUAL_INTAKE_REVIEW` | 系统 / 人工决策 | 质量 `INSUFFICIENT` 但可人工判断，或准入/策略冲突需裁决。 |
| `PARSING → PARSE_FAILED` | 系统（编排器） | 重试耗尽（`attempt_count >= max_attempts`）或输出无效；必须有 `failure_reason_code`。 |
| `PARSING → MATERIALS_REQUESTED` | 系统 / 人工决策 | 解析暴露材料缺失（如附件不可读、缺页）。 |
| `MANUAL_INTAKE_REVIEW → *` | 人工决策（审核者） | 审核者具备准入裁决权限；决定记录于 Teammate 3 的 `decision_id` 并写 `StatusEvent`。 |
| `PARSE_FAILED → PARSING` | 人工决策 | 仅当原因可通过重跑解决且输入快照未变；`input_manifest_hash` 必须一致，否则须新版本。 |
| `* → SUPERSEDED` | 系统 | 新版本已创建并成为案件当前版本；旧版本及其产物、任务、事件转只读。 |
| `DRAFT / UPLOADING → REJECTED` | 用户 / 定时器 | 用户取消，或全部 `UploadSession` 过期且无有效字节。 |

终态：`READY`（正向交接终态）、`REJECTED`、`SUPERSEDED`（不可再迁出）。`PARSE_FAILED` 与 `MATERIALS_REQUESTED` 是可行动的阻塞态，不是成功；界面禁止以绿色/完成样式或“未发现问题”文案呈现。

### 4.2 任务状态机（`Task.status`）

```text
QUEUED → RUNNING → SUCCEEDED            （终态）
                 → RETRYING → QUEUED
                 → FAILED               （终态）
                 → BLOCKED
QUEUED  → CANCELLED                     （终态）
RUNNING → CANCELLED
BLOCKED → QUEUED（阻塞原因解除）| FAILED | CANCELLED
RETRYING → FAILED（重试耗尽）
```

| 迁移 | 触发方 | 守卫条件 |
| --- | --- | --- |
| `→ QUEUED`（创建） | 系统（编排器） | 幂等键 `(document_id, task_type, input_manifest_hash)` 无活动任务。 |
| `QUEUED → RUNNING` | 系统（Worker） | 领取成功；创建 `TaskAttempt` 且 `attempt_count` 自增。 |
| `RUNNING → SUCCEEDED` | 系统（Worker） | 全部必需 `TaskStep = SUCCEEDED`；`PARSE` 任务须已落库 `ParsedDocument` 与 `ParseQuality`。 |
| `RUNNING → RETRYING` | 系统（Worker） | `ErrorRecord.is_retryable = true` 且 `attempt_count < max_attempts`；设置 `next_retry_at` 退避。 |
| `RETRYING → QUEUED` | 定时器 | 到达 `next_retry_at`；版本仍是案件当前版本且未被替代。 |
| `RUNNING / RETRYING → FAILED` | 系统 | 重试耗尽，或异常 `is_retryable = false`（文件损坏、加密、质量不足、范围冲突）。 |
| `RUNNING → BLOCKED` | 系统 | 依赖不可用（如安全隔离未解除、基线不可用、上游配额耗尽），需人工或策略介入。 |
| `BLOCKED → QUEUED` | 系统 / 人工决策 | 阻塞原因已解除且输入快照未变。 |
| `* → CANCELLED` | 用户 / 系统 | 用户取消未开始的版本，或版本已 `SUPERSEDED`（原因 `SUPERSEDED_BY_RESUBMISSION`）。 |

终态：`SUCCEEDED`、`FAILED`、`CANCELLED`。任务进入 `FAILED` 或 `BLOCKED` 后，`Document` 必须在同一编排内转入 `PARSE_FAILED`、`MATERIALS_REQUESTED` 或 `MANUAL_INTAKE_REVIEW` 之一，禁止永久停留 `PARSING`。

### 4.3 失败重试与幂等键

| 场景 | 幂等键 | 冲突处理 |
| --- | --- | --- |
| 创建上传会话 | `(case_id, upload_batch_id, display_name, expected_byte_size, client_nonce)` | 返回既有会话，允许续传。 |
| 提交上传批次 | `UploadBatch.idempotency_key`，作用域 `(submitted_by_user_id, case_id, "UPLOAD_BATCH")` | 请求摘要一致返回原结果；不一致返回 `IDEMPOTENCY_CONFLICT`，不创建第二个版本。 |
| 创建任务 | `Task.idempotency_key` = `(document_id, task_type, input_manifest_hash)` | 已有活动任务则返回该任务，不新建并行任务。 |
| 任务重试 | 同一 `task_id` + 新 `TaskAttempt.attempt_number` | 重试不新建任务、不覆盖既有尝试记录。 |
| 重复文件 | `(case_id, sha256, role)` 用于提示重复 | 仅提示与幂等判断，禁止自动合并跨案件或跨范围材料。 |

可自动重试：`TRANSPORT`、`ORCHESTRATION` 及 `PARSE` 中的瞬时超时/限流（`PARSE_TRANSIENT_FAILURE`）。禁止自动重试：文件加密、损坏、扫描质量不足、材料缺失、范围冲突、安全隔离、`PARSE_OUTPUT_INVALID` 中的内容性无效。内容变更后的再处理一律是新版本，不是「覆盖式重试」。

每次重试必须写 `TaskAttempt` 与 `StatusEvent`，并保持关联同一 `document_id` 与 `input_manifest_hash`。所有状态更新须在同一事务内更新对象状态、`updated_at`、`revision` 并追加 `StatusEvent`。

## 5. 前端必须展示的字段

「展示位置」按 `docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md` 的页面职责划分。未列出的字段默认不下发给业务提交者。

| 字段 | 来源实体 | 展示位置 | 展示理由 |
| --- | --- | --- | --- |
| `case_id`、`case_reference` | `AuditCase` | 列表页、详情页页头 | 用户与客服沟通、跨页跳转的稳定引用。 |
| `document_id`、`version_number` | `Document` | 列表页、详情页版本区 | 区分当前版本与历史版本，避免把旧结论当新结论。 |
| `Document.status` | `Document` | 列表页状态列、详情页状态区 | 用户判断「现在轮到谁」的核心事实。 |
| `Document.status_reason_code` → 安全文案 | `Document` / `ErrorRecord.submitter_message_key` | 详情页错误提示区 | 让用户知道为什么被阻塞及可做什么；必须为映射后文案，不暴露检测细节。 |
| `Document.updated_at` | `Document` | 列表页、详情页状态区 | 表明信息新鲜度，避免误认为系统卡死。 |
| `contract_type_code`、`audit_scope_id`（显示为范围名称） | `Document` | 详情页页头 | 确认提交的是正确审核范围。 |
| `parent_document_id`、`superseded_by_document_id` | `Document` | 详情页历史版本区 | 表达版本链与「已被新版本替代」的只读语义。 |
| `submission_note` | `UploadBatch` | 详情页版本区 | 回显用户自己的版本说明，便于核对。 |
| `file_object_id`、`display_name`、`role`、`byte_size`、`page_count` | `FileObject` | 详情页材料清单 | 用户核对材料是否齐全、角色是否正确。 |
| `FileObject.intake_status` + 安全化 `intake_reason_code` | `FileObject` | 材料清单每行状态、错误提示 | 逐文件反馈哪一份不合格，而不是整批笼统失败。 |
| `received_at` | `FileObject` | 材料清单 | 确认文件已被受控接收。 |
| `UploadSession.status`、`received_byte_size` / `expected_byte_size` | `UploadSession` | 上传进度条 | 传输可视化与断点续传引导。 |
| `UploadSession.expires_at` | `UploadSession` | 上传区提示 | 会话过期需重新选择文件，避免用户长时间无效等待。 |
| `task_id` | `Task` | 详情页处理区（可隐藏但需可用） | 状态刷新与问题上报的引用。 |
| `Task.status`（映射为阶段文案） | `Task` | 详情页进度条、列表页状态列 | 表达「正在读取 / 正在审核 / 处理失败」，不得映射为通过。 |
| `Task.updated_at` / `finished_at` | `Task` | 进度条下方 | 判断处理是否仍在推进。 |
| `TaskStep.step_code`、`status`、`progress_ratio` | `TaskStep` | 详情页进度条分段 | 长文档解析需要阶段级反馈，减少「无响应」焦虑。审核者可见全部阶段，提交者见粗粒度阶段。 |
| `Task.failure_reason_code` → 安全文案 | `Task` | 错误提示区 | 失败必须给出可行动指引（重导出、补件、等待人工）。 |
| `ParsedDocument.page_count` | `ParsedDocument` | 详情页材料详情 | 让用户确认解析覆盖了完整文档。 |
| `ParseQuality.status`（至少二值化为「可用于审核 / 需要处理」） | `ParseQuality` | 详情页状态区 | 防止低质量解析被误认为正常；不得展示为「无风险」。 |
| `ParseQuality` 各比率、`quality_policy_version` | `ParseQuality` | 审核者详情页质量摘要 | 审核者需据此判断证据可信度；不面向提交者。 |
| `ParsedDocument.source_type`、`parser_version`、`detected_language` | `ParsedDocument` | 审核者详情页 | OCR 来源与解析器版本影响证据采信。 |
| `TaskAttempt.attempt_number` 汇总（重试摘要） | `TaskAttempt` | 审核者详情页处理区 | 审核者接手时需知系统已尝试过什么。 |
| `ErrorRecord.category`、`severity`、`occurred_at`、`submitter_message_key` | `ErrorRecord` | 错误提示区（提交者）；审核者异常摘要 | 区分「系统未完成」「系统失败」「需要你补件」。 |
| `material_request_id`、`items`、`status`、`due_at` | `MaterialRequest` | 详情页补件区（置于状态说明之前） | 需要用户行动时，行动优先于状态描述。 |
| `fulfilled_by_document_id` | `MaterialRequest` | 补件区 | 表明补件已由哪个新版本响应。 |
| `StatusEvent.to_status`、`reason_code`、`actor_type`、`occurred_at` | `StatusEvent` | 详情页时间线 | 权威历史；提交者只见主体类别，审核者按权限见主体身份。 |
| `Document.revision`、`Task.revision` | `Document` / `Task` | 不可见但必须持有 | 后续写操作的乐观锁前置条件。 |

禁止下发前端：`storage_object_ref`、`content_ref`、`page_image_ref`（须换为受控短期访问能力）、`normalized_text_hash` 之外的内部摘要用途、`ErrorRecord.internal_detail`、`TaskAttempt.worker_ref`、安全检测规则细节、其他案件任何字段。

## 6. 后端必须存储的字段

分类说明：**必须持久化** = 落库且不可由其他字段重算；**派生可计算** = 可从已持久化数据推导，可物化为缓存但以源数据为准；**仅运行时/内存** = 不落库或仅短期存活。

### 6.1 必须持久化（按实体）

| 实体 | 必须持久化字段 | 唯一约束 | 索引建议 |
| --- | --- | --- | --- |
| `UploadSession` | `upload_session_id`、`case_id`、`upload_batch_id`、`file_object_id`、`status`、`expected_byte_size`、`received_byte_size`、`checksum_algorithm`、`expected_checksum`、`expires_at`、`completed_at`、`created_at`、`updated_at` | PK `upload_session_id`；UNIQUE `file_object_id` | `(upload_batch_id, status)`；`(status, expires_at)` 供过期清理定时器 |
| `UploadBatch` | `upload_batch_id`、`case_id`、`document_id`、`idempotency_key`、`submission_note`、`client_file_count`、`status`、`submitted_by_user_id`、`submitted_at`、`created_at`、`updated_at` | PK；UNIQUE `(submitted_by_user_id, case_id, idempotency_key)` | `(case_id, created_at DESC)`；`document_id` |
| `Document` | `document_id`、`case_id`、`version_number`、`parent_document_id`、`superseded_by_document_id`、`status`、`audit_scope_id`、`contract_type_code`、`intake_policy_version`、`submitted_by_user_id`、`submitted_at`、`current_parse_task_id`、`status_reason_code`、`revision`、`created_at`、`updated_at` | PK；UNIQUE `(case_id, version_number)` | `(case_id, status)`；`(status, updated_at)` 供编排扫描；`parent_document_id` |
| `FileObject` | `file_object_id`、`document_id`、`role`、`display_name`、`declared_mime_type`、`detected_mime_type`、`byte_size`、`page_count`、`sha256`、`storage_object_ref`、`intake_status`、`intake_reason_code`、`received_at`、`quarantined_at`、`created_at`、`updated_at` | PK；UNIQUE 部分索引 `(document_id) WHERE role='PRIMARY_CONTRACT'`（保证每版本恰 1 正文） | `(document_id, role)`；`(case_id via document, sha256)` 供重复检测；`intake_status` |
| `ParsedDocument` | `parsed_document_id`、`document_id`、`task_id`、`content_ref`、`normalized_text_length`、`normalized_text_hash`、`page_count`、`detected_language`、`source_type`、`parser_version`、`completed_at`、`created_at`、`updated_at` | PK；UNIQUE `task_id`；UNIQUE 部分索引 `(document_id)` 限当前有效产物 | `document_id` |
| `ParsedPage` | `parsed_page_id`、`parsed_document_id`、`file_object_id`、`page_number`、`text_start`、`text_end`、`width_px`、`height_px`、`page_image_ref`、`is_empty`、`ocr_confidence` | PK；UNIQUE `(parsed_document_id, file_object_id, page_number)` | `(parsed_document_id, text_start)` 供偏移→页码反查 |
| `ParsedBlock` | `parsed_block_id`、`parsed_document_id`、`parsed_page_id`、`parent_block_id`、`block_type`、`order_index`、`section_path`、`text_start`、`text_end`、`bounding_box`、`text_snippet_hash`、`confidence` | PK；UNIQUE `(parsed_document_id, parent_block_id, order_index)` | `(parsed_document_id, text_start, text_end)` 供 locator 区间命中；`parsed_page_id`；`parent_block_id` |
| `ParseQuality` | `parse_quality_id`、`parsed_document_id`、`status`、`text_coverage_ratio`、`ocr_confidence_ratio`、`unreadable_page_ratio`、`anchor_coverage_ratio`、`structure_completeness_ratio`、`quality_policy_version`、`reason_code`、`evaluated_at` | PK；UNIQUE `parsed_document_id` | `status` 供质量异常队列统计 |
| `Task` | `task_id`、`case_id`、`document_id`、`task_type`、`status`、`idempotency_key`、`input_manifest_hash`、`audit_run_id`、`engine_version`、`attempt_count`、`max_attempts`、`priority`、`queued_at`、`started_at`、`finished_at`、`next_retry_at`、`failure_reason_code`、`revision`、`created_at`、`updated_at` | PK；UNIQUE `(document_id, task_type, input_manifest_hash)`；UNIQUE 部分索引 `(document_id, task_type) WHERE status IN ('QUEUED','RUNNING','RETRYING','BLOCKED')`（活动任务唯一）；UNIQUE `audit_run_id`（非空时） | `(status, priority DESC, queued_at)` 供队列领取；`(status, next_retry_at)` 供重试定时器；`(case_id, task_type)` |
| `TaskStep` | `task_step_id`、`task_id`、`step_code`、`step_order`、`status`、`attempt_number`、`progress_ratio`、`started_at`、`finished_at`、`failure_reason_code` | PK；UNIQUE `(task_id, attempt_number, step_code)` | `(task_id, step_order)` |
| `TaskAttempt` | `task_attempt_id`、`task_id`、`attempt_number`、`status`、`worker_ref`、`started_at`、`finished_at`、`failure_reason_code`、`error_record_id` | PK；UNIQUE `(task_id, attempt_number)` | `(task_id, attempt_number DESC)` |
| `ErrorRecord` | `error_record_id`、`case_id`、`document_id`、`task_id`、`task_step_id`、`file_object_id`、`category`、`severity`、`reason_code`、`is_retryable`、`submitter_message_key`、`internal_detail`、`correlation_id`、`occurred_at`、`resolved_at` | PK | `(case_id, occurred_at DESC)`；`(category, severity, occurred_at DESC)` 供运营看板；`(task_id)`；`correlation_id` |
| `MaterialRequest` | `material_request_id`、`case_id`、`document_id`、`status`、`items`、`reason_code`、`origin_decision_id`、`created_by_actor_type`、`created_by_actor_id`、`due_at`、`fulfilled_by_document_id`、`created_at`、`updated_at` | PK | `(case_id, status)`；`(status, due_at)` 供到期提醒 |
| `StatusEvent` | 全部字段（追加式，不可更新/删除） | PK `status_event_id` | `(case_id, occurred_at DESC)`；`(object_type, object_id, occurred_at)`；`(document_id, occurred_at)` |

### 6.2 派生可计算（可物化为读缓存，但不作为权威）

| 字段 | 推导来源 | 说明 |
| --- | --- | --- |
| `AuditCase.upload_stage_status` | 当前 `Document.status` 投影 | 列表页快速筛选用；权威值仍是当前版本状态。 |
| `AuditCase.current_document_id` | `Document` 中 `version_number` 最大且非 `SUPERSEDED` 者 | 建议物化以避免列表页 N+1 查询，须与版本创建同事务更新。 |
| `Task.attempt_count` | `count(TaskAttempt)` | 物化以支持重试守卫的原子判断，须与尝试插入同事务自增。 |
| `Document` 的整体上传进度百分比 | `sum(received_byte_size) / sum(expected_byte_size)` | 进度条用，不落库。 |
| `ParsedPage`/`ParsedBlock` 的「偏移 → 页码」映射 | `text_start` / `text_end` 区间查找 | 供 locator 解析，靠索引在线计算。 |
| `ParseQuality.status` 的达标判定 | 各比率 + `quality_policy_version` 对应阈值 | 结论必须落库以固定历史判定；阈值本身不落本模型。 |
| 材料齐备性（是否满足准入清单） | `FileObject.role` + `intake_status` + 策略清单 | 每次准入判定时在线计算，结论体现在 `Document.status`。 |
| 未解决异常数、重试摘要 | `ErrorRecord` / `TaskAttempt` 聚合 | 审核者与运营视图在线聚合。 |

### 6.3 仅运行时 / 内存（不得作为权威事实持久化）

| 项 | 说明 |
| --- | --- |
| 分片上传的临时分片缓冲与拼装状态 | 生命周期内存/临时存储；权威事实是 `received_byte_size` 与最终 `sha256`。 |
| 短期受控下载/预览访问凭据 | 按需签发、短时效，不入库，不返回持久链接。 |
| 队列消息体与 Worker 心跳/租约 | 队列内部状态；任务权威状态只在 `Task` 表。 |
| 解析中间产物（原始 OCR 逐字结果、临时页图缓存） | 落库的是标准化文本、锚点与质量结论，不是模型中间态。 |
| 客户端上传前校验结果 | 仅辅助反馈，服务端必须独立重算。 |
| 前端本地状态（选择中的文件、未提交表单） | 不构成案件事实，未收到后端确认前不得展示为终态。 |

## 7. 跨主题衔接字段

### 7.1 本主题输出给 Teammate 2（审核规则 / 命中项 / 原文定位）

| 本主题键 | 被引用方式 | 约束 |
| --- | --- | --- |
| `document_id` | `AuditRun.document_version_id`、`SourceLocator.document_version_id` | 一次审核运行只能固定引用一个 `document_id`，且该版本必须为 `READY`。版本转 `SUPERSEDED` 后，基于它的运行与命中转只读。 |
| `Task.task_id`（`task_type = AUDIT`） | 与 `audit_run_id` 一对一 | 审核运行的执行状态、重试、失败原因由本主题 `Task` / `TaskStep` / `TaskAttempt` / `ErrorRecord` 承载；Teammate 2 不重复定义任务状态机。 |
| `parsed_document_id` | `SourceLocator.parsed_document_id` | 证据必须绑定生成它的解析产物版本。产物被新版本替代时，locator 应置 `STALE`。 |
| `file_object_id` | `SourceLocator.source_file_id` | 支持正文与附件级定位。该文件必须属于同一 `document_id`，禁止跨版本或跨案件引用。 |
| `ParsedPage.page_number` | `locator.page_number`、`bounding_boxes[].page_number` | 页码从 1 开始，且按 `(parsed_document_id, file_object_id)` 作用域，附件页码独立编号。 |
| `ParsedPage.text_start/text_end`、`ParsedBlock.text_start/text_end`、`ParsedDocument.normalized_text_length` | `locator.text_start` / `text_end` | 偏移基于同一标准化文本，0 起始、半开区间，上界为 `normalized_text_length`。locator 不得使用未经标准化的原始文本偏移。 |
| `ParsedBlock.section_path` | `locator.section_path` | 章节层级由解析产物提供，Teammate 2 直接复用，不自行推断条款编号。 |
| `ParsedBlock.bounding_box`（归一化 `[0,1]`）、`ParsedPage.width_px/height_px` | `locator.bounding_boxes` | 坐标统一归一化，阅读器按页尺寸换算。 |
| `ParsedBlock.text_snippet_hash`、`ParsedDocument.normalized_text_hash` | `locator.content_hash` | locator 用它校验锚点是否漂移，决定 `locator_status` 为 `VERIFIED` 还是 `STALE`。 |
| `ParseQuality.status`、`anchor_coverage_ratio`、`ParsedDocument.source_type` | 命中项的证据可信度与人工路由输入 | 质量非 `QUALIFIED` 或 `source_type = OCR` 且置信度低时，Teammate 2 必须提升 `review_requirement`，不得自动放行。 |

`locator` 的完整结构、`locator_status` 语义与有效锚点组合规则由 Teammate 2 定义；本主题只保证上述锚点基础字段的存在性、值域与稳定性。

### 7.2 本主题输出给 Teammate 3（人机交互决策）

| 本主题键 | 被引用方式 | 约束 |
| --- | --- | --- |
| `case_id` | `HumanTask.case_id`、`HumanDecision.case_id` | 人工待办与决定的案件归属。 |
| `document_id` | `HumanDecision.document_version_id`、`HumanTask.document_version_id` | 人工决定必须固定关联被决定的文档版本。若该版本已 `SUPERSEDED`，后端须拒绝将旧上下文的决定写为当前结论。 |
| `Task.task_id`、`Task.status`、`TaskStep`、`TaskAttempt` 摘要 | 人工交接包中的「系统已尝试什么」 | 审核者接手时必须能区分「系统未完成」「系统失败」「候选结果已生成」。 |
| `ErrorRecord`（`category`、`severity`、`reason_code`、`is_retryable`） | 人工待办的路由原因与升级依据 | `PARSE_FAILED`、`QUALITY` 类异常是强制人工路由条件之一。 |
| `ParseQuality.status` 及各比率 | 人工决定的前置证据充分性判断 | 质量 `INSUFFICIENT` 时，禁止在无人工确认的情况下推进到交付。 |
| `MaterialRequest.material_request_id`、`items`、`status` | 人工「要求补件」决定的落地载体 | 人工发起补件时，Teammate 3 写 `decision_id`，本主题据此创建 `MaterialRequest` 并回填 `origin_decision_id`；`Document` 转 `MATERIALS_REQUESTED`。 |
| `MaterialRequest.fulfilled_by_document_id` | 重提闭环 | 提交者重提生成新 `document_id`，回填此字段并将待办置 `FULFILLED`。 |
| `StatusEvent` | 案件时间线的上传/处理段 | Teammate 3 的决定事件与本主题状态事件共用同一时间线语义（`object_type` + `object_id` + `occurred_at`）。 |

### 7.3 本主题引用其他主题的键（只出引用，不定义）

| 外部键 | 定义方 | 本主题用途 |
| --- | --- | --- |
| `finding_id` | Teammate 2 | 预留：当补件请求源自某条命中项时，`MaterialRequest.items[].origin_finding_id` 可引用该命中，供审核者追溯补件依据。本主题不定义其结构与状态。 |
| `audit_run_id`、`baseline_id` | Teammate 2 | `Task.audit_run_id` 登记 `AUDIT` 任务与运行的一对一关系；基线不可用导致的 `BLOCKED` 原因码由本主题记录，基线本体不在此定义。 |
| `decision_id` | Teammate 3 | `MaterialRequest.origin_decision_id`；`MANUAL_INTAKE_REVIEW` 迁出、`PARSE_FAILED → PARSING` 受控重解析均须关联触发决定。 |
| `case_id`、`audit_scope_id` | 案件与策略模型（Lead 汇总层） | 本主题作为外键引用，不定义案件全生命周期状态与审核范围本体。 |

### 7.4 命名一致性承诺

- 文档版本主键统一为 `document_id`（不使用 `document_version_id` 作为本主题字段名）。对外被 Teammate 2/3 以 `document_version_id` 引用时，两者指向同一值；建议 Lead 在汇总层统一为其中一个名称。
- 任务主键统一为 `task_id`；`AUDIT` 任务与 `audit_run_id` 一对一但不同名，`task_id` 是执行态标识，`audit_run_id` 是审核语义标识。
- 时间字段一律 `*_at` + UTC ISO-8601；枚举一律大写下划线。
- 原因码集中在 `ReasonCode` 一个枚举内，三个主题共用同一码表，新增码须在 Lead 汇总层登记。

<!--CONT-->








