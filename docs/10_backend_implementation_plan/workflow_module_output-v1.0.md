# 后端 MVP 阶段输出：workflow 模块（Teammate 1）v1.0

- 日期：2026-08-15
- 上游 Plan：`docs/00_setup/plans/2026-08-15-backend-mvp-agent-team-plan.md`
- 负责范围：`backend/app/workflow/` 与对应单元测试（文件所有权边界内）

## 1. 目标

依据 `docs/08_api_spec/api_spec-v1.0.md` 与
`docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`，在
`backend/app/workflow/` 实现 LangGraph HITL 审核工作流：准备与准入校验、
Agent 候选风险生成（LLM 适配层）、确定性分流、人工中断/恢复与按决定路由，
配套离线单元测试。

## 2. 输入

- `docs/08_api_spec/api_spec-v1.0.md`：标识与枚举词汇（小写 snake_case）、
  版本/运行/基线上下文、人工动作集。
- `docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md`：
  HITL 流程边界（文档版本+基线+运行）、中断恢复约束（节点重执行幂等、
  payload 最小化、JSON 可序列化、不吞中断）。
- `docs/07_data_model/audit_rule_hit_result_model_spec-v1.0.md` section 5.3：
  强制人工路径判据。
- `docs/06_system_architecture/backend_service_architecture_spec-v1.0.md`：
  后端权威边界（图不写业务状态、不持久化决定）。

## 3. 交付物

- `backend/app/workflow/`：`constants.py`、`state.py`、`triage.py`、
  `settings.py`、`llm.py`、`nodes.py`、`graph.py`、`runner.py`、`README.md`。
- `backend/tests/unit/workflow/`：`test_triage.py`（19）、`test_graph.py`（16）、
  `test_runner.py`（9）、`test_llm.py`（12），共 56 条单元测试。
- 附带创建空 `backend/app/__init__.py` 与 `backend/tests/__init__.py` 等包标记
  （空文件，供 Teammate 2/3/4 共享目录使用）。

## 4. 关键决策

1. **thread_id 即 audit_run_id**：HITL 恢复边界与运行一一对应；runner 强制绑定。
2. **resume 值先校验后入图**：实测 LangGraph 在节点失败时会消费 resume 值且无法
   以新值重试，因此 `AuditWorkflowRunner.resume` 在调用 `Command(resume=...)` 前完成
   形状/动作/理由/目标队列校验；节点内校验仅作防御，触发即视为运行不可恢复。
3. **图不批准任何事项**：自动路径终态只有 `ready_for_delivery`；`approved` 等
   outcome 仅作为已校验人工 resume 的投影，案件级状态转换由 services 执法。
4. **幂等策略**：全部节点更新采用从 checkpoint 状态计算的覆盖语义；图本身不创建
   待办、不发通知、不写决定（副作用归 services），满足中断节点重执行约束。
5. **transfer/escalate 以条件边回到 human_review 再次中断**，节点单次执行只中断
   一次，不在节点内循环中断。
6. **LLM 适配层集中于 `llm.py`**：`AgentReviewer` 协议 + ChatOpenAI 兼容客户端
   （DeepSeek env 配置）；测试使用 stub 与 `GenericFakeChatModel`，全程离线。
7. **模型输出保守归一化**：缺失/未知字段归一为 unknown/failed，使分流强制人工，
   绝不让畸形模型输出静默自动通过。

## 5. 验证

- 环境：`uv venv`（CPython 3.12.13）+ `uv pip install langgraph langchain-openai pytest`
  （langgraph 1.2.11、langgraph-checkpoint 4.2.0、langchain-core 1.5.5、
  langchain-openai 1.5.1、pytest 9.1.1）。
- 命令：`PYTHONPATH=backend python -m pytest backend/tests/unit/workflow -v`
- 结果：**56 passed**（覆盖自动路由、强制人工各判据、中断 payload 最小性、
  approve/reject/request_supplement/transfer/escalate 路由、恢复前校验、
  前置条件失败、Agent 失败、恢复不重复调用 LLM、线程隔离、适配层解析与归一化）。
- 注：`backend/pyproject.toml` 归 Teammate 3；上述依赖需由其声明后，`uv run`
  路径方可直接运行本模块测试。

## 6. 待解决风险

| 风险 | 说明与去向 |
| --- | --- |
| LangChain MCP 不可用 | 设计期无法核验官方文档；SDK 签名以 langgraph 1.2.11 实测为准，上线前须官方复核（承接既有规范风险项）。 |
| 生产 checkpointer 未定型 | 默认 InMemorySaver 仅供 MVP/测试；services 需注入持久化 saver，属 Teammate 3 集成决策。 |
| 中毒运行语义 | 绕过 runner 预校验导致的节点校验失败会使运行不可恢复；API 层不得绕过 runner。 |
| 解析结果结构未定 | `parsed_document` 暂为不透明 dict 透传；待解析主题数据模型落地后收紧契约。 |

## 7. 下一阶段交付物（对 Teammate 4 / Lead）

- Teammate 4 可基于 `AuditWorkflowRunner` + stub reviewer 编写 e2e 链路用例。
- Lead 统一 `uv sync`（依赖见 `backend/app/workflow/README.md`）后重跑
  `backend/tests/unit/workflow` 并纳入整体 MVP 验证。
