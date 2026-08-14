# 人机交互流程数据模型规范

- **文档目的**：定义 DocAuditAgent 人工复核环节（approve / edit / reject 等）的权威数据契约，覆盖复核会话、人工决策记录、编辑内容、驳回理由、决策审计日志、批量操作与 HITL 中断/恢复，作为前端工作台与后端持久化的共同输入输出规范。
- **版本**：v1.0
- **日期**：2026-08-04
- **上游输入**：
  - `docs/04_core_interaction_flows/human_approval_state_flow.md`（人工动作语义、权限、异常与并发规则）
  - `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`（HITL 汇总与共同约束）
  - `docs/04_core_interaction_flows/interaction_flow_summary.md`（端到端链路衔接）
  - `docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md`（`thread_id`、checkpoint、恢复与幂等约束）
  - `docs/06_system_architecture/frontend_design_spec-v1.0.md`（P6 工作台、P7 决定确认页展示语义）
  - `docs/07_data_model/upload_and_task_models.md`（`document_id` / `task_id`，Teammate 1）
  - `docs/07_data_model/audit_rule_hit_result_model_spec-v1.0.md`（`finding_id` / `rule_id` / `rule_version`，Teammate 2）
- **下游消费方**：API 规范（决策提交、批量提交、恢复接口与冲突错误契约）、后端实现（持久化、事务边界、幂等与审计存储）、前端实现（工作台、决策按钮区、编辑器、历史时间线、批量反馈）、集成测试（并发、幂等、撤销、超时场景）。
- **边界**：本文件只定义数据契约，不定义接口路径、数据库产品、ORM、页面布局或权限系统实现，不新增自动批准能力。

## 0. 通用约定

| 约定 | 结论 |
| --- | --- |
| 标识 | 所有 `*_id` 为不可猜测的 UUID 字符串。本主题定义并拥有 `decision_id`。 |
| 时间 | 所有时间字段以 `*_at` 结尾，UTC ISO-8601，带时区。 |
| 枚举 | 全部大写下划线，如 `APPROVE`、`PENDING_REVIEW`。 |
| 追加不可变 | `Decision`、`DecisionAuditLog`、`DecisionEdit`、`DecisionRejection` 为 append-only。撤销与改判通过新增记录表达，禁止原地更新或删除历史事实。 |
| 版本绑定 | 每条人工记录必须固定关联 `document_id + task_id + ruleset_version`（Finding 级再绑定 `rule_version`）。上下文失效后旧记录只读。 |
| 权威性 | 服务端是状态唯一裁决方。前端提交的可执行动作、结果状态与权限结论均以服务端返回为准；LangGraph checkpoint 不是业务决策记录。 |
| 并发 | 所有写操作使用乐观锁：请求必须回传 `expected_revision`（Finding 级）或 `expected_session_revision`（会话级）；冲突返回 `STALE_REVISION`，不得静默覆盖。 |

## 1. 实体清单

本主题共 8 个实体：`ReviewSession`、`Decision`、`DecisionEdit`、`DecisionRejection`、`DecisionAuditLog`、`BulkDecisionBatch`、`BulkDecisionItem`、`HitlInterrupt`。

### 1.1 `ReviewSession`（复核工作台会话）

一次审核者对某个 `task_id` 的人工复核工作单元。它承载责任归属与工作台上下文有效性，**不承载**案件级审批结论。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `session_id` | string(UUID) | 是 | 主键 | 复核会话标识。 |
| `task_id` | string(UUID) | 是 | 外键 → `Task`（Teammate 1），不可变 | 被复核的审核任务。 |
| `document_id` | string(UUID) | 是 | 外键 → `Document`（Teammate 1），不可变 | 被复核的文档版本，冻结于会话创建时。 |
| `case_id` | string(UUID) | 是 | 外键 → `AuditCase` | 所属案件，用于队列聚合与权限范围。 |
| `ruleset_version` | string | 是 | 版本串，不可变 | 会话创建时固定的规则集版本快照。 |
| `session_status` | enum | 是 | `OPEN`、`IN_PROGRESS`、`SUBMITTED`、`ABANDONED`、`EXPIRED`、`SUPERSEDED` | 会话生命周期，见 3.3。 |
| `assigned_actor_id` | string(UUID) | 否 | 外键 → 主体；`OPEN` 未认领时为空 | 当前责任人。 |
| `assigned_actor_role` | enum | 否 | `REVIEWER`、`SENIOR_REVIEWER`、`SPECIALIST`、`POLICY_OWNER`、`ADMIN` | 认领时的角色快照。 |
| `queue_code` | string | 是 | 稳定业务码，如 `REVIEW_DEFAULT`、`ESCALATION` | 承接队列，决定待办可见范围。 |
| `routing_reasons` | enum[] | 是（可为空） | `REDLINE`、`HIGH_SEVERITY`、`LOW_CONFIDENCE`、`EVIDENCE_GAP`、`PARSE_QUALITY`、`RULE_CONFLICT`、`SUBMITTER_OBJECTION`、`MANUAL_ROUTE` | 进入人工的触发原因，前端必须展示。 |
| `priority` | enum | 是 | `NORMAL`、`HIGH`、`URGENT` | 待办优先级。 |
| `total_finding_count` | int32 | 是 | ≥ 0 | 会话范围内 Finding 总数（派生）。 |
| `pending_finding_count` | int32 | 是 | ≥ 0 | 尚未处置的 Finding 数（派生），为 0 才允许任务级 APPROVE。 |
| `context_valid` | boolean | 是 | true / false | 上下文是否仍有效（派生：文档未 `SUPERSEDED`、任务未失效、规则集未变更）。为 false 时决策入口必须禁用。 |
| `session_revision` | int32 | 是 | ≥ 0 | 会话级乐观并发版本。 |
| `parent_session_id` | string(UUID) | 否 | 外键 → `ReviewSession`，自引用 | 转交、升级或重开前的会话，构成责任链。 |
| `superseded_by_session_id` | string(UUID) | 否 | 外键 → `ReviewSession`，自引用 | 替代本会话的后继会话。 |
| `created_at` | timestamp | 是 | UTC ISO-8601 | 待办生成时间，等待时长基准。 |
| `claimed_at` | timestamp | 否 | UTC ISO-8601 或 null | 认领时间。 |
| `due_at` | timestamp | 否 | UTC ISO-8601 或 null | 处理期限（若业务定义 SLA）。 |
| `expires_at` | timestamp | 是 | UTC ISO-8601 | 认领租约到期时间；到期未提交则回到 `OPEN` 或转 `EXPIRED`。 |
| `closed_at` | timestamp | 否 | UTC ISO-8601 或 null | 会话结束时间。 |

约束：同一 `task_id` 在任一时刻最多存在 1 条 `session_status IN (OPEN, IN_PROGRESS)` 的会话；转交/升级必须先创建后继会话，再将原会话置为 `SUPERSEDED`，禁止原地改写 `assigned_actor_id`。

### 1.2 `Decision`（人工决策记录）

一次不可变的人工处置动作，主键 `decision_id`。它是人机交互的核心事实；Finding 与任务的当前状态是从有效 Decision 投影出的读模型。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `decision_id` | string(UUID) | 是 | 主键，本主题拥有 | 决策标识，跨主题引用键。 |
| `session_id` | string(UUID) | 是 | 外键 → `ReviewSession` | 发起该决策的会话。 |
| `task_id` | string(UUID) | 是 | 外键 → `Task`（Teammate 1） | 所属审核任务，落库冗余。 |
| `document_id` | string(UUID) | 是 | 外键 → `Document`（Teammate 1） | 被决策的文档版本，落库冗余。 |
| `scope_type` | enum | 是 | `FINDING`、`TASK` | 决策粒度：单条命中项处置，或任务级最终结论。 |
| `finding_id` | string(UUID) | 否 | 外键 → `Finding`（Teammate 2）；`scope_type=FINDING` 时必填 | 被处置的命中项。 |
| `rule_version` | string | 否 | 版本串；`scope_type=FINDING` 时必填 | 决策当时该 Finding 依据的规则版本快照。 |
| `ruleset_version` | string | 是 | 版本串 | 决策当时的规则集版本快照。 |
| `action` | enum | 是 | 见 2.1 动作枚举表 | 人工动作。 |
| `decision_result` | enum | 是 | `ACCEPTED`、`REJECTED_STALE`、`REJECTED_UNAUTHORIZED`、`REJECTED_VALIDATION`、`SUPERSEDED` | 服务端受理结果。只有 `ACCEPTED` 产生状态效果。 |
| `is_current` | boolean | 是 | true / false | 是否为该范围当前有效决策，见 2.3 历史/当前建模。 |
| `actor_id` | string(UUID) | 是 | 外键 → 主体 | 操作者。 |
| `actor_role` | enum | 是 | 同 `assigned_actor_role` | 操作者当时的角色快照，不随后续权限变更回填。 |
| `authorization_scope` | JSON object | 是 | 结构化：合同类型、案件范围、风险等级、审批额度 | 决策时的授权快照，作为事后责任解释依据。 |
| `reason_text` | string | 否 | 自由文本；`REJECT`、`EDIT`、`DEFER`、`ESCALATE`、`WITHDRAW` 必填 | 人工理由。`APPROVE` 建议必填，最小长度由产品定义。 |
| `evidence_refs` | JSON array | 是（可为空） | 每项含 `ref_type`（`FINDING`、`LOCATOR`、`RULE`、`SUGGESTION`、`AUTHORIZATION`）与 `ref_id` | 支撑该决策的引用。任务级 `APPROVE` 不得为空。 |
| `accepted_suggestion_id` | string(UUID) | 否 | 外键 → `Suggestion`（Teammate 2） | 采纳的 AI 建议；仅 `EDIT`/`APPROVE` 适用。 |
| `previous_decision_id` | string(UUID) | 否 | 外键 → `Decision`，自引用；`WITHDRAW`、`REOPEN` 必填 | 被撤销或替代的决策。 |
| `supersedes_decision_id` | string(UUID) | 否 | 外键 → `Decision`，自引用 | 同范围内被本决策取代的上一条有效决策。 |
| `target_queue_code` | string | 否 | 队列码；`ESCALATE`、`REASSIGN` 至少一项非空 | 转交/升级目标队列。 |
| `target_actor_id` | string(UUID) | 否 | 外键 → 主体 | 转交/升级目标责任人。 |
| `defer_until_at` | timestamp | 否 | UTC ISO-8601；`DEFER` 必填 | 挂起到期时间，到期后重回待办。 |
| `conditions` | JSON array | 是（可为空） | 每项含条件文本与是否对提交者可见 | 附条件批准的限制说明。 |
| `expected_revision` | int32 | 否 | ≥ 0；`scope_type=FINDING` 必填 | 提交时客户端持有的 `Finding.revision`，用于乐观锁。 |
| `expected_session_revision` | int32 | 否 | ≥ 0；`scope_type=TASK` 必填 | 提交时客户端持有的 `ReviewSession.session_revision`。 |
| `expected_state` | enum | 否 | Finding 人工处置状态枚举，见 3.1 | 客户端认为的当前状态，服务端二次校验，防止基于过期视图处置。 |
| `idempotency_key` | string | 是 | 1–128 字符；`(actor_id, session_id, scope_type, finding_id, action, idempotency_key)` 唯一 | 幂等键，重复提交只产生 1 条 `ACCEPTED` 决策。 |
| `bulk_batch_id` | string(UUID) | 否 | 外键 → `BulkDecisionBatch` | 批量操作产生的决策指向其批次。 |
| `interrupt_id` | string(UUID) | 否 | 外键 → `HitlInterrupt` | 该决策作为哪个 HITL 中断的恢复输入。 |
| `submitted_at` | timestamp | 是 | UTC ISO-8601 | 客户端提交时间。 |
| `recorded_at` | timestamp | 是 | UTC ISO-8601 | 服务端权威落库时间，时间线排序以此为准。 |

<!--CONT-->

