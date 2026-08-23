# 后端 MVP Agent Team 实施 Plan（2026-08-15）

## 目标

依据 `docs/08_api_spec/api_spec-v1.0.md` 与 `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`，在 `backend/` 实现可运行 MVP：Workflow、HITL、API/Schema/Service 集成与整体链路测试。

## 分工与文件所有权

1. Teammate 1：`backend/app/workflow/` 与对应单元测试。
2. Teammate 2：`backend/app/hitl/` 与对应单元测试。
3. Teammate 3：`backend/app/api/`、`backend/app/schemas/`、`backend/app/services/`、`backend/app/main.py`、`pyproject.toml`、`.env.example`。
4. Teammate 4：前三位完成后，仅负责 `backend/tests/e2e/`、`backend/tests/conftest.py` 和 `docs/11_integration_testing/` 测试记录。

## 模型与配置

- 模型采用 LangChain `ChatOpenAI` 兼容适配层，endpoint、模型、密钥分别读取 `DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`DEEPSEEK_API_KEY`。
- 默认模型：`deepseek-v4-flash`；默认 endpoint：`https://api.deepseek.com`。
- 真实 key 只写入本地 `backend/.env`，不进入源码、测试、文档或 Git。
- 当前 LangChain MCP 无可用 resources/templates，已记录；实现需把具体 SDK 依赖与调用集中在适配层，测试使用离线 stub。

## 实施步骤

1. 并行启动前三位 Terra teammate，按独立文件所有权实现。
2. 等前三位完成并关闭后，启动第四位 Terra teammate 编写整体链路测试。
3. 全部 teammate 完成并关闭后，Lead 统一使用 `uv` 安装依赖、启动 backend，并运行 MVP 完整测试与 `/healthz`/API smoke。
4. 将验证结果与风险写入 `docs/11_integration_testing/`；Lead 不代写主题实现。

## 验证与风险

- 验证：`uv run --extra test pytest`、backend 启动、`/healthz`、创建案件 smoke。
- 风险：LangChain MCP 当前不可用；DeepSeek 模型名和 SDK 兼容性需可配置并通过适配层隔离。
- 回滚：实现限于 `backend/`，按文件所有权回退，不修改现有 frontend/docs。
