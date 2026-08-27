# DocAuditAgent

DocAuditAgent 是一个可审计的文档审核工作台 MVP。业务提交者可以创建案件、上传材料并查看授权范围内的处理结果；审核人员可以接收待办、查看风险及原文证据，并在当前文档版本和审核上下文中提交人工决定。

项目的目标不是把上传或自动处理误表述为审批通过。`approved` 仅能由具有权限的人员在有效的文档版本、审核运行、审核基线和证据上下文中作出。

## 当前能力

- 创建审核案件，并以不可变文档版本上传合同正文和支持附件。
- 创建审核运行，查看案件状态、风险项、原文定位和时间线。
- 将高风险或不确定结果路由到人工审核队列。
- 审核人员接收待办、先处置必处置风险项，再提交案件级决定。
- 对变更请求使用幂等键和 `expected_revision`，避免重复提交及过期写入。
- 前端通过真实 FastAPI API 工作，不依赖浏览器运行时 Mock 数据。

## 架构

```text
React + Vite 前端
        |
        | /api/v1/* (Vite 开发代理)
        v
FastAPI 服务层
        |
        +-- 案件、版本、上传批次、审核运行
        +-- 风险项、证据定位、审核队列、人工决定
        |
        v
LangGraph HITL 审核工作流
prepare -> agent_review -> triage -> human_review -> finalize
```

后端的 `AuditService` 是业务状态与授权判断的权威来源。当前 MVP 使用进程内存储，服务重启后案件、待办与运行数据会丢失。工作流支持 DeepSeek 兼容的配置，但离线测试使用 stub，不会调用外部模型。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite、React Router、Vitest |
| 后端 | Python 3.12+、FastAPI、Pydantic、LangGraph、LangChain OpenAI 兼容层 |
| 依赖管理 | 前端 npm；后端 uv |
| 测试 | Vitest、Testing Library、pytest |

## 项目结构

```text
.
├── frontend/                 # React 前端和前端测试
├── backend/
│   ├── app/api/              # FastAPI 路由
│   ├── app/services/         # 案件、上传与审核业务服务
│   ├── app/hitl/             # 人工审核领域模型与状态
│   ├── app/workflow/         # LangGraph 审核工作流
│   └── tests/                # 单元与端到端 API 测试
├── docs/                     # 产品、架构、API、计划和测试记录
├── PRODUCT.md                # 产品定位和设计原则
└── README.md
```

## 本地启动

### 前置条件

- Node.js 20.19+ 或 22.12+（Vite 7 的推荐最低版本）。
- Python 3.12 至 3.14。
- 已安装 `uv`。

### 1. 配置后端环境变量

后端密钥只存放在 `backend/.env`，不要提交该文件。可从示例文件开始：

```bash
cd backend
cp .env.example .env
```

`DEEPSEEK_API_KEY` 仅在需要真实模型调用时填写。离线开发和测试不需要真实密钥。

### 2. 启动后端

```bash
cd backend
uv sync --extra test
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查地址：<http://127.0.0.1:8000/healthz>

### 3. 启动前端

另开一个终端：

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 <http://127.0.0.1:5173>。开发服务器会将 `/api` 请求代理到 `http://127.0.0.1:8000`。

## 核心使用流程

1. 提交者在“新建审核案件”中填写案件参考号并选择材料。
2. 前端依次创建案件、创建上传批次、上传文件内容并提交批次。
3. 后端创建当前文档版本和审核运行，案件进入处理中或人工复核状态。
4. 审核人员在“人工审核工作台”接收待办，并查看当前运行的风险项和证据原文。
5. 必处置风险项处理完成后，审核人员附带理由提交同意决定；服务端校验版本、运行、基线、责任和 revision。

## API 约定

API 基础路径为 `/api/v1`。所有业务接口都需要身份请求头：

```http
X-Actor-ID: example-user
X-Actor-Role: submitter
```

可用角色包括 `submitter`、`reviewer`、`expert`、`approver`、`policy_owner`、`operator` 和 `admin`。前端示例使用本地联调身份 `frontend-submitter` 与 `frontend-approver`；它们仅用于 MVP 开发，不构成生产认证方案。

状态变更接口通常还需要 `Idempotency-Key`，人工决定需要包含服务端返回的 `document_version_id`、`audit_run_id`、`baseline_version_id` 和 `expected_revision`。成功响应使用 `data` envelope，失败响应使用：

```json
{
  "error": {
    "code": "revision_conflict",
    "message": "当前任务已发生变化，请刷新后重试",
    "details": {},
    "retryable": false,
    "request_id": "req_..."
  }
}
```

主要接口包括：

| 领域 | 接口 |
| --- | --- |
| 案件 | `POST /cases`、`GET /cases`、`GET /cases/{case_id}` |
| 上传 | `POST /cases/{case_id}/upload-batches`、`PUT /upload-sessions/{id}/content`、`POST /upload-batches/{id}/submit` |
| 审核结果 | `GET /cases/{case_id}/audit-runs/{run_id}/findings`、`GET /cases/{case_id}/audit-runs/{run_id}/findings/{finding_id}` |
| 人工审核 | `GET /review-queues/{queue_id}/assignments`、`POST /cases/{case_id}/assignments/{id}/accept`、`POST /cases/{case_id}/assignments/{id}/decisions` |

完整接口契约见 [docs/08_api_spec/api_spec-v1.0.md](docs/08_api_spec/api_spec-v1.0.md)。

## 测试与构建

```bash
# 前端测试
cd frontend && npm test -- --run

# 前端生产构建
cd frontend && npm run build

# 后端测试
cd backend && uv run pytest
```

当前基线验证结果：前端 6 个测试文件、12 个测试通过；后端 91 个测试通过；前端生产构建通过。

## 已知边界

- 后端数据存储为内存实现，重启服务会清空数据。
- 本地身份通过请求头模拟，尚未接入生产级认证、租户隔离或权限提供方。
- 前端尚未完成补件/重提、驳回、要求补件、转交、升级、交付、异议和历史版本浏览的完整交互。
- 生产化还需要接入事务数据库、对象存储、持久化工作流 checkpointer、异步队列、超时重试和审计运维能力。

## 参考文档

- [产品定义](PRODUCT.md)
- [前后端边界规范](docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md)
- [后端服务架构](docs/06_system_architecture/backend_service_architecture_spec-v1.0.md)
- [HITL 工作流架构](docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md)
- [API 契约](docs/08_api_spec/api_spec-v1.0.md)
- [前后端联调记录](docs/11_integration_testing/frontend_backend_integration-v1.0.md)
