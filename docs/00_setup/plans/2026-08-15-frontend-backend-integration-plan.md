# 前后端真实 API 联调实施 Plan（2026-08-15）

## 目标

移除浏览器运行时的 Mock API，令 `frontend/` 仅通过 `docs/08_api_spec/api_spec-v1.0.md` 中已由 `backend/` 实现的 `/api/v1` 接口完成最小完整链路：创建案件、上传文档并提交、查询审核状态与风险、人工接收待办并提交审批决定。后端未实现的界面能力必须显示“未开发”，不得保留本地伪造成功状态。

## 输入与事实来源

- API 契约：[docs/08_api_spec/api_spec-v1.0.md](../../08_api_spec/api_spec-v1.0.md)
- 边界规范：[docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md](../../06_system_architecture/frontend_backend_boundary_spec-v1.0.md)
- 后端可用路由：[backend/app/api/routes.py](../../../backend/app/api/routes.py)
- 当前 Mock 边界：[frontend/src/mocks/handlers.ts](../../../frontend/src/mocks/handlers.ts)

## 实施边界

- 只改 `frontend/` 的 API 客户端、类型、页面、测试和 Vite 本地代理配置；不改变 `backend/` 业务实现或 API 契约。
- 开发态不再启动 MSW browser worker；MSW 可只保留为隔离的客户端错误单测辅助，不得拦截实际联调页面请求。
- 本地 MVP 后端当前以 `X-Actor-ID`、`X-Actor-Role` 识别身份。开发配置明确固定提交者、审核者、审批者三组主体；生产认证接入不属于本次范围。
- 任何写操作由客户端生成 `Idempotency-Key`；待办动作使用服务端返回的 `expected_revision` 和固定上下文，不写死 `assignment_case_2`、`docv_01J`、`run_01J` 或 `baseline_2026_01`。

## 已核对的接口映射

| 前端能力 | 真实后端接口 | 当前状态 | 联调处理 |
| --- | --- | --- | --- |
| 创建案件 | `POST /api/v1/cases` | 已实现 | 传递提交者头和幂等键。 |
| 创建上传批次 | `POST /api/v1/cases/{case_id}/upload-batches` | 已实现 | 从选中文件生成 `files` 描述。 |
| 上传字节 | `PUT /api/v1/upload-sessions/{upload_session_id}/content` | 已实现 | 对每个 upload session 逐个发送原始 `File` 字节。 |
| 提交批次 | `POST /api/v1/upload-batches/{upload_batch_id}/submit` | 已实现 | 传递上传批次 `revision` 和幂等键。 |
| 案件、运行、风险、证据查询 | 已实现的 `GET /cases`、`/cases/{id}`、`/audit-runs/...` | 已实现 | 从案件详情的当前运行读取风险与证据。 |
| 队列与接收待办 | `GET /review-queues/{queue}/assignments`、`POST /cases/{case_id}/assignments/{assignment_id}/accept` | 已实现 | 保存服务端返回的 assignment、上下文和 revision。 |
| 人工决定 | `POST /cases/{case_id}/assignments/{assignment_id}/decisions` | 已实现 | 仅显示后端当前支持且页面具备完整必填参数的动作。 |
| 补件快捷接口 | `/cases/{case_id}/supplements` | **未开发** | 移除 Mock 调用；页面显示“未开发”。后续应复用真实上传批次三步流程。 |
| 简化版待办接口 | `/assignments/{assignment_id}/accept`、`/assignments/{assignment_id}/decisions` | **未开发** | 替换为含 `case_id` 的真实路径，不保留 fallback。 |
| 交付创建/查询、异议、历史版本浏览 | 后端接口已存在，但当前页面未形成完整用户流程 | **未开发** | 本次不自行补造页面工作流，保留或展示“未开发”。 |

## 文件范围

| 文件 | 计划中的责任 |
| --- | --- |
| `frontend/src/main.tsx` | 移除开发态 MSW 自动启动。 |
| `frontend/src/api/client.ts` | 统一真实 API base URL、主体头、幂等键、JSON/字节请求、错误 envelope。 |
| `frontend/src/api/cases.ts` | 实现案件创建、上传批次、原始字节上传、提交、案件/运行/风险/定位查询。 |
| `frontend/src/api/review.ts` | 实现真实队列、接收和人工决定请求。 |
| `frontend/src/types/domain.ts` | 用后端响应字段表达案件、上传批次、待办、决定、风险和定位，不保留 Mock 专属字段。 |
| `frontend/src/App.tsx` | 用真实异步状态驱动上传、状态查询、证据、人工审批；无法完成的操作标注“未开发”。 |
| `frontend/vite.config.ts` | 将 `/api` 开发代理到本地后端，地址只从开发环境配置读取。 |
| `frontend/src/api/*.test.ts`、`frontend/src/App.test.tsx` | 替换 MSW 成基于真实契约 shape 的 fetch 单测，并为未开发提示及真实必填字段增加回归测试。 |
| `docs/11_integration_testing/frontend_backend_integration-v1.0.md` | 记录每个阶段的真实请求、状态码、页面验收和未开发项。 |

## 分阶段实施与测试门槛

### 阶段 0：联调运行环境

1. 启动后端：在 `backend/` 执行 `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`。
2. 启动前端：在 `frontend/` 执行 `npm run dev -- --host 127.0.0.1 --port 5173`。
3. 通过 Vite `/api` 代理请求后端；不在组件中拼接 `http://localhost:8000`。
4. 验收：`GET /healthz` 为 `200`，浏览器中任一真实 `GET /api/v1/cases` 不被 MSW 拦截，缺少主体头时服务端返回真实 `401`。

### 阶段 1：上传文档与创建审核任务

1. 先写 API 客户端单测，断言创建案件携带 `X-Actor-ID: frontend-submitter`、`X-Actor-Role: submitter` 与 `Idempotency-Key`。
2. 将“新建审核案件与上传材料”页面改为连续动作：`POST /cases` -> `POST /cases/{case_id}/upload-batches` -> 每个 session `PUT .../content` -> `POST /upload-batches/{batch_id}/submit`。
3. 只有所有文件上传成功且提交响应为 `202` 时导航案件详情；服务端 `data` 是唯一状态来源。
4. 处理错误 envelope：展示安全 `message` 与 `request_id`；`upload_incomplete`、`revision_conflict` 不更新本地成功状态。
5. 验收：使用一个真实 `.txt` 测试文件，在浏览器 DevTools 或 HTTP 日志中确认四类请求的顺序和状态码 `201 -> 201 -> 200 -> 202`，随后 `GET /cases/{case_id}` 返回当前文档版本和审核运行。

### 阶段 2：审核状态、风险与原文定位

1. 案件详情按服务端 `status`、`current_document_version`、`current_audit_run`、`assignment_summary`、`allowed_actions` 渲染，移除 Mock 文案和硬编码版本标识。
2. 通过 `GET /cases/{case_id}/audit-runs/{audit_run_id}/findings` 读取风险；选择风险后通过 finding detail 和 locator 接口读取真实 `quote`、上下文与定位信息。
3. 后端未返回页面所需字段时，组件显示“未开发”，不以 Mock 数据或推断文本填充。
4. 验收：完成阶段 1 后刷新详情页，确认状态、风险标题、严重度、原文证据均来自真实响应；对不存在案件确认展示后端安全错误。

### 阶段 3：人工审批

1. 审核工作台使用审核者主体查询真实 `legal_review` 队列；选择一条待办后保存其 `case_id`、三元组和 `expected_revision`。
2. “接收待办”调用真实 `POST /cases/{case_id}/assignments/{assignment_id}/accept`，并以接收响应的 revision 刷新本地待办。
3. 确认页只允许提交已由服务端支持、且 UI 已收集完必填字段的决定。审批必须携带当前 document version、audit run、baseline、revision、idempotency key、证据 locator 引用和所需理由/条件。
4. 页面中 `edit`、`reject`、`request_supplement`、`transfer`、`escalate` 的完整表单在本次未完成前均显示“未开发”；不得把选择器的值伪造为后端成功。
5. 验收：以 approver 主体完成“队列 -> 接收 -> approve”，确认案件状态仅在后端返回 `approved` 后更新；重复同一幂等键返回同一决定；使用旧 revision 得到并展示 `revision_conflict`。

### 阶段 4：回归与记录

1. 运行前端单测：`cd frontend && npm test -- --run`。
2. 运行前端构建：`cd frontend && npm run build`。
3. 运行后端全量测试：`cd backend && uv run --extra test pytest -q`。
4. 逐阶段执行浏览器/API 冒烟测试，并把真实 endpoint、状态码、断言、request_id（脱敏）和未开发项记录到 `docs/11_integration_testing/frontend_backend_integration-v1.0.md`。
5. 只有阶段 1、2、3 都通过时，才删除“Mock API 模式”可见提示；仍未实现的功能持续保留“未开发”。

## 风险与回滚

- 后端为进程内存储；前后端任一重启会丢失联调中的案件，需要从阶段 1 重建测试数据。
- 本地认证头仅为 MVP 接缝，不能视为生产身份方案；前端配置不得写入密钥。
- Vite 运行时 Node 版本必须满足当前 Vite 版本要求；环境告警应在联调记录中保留。
- 回滚仅恢复 `frontend/` 中 Mock 启动与客户端变更；不回滚或改写后端状态和 API 契约。

## 非目标

- 不新增后端接口、不改 API 语义、不编写生产认证、持久化、对象存储或异步任务队列。
- 不对后端未实现的页面能力使用 Mock、假数据、假的成功 Toast 或本地状态机替代。
