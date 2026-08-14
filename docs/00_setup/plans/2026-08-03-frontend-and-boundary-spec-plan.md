# 前端设计与前后端边界规范计划

## 范围

以 `docs/03_business_problem_modeling/document_audit_business_model.md` 和 `docs/04_core_interaction_flows/interaction_flow_summary.md` 为唯一业务输入，形成前端页面/交互规范及前后端功能边界规范。仅生成文档，不实现前后端代码、接口或数据表。

## 涉及文件

- 新建：`docs/06_system_architecture/frontend_design_spec-v1.0.md`
- 新建：`docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md`

## 实施步骤

1. 将已定义的角色、案件生命周期和交互链路映射为页面清单、页面层次、跳转关系与核心交互。
2. 以业务对象、状态权威和交接信息为界，明确前端展示/发起职责与后端判定/持久化职责。
3. 核验两份文档不新增业务范围，不包含代码、接口字段或技术实现细节。

## 验证方式

确认两个指定文件存在；检查页面、状态和人工处置语义均可回溯至输入文档；确认前端和后端目录没有新增代码文件。

## 风险与回滚

风险是将规范误扩展为未确认的产品或技术方案。通过仅引用既有对象、状态和交接限制风险；如发现超出范围，删除对应扩展段落并回归输入文档。

## 审批记录

该计划明确了调研/规范范围、输出文件和分析结构，符合项目“先 Plan 后实施”的要求，已获 Lead 批准后执行。
