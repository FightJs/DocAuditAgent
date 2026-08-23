# HITL 模块实施记录（backend/app/hitl/）

- **日期**：2026-08-15
- **责任人**：Agent Team Teammate 2（人工交互 HITL 流程）
- **Plan 来源**：`docs/00_setup/plans/2026-08-15-backend-mvp-agent-team-plan.md`
- **文件所有权**：`backend/app/hitl/` 与 `backend/tests/unit/hitl/`；未触碰 api/schemas/services/main.py/pyproject.toml（Teammate 3）与 tests/e2e、conftest（Teammate 4）。

## 1. 目标

依据 HITL 架构规范与 API 契约，实现后端 MVP 的人工交互子域：中断开启与待办去重、待办认领、append-only 人工决定、乐观并发/幂等、上下文失效后的受控恢复拒绝、审计事件，以及 LangGraph 恢复适配缝。

## 2. 输入

- `docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md`（中断点、恢复前置条件、节点幂等约束）
- `docs/07_data_model/human_interaction_decision_models.md`（决定追加不可变、版本绑定、乐观锁、幂等键）
- `docs/08_api_spec/api_spec-v1.0.md`（6.3 统一决定入口、6.4 HITL 恢复边界、第 8 节错误码）
- `docs/06_system_architecture/backend_service_architecture_spec-v1.0.md`（人工决定执法与审计边界）

## 3. 产出

| 文件 | 职责 |
| --- | --- |
| `backend/app/hitl/enums.py` | 中断点、路由原因、待办/中断/决定状态、动作与角色枚举（值对齐 API 小写 snake_case 约定） |
| `backend/app/hitl/errors.py` | 领域错误，code 与 api_spec 第 8 节错误码一一对应，API 层可直接映射 envelope |
| `backend/app/hitl/models.py` | ContextTriple、ReviewAssignment、HitlInterrupt、HumanDecision、AuditEvent、DecisionOutcome |
| `backend/app/hitl/store.py` | MVP 内存存储：append-only 决定/审计、幂等键唯一索引、待办 dedup_key 去重索引 |
| `backend/app/hitl/policies.py` | ContextValidator / AuthorizationPolicy 协议 + MVP 默认授权矩阵与测试用静态校验器 |
| `backend/app/hitl/graph.py` | GraphResumeAdapter 协议、ResumeCommand、离线 StubGraphAdapter、JSON 可序列化校验 |
| `backend/app/hitl/service.py` | HitlService：open_interrupt / accept_assignment / submit_decision / invalidate_run |
| `backend/tests/unit/hitl/` | 24 个单元测试（stdlib unittest 编写，pytest 可直接收集） |

## 4. 关键决策

1. **纯 stdlib 实现，LangGraph 依赖集中于 `graph.py` 适配层**。LangChain MCP 当前不可用（团队 plan 已记录风险），SDK 签名未经官方复核；适配层协议满足后即可替换为真实 LangGraph 恢复实现，领域逻辑不变。
2. **恢复边界 = ContextTriple（版本 + 基线 + 运行）**。决定提交与图恢复前强制校验：上下文与待办绑定一致且经 ContextValidator 判定仍当前有效，否则 `run_superseded` / `stale_human_task`。
3. **中断节点重执行幂等**：open_interrupt 以 `thread_id + point` 去重，重执行返回既有中断与待办，不重复建单、不重复审计。
4. **决定 append-only**：撤回/更正新增决定并将旧决定置 `is_current=False, result=superseded`，历史只读保留；幂等键重放返回原决定，同键不同请求摘要返回 `idempotency_conflict`。
5. **先落库后恢复**：submit_decision 在决定落库、审计事件与投影更新完成后才调用 GraphResumeAdapter.resume；转交/升级保持人工路径（创建后继待办、原待办 superseded），不触发图恢复。
6. **案件状态不由本模块裁决**：DecisionOutcome.case_status_effect 仅为建议效果，案件聚合与终态由 services 层（Teammate 3）负责，保证“Agent 完成 ≠ approved”。
7. **MVP 默认授权矩阵**：approve/reject 仅 approver/expert；submitter 无复核动作；operator/admin 不获得专业审批权。案件级细粒度授权由上层叠加。

## 5. 验证

- `python3 -m unittest discover -s tests/unit/hitl -t .`（在 backend/ 下执行）：24 个测试全部通过（2026-08-15）。
- 测试覆盖：中断开启/去重/活跃待办唯一、payload JSON 校验、认领冲突与幂等、决定权限/乐观锁/幂等重放/同键冲突、approve 前置（未处置风险项、证据不完整、空证据引用）、撤回/更正 append-only、转交后继待办、恢复使用同一 thread_id 且不重复恢复、invalidate_run 后拒绝恢复且历史保留。
- 注：`pyproject.toml` 由 Teammate 3 提供后，应使用 `uv run --extra test pytest` 复跑（unittest 风格测试可被 pytest 收集）。

## 6. 待解决风险

- LangGraph 真实 SDK 的 interrupt/checkpoint/resume 语义须在接入前经官方文档复核（hitl arch 9.2 既有风险），当前仅有离线 stub 适配。
- InMemoryHitlStore 为单进程 MVP；生产需替换为持久化存储并保留幂等键/去重键唯一约束。
- ContextValidator/AuthorizationPolicy 当前为静态/默认实现，需 Teammate 3 在 services 层接入真实案件、运行与权限数据。

## 7. 下一阶段交付物

- Teammate 3：将 HitlService 接入 API 层（api_spec 6.1-6.4），注入真实 ContextValidator/AuthorizationPolicy。
- Teammate 4：e2e 链路测试覆盖“中断 → 待办 → 决定 → 恢复/拒绝恢复”及并发、过期场景。
