# API 规范 v1.0 编写 Plan

## 目标

基于既有数据模型、业务模型、后端服务架构和 LangChain HITL 约束，收口形成 `docs/08_api_spec/api_spec-v1.0.md`。范围限于上传、审核查询、人工审核和前后端联调顺序，不新增业务状态、自动放行规则或外部集成。

## 输入与文件核对

- `docs/06_system_architecture/data_model_spec-v1.0.md`
- `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`
- `docs/03_business_problem_modeling/document_audit_business_model.md`
- `docs/06_system_architecture/backend_service_architecture_spec-v1.0.md`
- 用户列出的 `langchain_hitl_workflow_design-v1.0.md` 与 `backend_service_arch-v1.0.md` 当前未找到；以工作区现存的 `langchain_hitl_document_audit_arch-v1.0.md` 和 `backend_service_architecture_spec-v1.0.md` 作为对应输入，并在 API 文档中记录该事实。

## 实施步骤

1. 固化统一术语、版本/运行/基线三元组、授权和错误语义。
2. 定义上传及异步状态查询接口。
3. 定义审核结果、风险证据、原文定位、人工队列和人工动作接口。
4. 定义请求/响应/幂等/并发/可见性约束及联调顺序。
5. 校验接口不得把解析成功、空命中或 Agent 完成表达为 `approved`。

## 验证与风险

- 验证目标文件存在，且覆盖上传、审核查询、人工审核、错误和联调顺序。
- 所有写接口均包含权限、当前版本/运行、责任和 `revision` 校验要求。
- API 路径为逻辑契约，不暗示数据库、对象存储、队列或 LangGraph SDK 的具体实现。
- 现存文件名差异不在本阶段创建副本或改名；后续如需补齐，应先更新架构索引。
