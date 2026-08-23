# 前端规划设计 Agent Team Plan

## 目标

基于 API、前端设计、前后端边界和 LangChain HITL 架构规范，输出前端页面层级、路由、组件、状态和接口依赖规划；本阶段只写规划文档，不生成 frontend/backend 代码。

## 分工与文件所有权

1. Teammate 1：上传与任务状态，独占 `docs/09_frontend_implementation_plan/upload_task_pages_routes.md`。
2. Teammate 2：审核结果与证据组件，独占 `docs/09_frontend_implementation_plan/audit_result_evidence_components.md`。
3. Teammate 3：人工审核 HITL UI，独占 `docs/09_frontend_implementation_plan/hitl_review_ui_flow.md`。
4. Lead：三份主题完成后，只做交叉索引、页面层级统一、接口“未开发”状态汇总，写入 `docs/06_system_architecture/frontend_arch-spec-v1.0.md`。

## 输入

- `docs/08_api_spec/api_spec-v1.0.md`
- `docs/06_system_architecture/frontend_design_spec-v1.0.md`
- `docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md`
- `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`
- 当前 `backend/` 状态：仅有 `.gitkeep`，无可运行 API 实现。

## 实施与验证

1. 每位 teammate 说明页面层级、组件/路由、字段展示、权限和接口依赖。
2. 后端尚未实现的接口统一标记“未开发”，不得用 Mock 成功结果替代。
3. Lead 等所有 teammate 完成并关闭后汇总，不新增主题设计。
4. 检查三份主题文档及汇总文档存在、引用输入一致、未生成业务代码。

## 风险与回滚

- API 契约已定义但 backend 当前为空，规划中的接入点不代表已可调用。
- 历史版本、异步状态和 HITL 恢复依赖后端实现，前端只能按服务端权威状态设计。
- 本阶段仅新增 Markdown；移除新增文档即可回滚，不触碰既有文档和代码。
