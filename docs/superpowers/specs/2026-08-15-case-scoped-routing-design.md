# 案件上下文路由设计

## 目标

将 DocAuditAgent 的案件、风险证据和人工审核页面组织为案件上下文路由，消除依赖浏览器历史和 `location.state` 的跳转。用户在任意页面刷新后，系统仅依靠 URL 中的标识和后端真实响应恢复页面状态。

## 路由结构

| 路由 | 页面 | 数据来源 | 明确返回目标 |
| --- | --- | --- | --- |
| `/cases` | 案件列表 | `GET /api/v1/cases` | 无 |
| `/cases/new` | 创建案件与上传 | 创建、上传批次、上传内容、提交接口 | `/cases` |
| `/cases/:caseId` | 案件概览 | `GET /api/v1/cases/{caseId}` | `/cases` |
| `/cases/:caseId/evidence` | 风险与原文证据 | 案件、当前运行、findings、finding detail | `/cases/:caseId` |
| `/review` | 审核待办队列 | `GET /api/v1/review-queues/legal_review/assignments` | `/cases` |
| `/cases/:caseId/assignments/:assignmentId` | 待办详情与接收 | 待办详情、案件、风险列表 | `/review` |
| `/cases/:caseId/assignments/:assignmentId/confirm` | 风险处置与批准确认 | 待办详情、风险 detail、决定接口 | `/cases/:caseId/assignments/:assignmentId` |

补件、交付、异议等当前没有完整页面流程的能力不纳入本次路由重构；不新增 Mock 页面或伪造跳转。

## 跳转规则

1. 创建和提交上传成功后跳转 `/cases/:caseId`。
2. 案件详情进入风险页时保留 `caseId`；风险页仅返回该案件详情。
3. 审核队列接收待办成功后跳转到该待办的案件级详情路径，而非全局确认页。
4. 确认页返回待办详情的固定路由；删除 `navigate(-1)`，避免从刷新、深链或跨页面进入时返回不确定位置。
5. 面包屑固定由 URL 构建：案件列表 / 案件编号 / 当前页面；审核队列页显示审核队列 / 当前待办。

## 数据和错误边界

- 待办详情与确认页从 URL 获取 `caseId` 和 `assignmentId`，通过真实 `GET /api/v1/cases/{caseId}/assignments/{assignmentId}` 读取当前三元组和 `expected_revision`。
- 页面刷新不读取 `location.state`；决定提交使用刚从服务端读取或刚由接收返回的 revision。
- `case_not_found`、`resource_not_found`、`run_superseded`、`stale_human_task`、`revision_conflict` 使用后端安全错误消息；页面提供明确的案件详情或审核队列链接。
- 前端不推断权限。后端返回的 `allowed_actions`、当前责任和上下文决定按钮可用性。

## 测试标准

1. 路由组件测试覆盖从队列接收后跳转到案件级待办路径。
2. 确认页在没有 `location.state` 时仍使用 URL 读取数据，不呈现伪造上下文。
3. 返回按钮的 `href` 或 `navigate()` 参数等于其固定父路由。
4. 前端单测、构建、后端测试和一次真实 API 链路回归全部通过。

## 非目标

- 不改变后端路由、API 契约、认证或状态机。
- 不新增补件、交付、异议或其他尚未形成完整页面流程的功能。
- 不使用浏览器历史长度作为业务导航逻辑。
