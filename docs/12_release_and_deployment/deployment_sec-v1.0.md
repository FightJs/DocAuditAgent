# DocAuditAgent 部署与发布规范 v1.0

## 1. 文档定位

本文档定义当前 DocAuditAgent MVP 的本地运行、容器化部署、发布验证、回滚和故障排查方式。它是交付阶段的运行手册，不改变现有 API 契约、工作流或前端路由。

输入依据：

- `backend/` 当前 FastAPI、LangGraph/HITL 与内存服务实现；
- `frontend/` 当前 React/Vite 应用和相对路径 API 客户端；
- `docs/08_api_spec/api_spec-v1.0.md`；
- `docs/11_integration_testing/e2e_api_flow-v1.0.md`；
- `docs/11_integration_testing/frontend_backend_integration-v1.0.md`。

当前版本为 MVP。部署可用于本地演示、联调和受控验收，不能直接作为公网生产部署。生产化前必须完成持久化、认证/授权、秘密管理、TLS、审计与监控能力接入，详见第 11 节。

## 2. 当前交付范围

### 2.1 已实现并可部署的链路

```text
创建审核案件
  -> 创建上传批次
  -> 上传文件内容
  -> 提交并生成审核运行
  -> 查询人工队列
  -> 接收待办
  -> 处置风险项
  -> 人工同意
```

前端提供案件列表、创建与上传、案件详情、风险与证据、审核队列、案件级待办详情和确认页面。确认页使用 `/cases/{caseId}/assignments/{assignmentId}/confirm` 读取真实后端待办；刷新不依赖浏览器历史或 `location.state`。

### 2.2 当前版本边界

| 主题 | 当前实现 | 部署影响 |
| --- | --- | --- |
| 业务数据 | `AuditService` 使用进程内内存存储。 | 重启后案件、上传、待办、决定和幂等记录均丢失；后端只能运行一个副本。 |
| HITL checkpoint | `InMemorySaver`。 | 不支持跨进程、跨副本或重启恢复。 |
| 身份认证 | 通过 `X-Actor-ID` 和 `X-Actor-Role` 模拟联调主体。 | 不能将后端 API 直接暴露至公网，也不能信任来自公网的这两个请求头。 |
| 大模型 | 默认工作流使用 `OfflineMvpReviewer`。 | 当前运行不要求 DeepSeek 网络或 API Key；`DEEPSEEK_*` 是已实现的 LangChain 适配器配置，为切换真实 reviewer 的后续接线预留。 |
| 文件存储 | 文件内容为内存对象。 | 不适合大文件、持久化归档或多实例。 |
| CORS | 当前应用未配置跨域中间件。 | 生产建议前端与 `/api` 同源，由 Nginx 反向代理，避免浏览器跨域请求。 |

## 3. 架构与服务边界

### 3.1 推荐容器拓扑

```text
Browser
  |
  | http(s)://host:8080/
  v
frontend (Nginx, static React assets)
  |                         |
  | /                       | /api/*
  |                         v
  +--------------------> backend (FastAPI/Uvicorn :8000)
                              |
                              +--> DeepSeek-compatible API (only after real reviewer wiring)
```

- `frontend` 是唯一对外暴露的 HTTP 服务，默认映射宿主机 `8080`。
- `backend` 在 Compose 内部网络监听 `8000`，不映射到宿主机；Nginx 以 `/api` 代理请求，保留 `/api/v1/...` 路径。
- 后端 `/healthz` 返回 `{ "status": "ok" }`，用于容器健康检查。
- 当前实现没有数据库、对象存储、消息队列或缓存服务；这些不是本 MVP 的运行依赖。

### 3.2 服务启动顺序

1. 准备后端运行环境变量和受保护的 `backend/.env`；
2. 启动 `backend` 并等待 `/healthz` 为 `200`；
3. 启动 `frontend` Nginx；
4. 从浏览器打开 `http://127.0.0.1:8080`，由前端经同源 `/api` 访问后端；
5. 发布后执行第 9 节的健康检查和完整业务冒烟测试。

Docker Compose 中使用 `depends_on` 的 `service_healthy` 条件表达第 2、3 步；它不是数据库就绪或真实大模型可用性的替代检查。

## 4. 环境要求与变量

### 4.1 本地开发工具链

| 工具 | 要求 | 用途 |
| --- | --- | --- |
| Python | `>=3.12,<3.15` | FastAPI 后端。 |
| uv | 已安装且可执行 | Python 依赖同步、运行和测试。 |
| Node.js | 推荐 `>=20.19` | Vite 开发、测试和生产构建。 |
| npm | 与 Node.js 匹配 | 前端依赖安装和脚本运行。 |
| Docker Engine + Docker Compose v2 | 容器部署时必需 | 构建和启动容器组合。 |

当前已验证的本地 Node 版本为 `20.13.0`，测试与构建可通过，但 Vite 7 会警告该版本低于推荐的 `20.19.0`。发布环境应使用 Node `20.19+`。

### 4.2 后端环境变量

真实密钥仅存放在 `backend/.env` 或部署平台的秘密管理服务中，绝不能提交到仓库、镜像层、测试夹具或发布文档。应以 `backend/.env.example` 为变量名模板。

| 变量 | 是否为当前 MVP 启动必需 | 示例 | 说明 |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | 否 | `replace-with-a-server-side-secret` | 真实 `LLMAgentReviewer` 调用 DeepSeek 兼容 API 时必需。当前默认离线 reviewer 不读取该值。 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | DeepSeek ChatOpenAI 兼容 API 根地址。 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-v4-flash` | 真实 reviewer 使用的模型标识。 |

当前 Python 代码不自动解析 `.env` 文件。以本地 shell 启动时，必须先导出变量；Docker Compose 使用 `env_file` 将变量传入容器。示例：

```bash
cd backend
set -a
source .env
set +a
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4.3 前端变量

| 变量 | 本地 Vite 开发 | 同源容器部署 | 说明 |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | 留空 | 留空 | 前端默认使用相对路径 `/api/v1/...`。 |

本地 Vite 开发服务器将 `/api` 代理至 `http://127.0.0.1:8000`。容器部署不使用 Vite 开发代理，由 Nginx 承担相同路径的反向代理。不要把 `VITE_API_BASE_URL` 指向一个不同源 API，除非后端新增并验证 CORS 与认证方案。

## 5. 本地部署与启动

### 5.1 首次安装

后端：

```bash
cd /Users/xiaochao/Desktop/DocAuditAgent/backend
uv sync --extra test
```

前端：

```bash
cd /Users/xiaochao/Desktop/DocAuditAgent/frontend
npm ci
```

### 5.2 启动服务

终端一，启动后端：

```bash
cd /Users/xiaochao/Desktop/DocAuditAgent/backend
set -a
source .env
set +a
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端二，启动前端：

```bash
cd /Users/xiaochao/Desktop/DocAuditAgent/frontend
npm run dev -- --host 127.0.0.1 --port 5175
```

访问：

- 前端：`http://127.0.0.1:5175/`
- 后端健康检查：`http://127.0.0.1:8000/healthz`
- 后端 OpenAPI：`http://127.0.0.1:8000/docs`

### 5.3 本地使用步骤

1. 在前端打开“新建审核案件”。
2. 填写案件参考号并选择至少一个合同正文文件；首个文件作为正文，其余文件作为支持附件。
3. 提交后进入案件详情，等待或刷新以读取服务端当前状态。
4. 在“人工审核工作台”接收待办。
5. 进入案件级待办详情，随后进入“人工决定确认”。
6. 先填写理由并处置当前风险项，再提交同意决定。

此步骤使用 MVP 的模拟身份头。仅用于本地或受控验收，不得将其视为真实用户登录。

## 6. 容器化部署设计

当前仓库尚未包含 `Dockerfile`、Nginx 配置或 `compose.yaml`。发布实施时应在仓库根目录新增以下交付物；本节给出标准内容和职责，避免前后端容器职责混淆。

| 文件 | 责任 |
| --- | --- |
| `backend/Dockerfile` | Python 3.12 + uv 运行 FastAPI；不复制真实 `backend/.env`。 |
| `frontend/Dockerfile` | Node 构建 React 静态文件，Nginx 承载构建产物。 |
| `deploy/nginx/default.conf` | 静态 SPA 回退与 `/api` 到 `backend:8000` 的反向代理。 |
| `compose.yaml` | 编排服务网络、健康检查、环境文件和对外端口。 |
| `.dockerignore`、`frontend/.dockerignore`、`backend/.dockerignore` | 排除密钥、依赖目录、缓存、测试产物和 Git 元数据。 |

### 6.1 后端 Dockerfile 模板

`backend/Dockerfile`：

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.2 前端 Dockerfile 模板

`frontend/Dockerfile`：

```dockerfile
FROM node:20.19-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY ../deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

构建上下文必须是仓库根目录，或将 Nginx 配置复制到 `frontend/` 构建上下文内；Docker 不允许 `COPY` 读取构建上下文之外的 `../deploy`。推荐根目录构建上下文并相应调整 Dockerfile 中的 `COPY frontend/...` 路径。

### 6.3 Nginx 反向代理模板

`deploy/nginx/default.conf`：

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 6.4 Docker Compose 模板

`compose.yaml`：

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    env_file:
      - ./backend/.env
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 10s
    restart: unless-stopped

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "8080:80"
    restart: unless-stopped
```

为使上面的前端 Compose 构建上下文正确，`frontend/Dockerfile` 应改为根上下文版本：

```dockerfile
FROM node:20.19-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

## 7. Docker 启动、停止与日志

在仓库根目录，准备好 `backend/.env` 后执行：

```bash
docker compose build --pull
docker compose up -d
docker compose ps
```

注意：Nginx 模板只代理 `/api/`，而后端健康端点位于 `/healthz`。因此健康检查应通过内部网络或临时映射后端端口执行；推荐的外部页面检查为：

```bash
curl -f http://127.0.0.1:8080/
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read().decode())"
```

常用命令：

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
docker compose down --remove-orphans
```

不要在没有确认数据持久化策略前使用会删除卷的命令。当前 MVP 无业务卷，但后续接入数据库和对象存储后，`docker compose down -v` 会删除持久卷，应仅在明确授权下执行。

## 8. 版本发布流程

### 8.1 发布前检查

1. 核对工作区变更仅包含本次发布允许的代码、配置和文档；不提交 `backend/.env`、密钥或运行产物。
2. 确认 `backend/.env.example` 仅包含变量名和安全示例值。
3. 在后端执行：

   ```bash
   cd backend
   uv run pytest
   ```

4. 在前端执行：

   ```bash
   cd frontend
   npm test -- --run
   npm run build
   ```

5. 记录测试结果、镜像标签、Git 提交、部署时间、操作者和目标环境。

### 8.2 构建与发布

建议使用不可变版本标签，例如 `v1.0.0` 和对应 Git 短提交号；不要使用仅有 `latest` 的发布引用。

```bash
docker compose build --pull
docker compose up -d
docker compose ps
```

镜像推送至仓库时，发布记录至少包含前端镜像、后端镜像、Nginx 基础镜像、Python/Node 版本和依赖锁文件摘要。

### 8.3 发布后验证

1. 检查 `frontend` 和 `backend` 均为 `running`，后端为 `healthy`。
2. 打开前端首页，确认静态资源无 `404`。
3. 执行后端健康检查。
4. 按第 5.3 节完成一次“创建案件 -> 上传 -> 接收待办 -> 编辑风险 -> 同意”的受控冒烟链路。
5. 检查失败响应中包含 `X-Request-ID`，将其保留到发布记录中用于追踪。

### 8.4 回滚

当前 MVP 没有持久化数据，回滚镜像会导致进程内数据清空。仅在确认可接受该影响时执行：

```bash
docker compose down
docker compose up -d --no-build
```

实际回滚应改为部署已验证的上一版本镜像标签，而不是依赖本机镜像缓存。未来引入数据库迁移后，回滚步骤必须先评估迁移是否向后兼容、是否需要数据恢复和是否应禁写。

## 9. 外部依赖与网络

| 依赖 | 当前 MVP 是否必需 | 网络要求 | 发布前检查 |
| --- | --- | --- | --- |
| DeepSeek ChatOpenAI 兼容 API | 否，默认离线 reviewer。 | 若启用真实 reviewer，后端须可出站访问 `DEEPSEEK_BASE_URL`。 | 校验密钥来源、模型名、超时、限流策略和无密钥/网络故障降级。 |
| Docker Registry | 容器发布时必需。 | CI/CD 或部署主机访问镜像仓库。 | 使用不可变标签、镜像扫描和拉取权限最小化。 |
| TLS 终止/负载均衡 | 受控本地验收不必需；公网必需。 | 入口层配置证书与 HTTPS。 | 强制 HTTPS、HSTS、访问日志和受信任代理头策略。 |
| 数据库、对象存储、队列、缓存 | 当前不使用。 | 无。 | 引入后必须补充迁移、备份、重试、监控和恢复方案。 |

## 10. 异常排查手册

| 现象 | 常见原因 | 检查命令/位置 | 处理方式 |
| --- | --- | --- | --- |
| 后端容器无法启动 | Python 依赖未锁定、命令路径错误或端口冲突。 | `docker compose logs backend`；本地执行 `uv run uvicorn ...`。 | 使用 Python 3.12 与 `uv sync --frozen`；释放冲突端口；修复启动命令后重新构建。 |
| `/healthz` 非 `200` | Uvicorn 未就绪或应用初始化异常。 | `docker compose ps`、`docker compose logs backend`。 | 等待 healthcheck 重试；定位首个 traceback；不向前端放行不健康后端。 |
| 前端白屏或路由刷新 `404` | 静态服务器未配置 SPA 回退。 | 浏览器 Network；Nginx 错误日志。 | 配置 `try_files $uri $uri/ /index.html`，重新构建前端镜像。 |
| 前端 API 返回 `404` 或 `502` | `/api` 代理缺失、目标服务名/端口错误，或后端未健康。 | `docker compose logs frontend backend`；检查 Nginx `proxy_pass`。 | 使用 `proxy_pass http://backend:8000`，确认二者在同一 Compose 网络并等待 `service_healthy`。 |
| 浏览器跨域错误 | 将 `VITE_API_BASE_URL` 指到不同源，后端未配置 CORS。 | 浏览器 Console/Network。 | 保持同源 `/api` 代理；如必须跨域，先在后端引入受限来源的 CORS 配置并测试。 |
| `401`、`403` 或 `action_not_authorized` | 角色不足、案件范围不符，或开发身份头被入口层剥离。 | API 错误 envelope、`X-Request-ID`、后端日志。 | 本地仅使用受控模拟主体；生产改用认证中间件和服务端签发的身份上下文。 |
| `revision_conflict`、`stale_human_task` 或 `run_superseded` | 多人并发、文档重提或审核运行已切换。 | API 错误 `details` 与案件当前运行。 | 刷新案件和待办详情，读取新的 `expected_revision`；不要重放旧版本、旧运行的审批请求。 |
| `422 action_not_allowed` 同意失败 | 必处置风险项尚未处理，或证据 locator 不完整。 | 读取当前 findings 和 finding detail。 | 先提交 finding-level `edit` 等处置，再使用新 revision 提交 `approve`。 |
| 上传失败或 `upload_incomplete` | 上传会话未完成、字节数不符或重复内容冲突。 | 上传会话响应与后端错误 envelope。 | 重新创建上传批次并完整上传；不要覆盖已有不可变版本。 |
| 重启后案件/队列消失 | 当前内存存储和 checkpoint 不持久化。 | 服务重启事件、容器生命周期。 | 这是 MVP 已知限制；生产前接入数据库、对象存储和持久 checkpoint。 |
| 真实大模型调用失败 | 密钥缺失、网络/DNS/TLS、模型名错误、限流或返回非 JSON。 | 后端日志；确认不记录密钥。 | 验证 `DEEPSEEK_*` 注入和出站网络；使用超时、重试边界和保守人工分流；当前 MVP 可回退到离线 reviewer。 |
| Vite 构建警告 Node 版本不足 | Node `<20.19`。 | `node --version` 与构建日志。 | 发布镜像固定 Node `20.19+`；本地开发升级 Node 后重新安装依赖。 |

## 11. 生产化前阻断项

以下项目未完成前，不得将此版本暴露至公网处理真实合同和真实用户数据：

1. 用真实认证与授权中间件替换客户端可构造的 `X-Actor-ID`、`X-Actor-Role`；
2. 用事务数据库持久化案件、版本、决定、幂等键与审计事件；
3. 用受控对象存储保存原件和上传内容，并配置恶意文件扫描、大小限制、保留策略与备份；
4. 用持久 checkpoint 和任务系统替换内存 HITL/工作流状态；
5. 通过秘密管理服务注入模型密钥，限制出站访问，并完成模型异常、限流和费用控制；
6. 配置 HTTPS、受信任反向代理、请求大小限制、速率限制、访问日志、指标、告警和追踪；
7. 建立镜像扫描、SBOM、依赖漏洞管理、发布审批、备份演练和灾难恢复流程；
8. 执行针对真实基础设施的安全、并发、重启恢复、租户隔离和数据保留测试。

## 12. 交付验收清单

- [ ] 后端 `uv run pytest` 通过。
- [ ] 前端 `npm test -- --run` 和 `npm run build` 通过。
- [ ] `backend/.env` 未被提交，`.env.example` 不含真实密钥。
- [ ] 前端和后端镜像均基于锁定依赖构建。
- [ ] Compose 启动后后端健康检查通过，前端可访问。
- [ ] 受控冒烟链路最终为 `approved`。
- [ ] 发布记录包含版本标签、Git 提交、镜像摘要、测试结果、部署时间和回滚目标。
- [ ] 已确认当前 MVP 内存存储、模拟身份和离线 reviewer 的部署边界。
