# 项目初始化与规范

## 1. 初始化范围

本阶段仅建立项目目录、文档分层与协作规范。不得生成前端或后端业务代码。

项目顶层目录：

```text
DocAuditAgent/
├── frontend/                         # 前端实现边界
├── backend/                          # 后端实现边界
├── docs/                             # 全生命周期文档
├── .codex/                           # Codex 项目级配置
└── AGENTS.md                         # Agent Teams 协作规范
```

## 2. 文档分层

| 阶段 | 目录 | 必需输出 |
| --- | --- | --- |
| 初始化与规则 | `docs/00_setup/` | 初始化说明、项目规则、实施 Plan |
| 业务调研 | `docs/01_business_research/` | 用户、场景、需求与约束调研结论 |
| 竞品分析 | `docs/02_competitive_analysis/` | 竞品对比、机会点与差异化结论 |
| 业务问题建模 | `docs/03_business_problem_modeling/` | 问题定义、角色、流程与成功指标 |
| 核心交互链路设计 | `docs/04_core_interaction_flows/` | 主链路、异常链路、状态转换说明 |
| 产品原型规范 | `docs/05_product_prototype_spec/` | 页面、组件、文案与交互规范 |
| 系统架构设计 | `docs/06_system_architecture/` | 模块边界、技术选型、依赖与风险 |
| 数据模型 | `docs/07_data_model/` | 实体、字段、关系、约束与迁移策略 |
| API 规范 | `docs/08_api_spec/` | 接口契约、鉴权、错误码与版本策略 |
| 前端实现计划 | `docs/09_frontend_implementation_plan/` | 页面、状态、组件、测试与里程碑 |
| 后端实现计划 | `docs/10_backend_implementation_plan/` | 服务、数据、任务、测试与里程碑 |
| 联调 | `docs/11_integration_testing/` | 契约校验、用例、缺陷与验收记录 |
| 发布与部署 | `docs/12_release_and_deployment/` | 环境、发布步骤、回滚、监控与运行手册 |

## 3. 阶段输出规则

每个 Agent Teams 阶段至少提交一个 Markdown 输出文件。推荐命名格式为：

```text
YYYY-MM-DD-<主题>.md
```

每份阶段输出至少应包含：

1. 目标与范围。
2. 输入材料和假设。
3. 结论与关键决策。
4. 风险、未决问题和依赖。
5. 下一阶段需要接收的交付物。

## 4. Plan 优先

遇到以下任一情况，先在 `docs/00_setup/plans/` 创建 Plan，评审后再实施：

- 同时涉及 `frontend/` 与 `backend/`。
- 涉及 API、数据模型、鉴权或外部集成。
- 需要多名 Agent 并行协作。
- 任务存在不可逆操作、迁移风险或明显的技术选型。

Plan 必须列出修改范围、步骤顺序、验证方法、风险及回滚方式。

## 5. 环境与安全规则

- 后端使用 `backend/.env` 保存环境变量和密钥；真实值不得入库。
- 后端 Python 依赖、虚拟环境与命令统一由 `uv` 管理。
- 前后端仅通过已记录的 API 契约协作。
- 当前初始化阶段禁止创建前端或后端业务代码。

## 6. 现有 Codex 能力

项目已启用 Agent Teams 与 LangChain 文档 MCP。LangChain MCP 用于获取 LangChain 官方最新的文档规范与 API 参考；它不负责调度 Agent Teams，也不负责 LangGraph 的 `interrupt` 或 Human-in-the-loop 运行流程。
