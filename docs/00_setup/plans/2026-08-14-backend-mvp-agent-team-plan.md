# 后端 MVP Agent Team 实施 Plan

## 目标

依据 `docs/08_api_spec/api_spec-v1.0.md` 与 `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`，在 `backend/` 实现可运行的 MVP 后端：工作流编排、HITL 人工交互、API/Schema/Service 集成和端到端功能测试。

## 团队分工与文件所有权

1. Teammate 1：整体 Workflow 流程；负责 `backend/app/workflow/` 及其单元测试。
2. Teammate 2：人工交互 HITL 流程；负责 `backend/app/hitl/` 及其单元测试。
3. Teammate 3：API、Schema、Service 集成；负责 `backend/app/api/`、`backend/app/schemas/`、`backend/app/services/` 和项目运行配置。
4. Teammate 4：整体链路功能测试；在前三项完成后负责 `backend/tests/e2e/`、测试夹具及测试记录，不修改核心实现。

## 实施顺序

1. 先核对 LangChain MCP；当前会话若无可调用资源，则记录阻塞并只采用可验证的 ChatOpenAI 兼容配置和既有文档约束。
2. 并行启动前三位 Terra teammate，严格按文件所有权实现，密钥仅从 `backend/.env` 读取。
3. 等前三位完成并关闭后，再启动第四位 Terra teammate 编写并执行整体链路功能测试。
4. Lead 等全部 teammate 完成并关闭后，统一使用 `uv` 启动 backend，执行 MVP 测试和健康检查；不在 Lead 侧编写主题实现。

## 统一技术边界

- Python 后端使用 `uv` 管理依赖和运行环境；API 使用 FastAPI 风格的 HTTP 契约。
- 模型配置从 `backend/.env` 读取，提供不含真实值的 `backend/.env.example`；真实 key 不进入源码、测试夹具、文档或 Git。
- Kimi 兼容 ChatOpenAI 的 endpoint、模型名和超时均配置化；不能在测试中强制调用外部模型，测试默认使用可控 stub。
- 服务端是状态、版本、运行、权限、人工决定和审计事实的权威方；HITL checkpoint 不替代业务记录。

## 验证与风险

- 验证：`uv run pytest`、API 健康检查、上传→解析→审核→人工决定→交付/补件的主链路测试。
- 风险：LangChain MCP 当前不可用；Kimi endpoint/模型名可能随官方版本变化，需通过环境配置和适配层隔离。
- 回滚：所有实现限于 `backend/`；按 teammate 文件所有权回退，不修改既有 docs 或 frontend。
