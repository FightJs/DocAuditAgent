# DocAuditAgent 前端实施规划汇总规范 v1.0

## 1. 文档定位

本文件汇总三份前端实施规划，作为后续前端原型、路由、组件、状态管理和联调工作的收口输入。本阶段只定义规划，不生成前端代码；主题细节以对应来源文件为准。

当前 `frontend/` 尚无可运行工程，`backend/` 仅保留 `.gitkeep`。因此所有后端 API 在本阶段均属于“契约已定义、后端未开发”，前端不得伪造成功响应或宣称联调完成。

## 2. 主题规划来源

| 主题 | 规划文档 | 页面/组件范围 |
| --- | --- | --- |
| 上传与任务状态 | [upload_task_pages_routes.md](../09_frontend_implementation_plan/upload_task_pages_routes.md) | P1 案件列表、P2 新建上传、P3 案件详情与时间线、材料/解析详情、P4 补件/重提。 |
| 审核结果与证据 | [audit_result_evidence_components.md](../09_frontend_implementation_plan/audit_result_evidence_components.md) | P5 风险结果与原文证据、P6/P7 复用的审核上下文、规则评估、命中项、解释、定位、依据和结果摘要组件。 |
| 人工审核 HITL | [hitl_review_ui_flow.md](../09_frontend_implementation_plan/hitl_review_ui_flow.md) | 队列、待办详情、人工工作台、决定确认、交付预览、异议和更正流程。 |

三份主题文档均已说明目标、输入、页面层级、组件职责、字段展示、权限边界、API 依赖、风险和下一阶段交付物。

## 3. 统一页面层级

```text
应用壳
├─ P1 案件列表 /cases
├─ P2 新建案件 /cases/new
│  └─ P2 上传材料 /cases/:caseId/upload
├─ P3 案件详情 /cases/:caseId
│  ├─ 材料与解析详情 /cases/:caseId/versions/:versionId
│  ├─ P5 风险结果与原文证据
│  └─ P6 人工审核工作台
│     └─ P7 决定确认与交付预览
├─ P4 补件/重提 /cases/:caseId/supplements/new
├─ 人工队列 /review-queues/:queueId/assignments
└─ 提交者交付与异议视图
```

页面进入和离开只改变视图上下文，不由前端跳转伪造案件状态。案件、文档版本、审核运行和审核基线是所有详情、风险和人工页面的固定上下文。

## 4. 跨主题页面职责

| 页面层 | 主要职责 | 必须承接的状态/信息 | 当前接口状态 |
| --- | --- | --- | --- |
| P1/P2 | 进入审核、创建案件、选择材料角色、上传并提交。 | 案件引用、审核范围、文件清单、上传进度、准入结果和下一步。 | 所有相关接口“未开发”。 |
| P3/P4 | 展示异步处理、版本关系、时间线、失败/补件和重提入口。 | 当前版本、解析任务/质量、状态原因、补件项、只读历史。 | 所有相关接口“未开发”。 |
| P5 | 展示审核结果和可复核证据。 | 运行/基线、风险、规则命中、解释、依据、原文定位和限制。 | 所有相关接口“未开发”。 |
| P6/P7 | 让授权审核者接收待办、查看证据、提交人工决定并预览交付。 | 队列、责任、`allowed_actions`、`expected_revision`、决定差异、交付可见性。 | 所有相关接口“未开发”。 |

## 5. 统一前端边界

1. 前端只展示服务端返回的权威状态和允许动作；不能自行计算案件终态、风险结论、权限或责任。
2. 上传完成、解析完成、Agent 完成、空风险项和结果准备状态均不能显示为 `approved`。
3. 原文、风险、解释和交付信息必须绑定 `document_version_id`、`audit_run_id`、`baseline_version_id`；版本替代后旧视图只读。
4. 前端错误态、加载态、空态、无权限、过期 revision、定位失效和后端不可用态必须先于成功态设计。
5. 后端返回未知枚举时保留原值并降级为“待确认”；不能隐藏为成功或无风险。
6. 前端不得展示对象存储引用、内部模型轨迹、隐藏提示、安全检测细节或未授权主体信息。

## 6. API 接入状态总览

依据当前工作区检查，以下能力仅在 [`api_spec-v1.0.md`](../08_api_spec/api_spec-v1.0.md) 中定义，`backend/` 当前没有对应运行实现，统一标注为“未开发”：

| 能力 | 典型接口 | 前端规划位置 | 状态 |
| --- | --- | --- | --- |
| 案件创建 | `POST /api/v1/cases` | P2 | 未开发 |
| 上传批次/文件/提交 | `POST /cases/{case_id}/upload-batches`、`PUT /upload-sessions/{id}/content`、`POST /upload-batches/{id}/submit` | P2/P4 | 未开发 |
| 案件、时间线、版本、解析、补件查询 | `GET /cases/{case_id}`、`/timeline`、`/document-versions/...` | P3/P4 | 未开发 |
| 运行、风险、解释、定位、依据查询 | `GET /audit-runs/...`、`/findings/...`、`/locators/...` | P5/P6 | 未开发 |
| 队列/待办/责任 | `GET /review-queues/.../assignments`、`GET /assignments/...` | P6 | 未开发 |
| 接收待办 | `POST /assignments/{assignment_id}/accept` | P6 | 未开发 |
| 人工决定 | `POST /assignments/{assignment_id}/decisions` | P6/P7 | 未开发 |
| 异议与交付查询 | `POST /objections`、`GET /deliveries/{delivery_id}` | 提交者视图/P7 | 未开发 |
| 创建交付 | `POST /deliveries` | 前端不提供按钮，由后端内部动作完成 | 未开发 |

在 backend 实现前，前端规划阶段只允许定义类型、契约校验、加载/错误/未开发提示和只读页面骨架；禁止用 Mock 成功响应补齐业务链路。

## 7. 实施顺序

1. 恢复前端工程并确认 `package.json`、锁文件和实际技术栈；当前缺失，不能声称可启动。
2. 建立应用壳、权限门禁、P1–P4 页面和上传/状态类型；等待对应后端接口实现。
3. 建立 P5 结果/证据组件，先覆盖加载、空、定位失效、质量不足和后端未开发态。
4. 建立 P6/P7 队列、证据包、决定确认和交付预览；动作按钮由 `allowed_actions` 控制。
5. 后端接口逐项实现后，按 API 契约接入；每个接口完成成功、权限、过期 revision、版本替代和错误态验证。
6. 完成从上传到人工决定的真实联调后，才开启对应成功态和交付态。

## 8. 风险与后续交付物

| 风险 | 处理方式 |
| --- | --- |
| backend 当前为空 | 所有接口保持“未开发”，先做契约和非成功状态，不伪造联调。 |
| frontend 当前无工程 | 先恢复工程和包管理信息，不能猜测框架或启动脚本。 |
| API 字段/路径后续变化 | 先更新 API/Schema，再同步主题规划和前端类型。 |
| 版本、权限、证据和人工动作并发 | 以后端返回的上下文、`allowed_actions`、`expected_revision` 和错误 envelope 为准。 |

下一阶段交付物：前端工程恢复记录、路由与组件实现计划、类型化 API client、状态适配层、真实后端联调记录、前端测试和无障碍验收。

## 9. Lead 验收记录

- 三份主题规划均已完成并归档。
- 每份主题均明确页面层级；汇总文件已统一页面树和跨页面职责。
- 当前 backend 仅有 `.gitkeep`，所有 API 依赖均明确标注“未开发”。
- 未生成前端代码、Mock 成功路径或后端代码。
- Team 成员均已完成并关闭，当前 Team 已清空。
