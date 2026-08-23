# 前后端真实 API 联调记录 v1.0

## 目标

验证 `frontend/` 已移除浏览器运行时 Mock API，并通过 Vite `/api` 代理调用 `backend/` 的真实 FastAPI 服务，完成上传文档、创建审核任务和人工审批的完整闭环。

## 环境与边界

- 后端：`cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`
- 前端：`cd frontend && npm run dev -- --host 127.0.0.1 --port 5175`
- 前端请求使用相对路径 `/api/v1/...`，由 Vite 代理转发至 `127.0.0.1:8000`。
- 本地 MVP 身份由后端现有的 `X-Actor-ID`、`X-Actor-Role` 识别。提交者为 `frontend-submitter`，审批者为 `frontend-approver`；未引入新的认证机制。
- 每个状态变更请求使用客户端生成的 `Idempotency-Key`，人工决定同时携带后端返回的版本、运行、基线和 revision。

## 已完成接口顺序

| 顺序 | 真实接口 | 主体 | 结果 |
| --- | --- | --- | --- |
| 1 | `POST /api/v1/cases` | submitter | `201`，创建案件。 |
| 2 | `POST /api/v1/cases/{case_id}/upload-batches` | submitter | `201`，创建不可变文档版本和上传会话。 |
| 3 | `PUT /api/v1/upload-sessions/{upload_session_id}/content` | submitter | `200`，上传真实文本字节。 |
| 4 | `POST /api/v1/upload-batches/{upload_batch_id}/submit` | submitter | `202`，生成当前文档版本和审核运行。 |
| 5 | `GET /api/v1/cases/{case_id}` | submitter | `200`，读取服务端权威状态。 |
| 6 | `GET /api/v1/review-queues/legal_review/assignments?status=queued` | approver | `200`，读取真实待办。 |
| 7 | `POST /api/v1/cases/{case_id}/assignments/{assignment_id}/accept` | approver | `200`，接收待办并取得最新 revision。 |
| 8 | `GET /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/findings` | approver | `200`，读取当前运行风险项。 |
| 9 | `POST /api/v1/cases/{case_id}/assignments/{assignment_id}/decisions`，`edit` | approver | `201`，处置必处置风险项并获得新 revision。 |
| 10 | 同一 decisions 接口，`approve` | approver | `201`，使用同一上下文、原文 locator 和更新后的 revision；案件状态为 `approved`。 |
| 11 | `GET /api/v1/cases/{case_id}/assignments/{assignment_id}` | approver | `200`，路由刷新时重新读取待办、版本和 revision。 |

首次直接 `approve` 得到后端真实响应 `422 action_not_allowed`，原因是仍存在未处置必处置风险项。前端据此接入了后端已实现的 finding-level `edit`，并要求该动作成功后才允许 `approve`，不再伪造审批成功。

## 自动验证

```text
cd frontend && npm test -- --run
6 test files passed, 12 tests passed

cd frontend && npm run build
TypeScript and Vite production build passed

cd backend && uv run pytest
91 passed
```

## 案件级路由回归（2026-08-15）

通过 `http://127.0.0.1:5175/api/v1/...` 执行，全部请求经 Vite `/api` 代理转发到本机后端。状态顺序为：

```text
POST cases=201
POST upload-batches=201
PUT upload content=200
POST upload-batches submit=202
GET review queue=200
POST assignment accept=200
GET case-scoped assignment=200
GET findings=200
GET finding detail=200
POST decision edit=201
POST decision approve=201
final case status=approved
```

本次回归验证了 `/cases/{caseId}/assignments/{assignmentId}` 和 `/cases/{caseId}/assignments/{assignmentId}/confirm` 所依赖的真实接口。页面刷新不需要 `location.state`；队列接收后的导航和两个返回入口均由前端路由测试覆盖为固定父路径。

Vite 使用时输出 Node `20.13.0` 低于 Vite 7 推荐的最低版本 `20.19.0` 的警告，但本次前端测试、构建、开发代理和真实 API 闭环均实际通过。应在后续环境维护中升级 Node。

## 未开发

- 独立的补件/重提页面尚未接入真实的版本化上传批次流程，页面明确显示“未开发”。
- `reject`、`request_supplement`、`transfer`、`escalate`、交付、异议和历史版本浏览未形成完整前端交互，页面不以 Mock 或本地状态模拟成功。
- 当前后端内存存储在进程重启后不保留案件和待办，联调数据需要重新创建。
