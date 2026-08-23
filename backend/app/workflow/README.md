# `app.workflow` — 审核运行 HITL 工作流模块

后端 MVP Agent Team（2026-08-15 Plan）Teammate 1 交付。实现 LangGraph HITL
审核主链路：prepare → agent_review → triage → human_review(interrupt) →
finalize，覆盖 `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`
§4 的主链路与 `docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md`
的中断/恢复/幂等约束。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `constants.py` | 运行状态、严重度、路由原因、人工动作、结果的常量（小写 snake_case，对齐 API 规范 v1.0）。 |
| `state.py` | LangGraph 状态 schema、中断/恢复数据契约、`validate_resume_payload`。全部 JSON 可序列化。 |
| `triage.py` | 强制人工路径判据（数据模型 §5.3 + 运行级解析质量/规则覆盖）。纯函数，无 LLM。 |
| `settings.py` | `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `DEEPSEEK_API_KEY` 环境配置；默认 `https://api.deepseek.com` + `deepseek-v4-flash`。 |
| `llm.py` | 适配层：`AgentReviewer` 协议、`build_chat_model`（ChatOpenAI 兼容）、`LLMAgentReviewer`、模型输出 JSON 解析与保守归一化。 |
| `nodes.py` | 图节点与条件路由；中断 payload 构建。 |
| `graph.py` | `build_audit_workflow(reviewer, checkpointer=...)` 编译 StateGraph。 |
| `runner.py` | `AuditWorkflowRunner.start/resume/snapshot` 集成 API；恢复前校验 + `resume_guard` 钩子。 |

## 给其他 Teammate 的集成契约

- **Teammate 3（services/api）**：
  - 依赖声明（请加入 `pyproject.toml`）：`langgraph>=1.2,<2`、
    `langchain-core>=1.5,<2`、`langchain-openai>=1.5,<2`；test extra：`pytest`。
  - 生产环境必须注入持久化 checkpointer（Postgres/Redis saver）；默认
    `InMemorySaver` 仅用于 MVP 开发与测试。
  - 恢复前必须由 services 完成权限/责任/版本/运行有效性校验并持久化权威
    Decision；`decision_id` 作为 resume 值引用传入。可将校验挂到
    `AuditWorkflowRunner(resume_guard=...)`。
  - 图不写案件业务状态；`outcome` 是路由结果投影，`approved` 只可能由已校验的
    人工 resume 产生。
- **Teammate 2（hitl）**：finding 级的 edit/withdraw 等决定在图暂停期间由
  services/hitl 处理；图只接受路由相关的五种 resume 动作
  （approve/reject/request_supplement/transfer/escalate）。
- **Teammate 4（e2e）**：用 `AuditWorkflowRunner` + 离线 stub reviewer 驱动；
  `thread_id == audit_run_id`；中断 payload 见 `RunSnapshot.interrupt_payload`。

## 已知限制

- 节点内防御性校验若触发（runner 预校验被绕过），LangGraph 会消费 resume 值，
  该运行不可再恢复 —— 必须由 services 标记失败/替代。runner 预校验使正常路径
  不会进入此状态。
- LangChain 官方文档 MCP 设计期不可用；SDK 签名（langgraph 1.2.11 /
  langchain-openai 1.5.1 实测可用）上线前需按官方文档复核。
