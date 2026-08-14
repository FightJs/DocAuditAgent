# Plan: 数据模型规范阶段（Agent Team）

- 日期: 2026-08-04
- 阶段: `docs/07_data_model/` + `docs/06_architecture_design/`
- 目标: 产出可直接作为前后端实现输入的数据模型规范，本阶段不生成任何前后端代码。

## 1. 范围

| 角色 | 主题 | 独占写入文件 |
| --- | --- | --- |
| Teammate 1 | 文档上传、任务状态处理相关模型 | `docs/07_data_model/upload_and_task_models.md` |
| Teammate 2 | 审核规则、命中项、解释性字段、审核结果、原文定位 | `docs/07_data_model/audit_rule_hit_result_model_spec-v1.0.md` |
| Teammate 3 | 人机交互流程模型（approve / edit / reject） | `docs/07_data_model/human_interaction_decision_models.md` |
| Lead | 汇总规范（不写主题内容） | `docs/06_architecture_design/data_model_spec-v1.0.md` |

文件所有权互斥，避免并行写冲突。

## 2. 输入

- `docs/03_business_problem_modeling/document_audit_business_model.md`
- `docs/04_core_interaction_flows/*.md`
- `docs/06_system_architecture/*.md`
- 现有 `docs/07_data_model/*.md`（作为基线，本轮规范化重写）

## 3. 每个 Teammate 的强制输出要素

1. 实体清单：字段名、类型、必填性、取值域/枚举、含义。
2. 实体间关系（1:1 / 1:N / N:M，外键与生命周期依赖）。
3. 状态机（若该主题含状态字段）：状态、合法迁移、触发方。
4. `前端必须展示` 字段标注。
5. `后端必须存储` 字段标注（含持久化与仅内存/派生字段区分）。
6. 与其他两位 Teammate 主题的衔接字段（跨主题引用键）。

## 4. 实施步骤

1. Lead 创建 Agent Team，三个 teammate 使用同一模型档位（环境可选模型中的 fable；无 "Terra" 档位，已向用户说明）。
2. 三个 teammate 并行读取现有文档并写入各自独占文件。
3. Lead 等待全部完成，校验字段命名与跨主题引用键一致性。
4. Lead 写汇总规范 `docs/06_architecture_design/data_model_spec-v1.0.md`：全局实体关系图、跨主题键对齐表、前端展示字段总表、后端存储字段总表、未决问题。
5. Lead 关闭并清空 Team。

## 5. 验证方式

- 三份主题文档均存在且含上述 6 要素。
- 跨主题引用键（如 `document_id` / `task_id` / `finding_id`）在三份文档中命名与语义一致。
- 汇总文档中每个实体都能追溯到唯一的主题文档来源。
- 无前后端代码文件被创建或修改（`frontend/`、`backend/` 无变更）。

## 6. 风险与回滚

- 风险: 三位 teammate 对同一概念使用不同字段名 → Lead 在汇总阶段做命名对齐表，冲突以业务模型文档为准。
- 风险: 覆盖已有文档内容 → 现有三份文档为同一阶段基线，本轮为规范化升级；如需回退可依据文档内版本号与本 Plan 重建。
- 回滚: 仅涉及 `docs/` 下文档，删除或还原对应 md 即可，无运行时影响。
