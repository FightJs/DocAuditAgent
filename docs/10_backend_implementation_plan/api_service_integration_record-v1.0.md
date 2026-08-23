# API / Schema / Service 集成实现记录 v1.0

## 目标

将 `docs/08_api_spec/api_spec-v1.0.md` 中的 MVP API 契约接入既有 Workflow 与 HITL 模块，提供可运行的 FastAPI 服务。实现仅使用服务端权威的案件、文档版本、审核运行、待办、决定与交付投影；前端不接触 checkpoint 或 `thread_id`。

## 输入

- `docs/08_api_spec/api_spec-v1.0.md`
- `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`
- Workflow 公共接口 `AuditWorkflowRunner`
- HITL 公共接口 `HitlService`

## 实现结论

- `backend/app/main.py` 创建 FastAPI 应用，统一错误 envelope、`request_id`、字段校验和本地 MVP 认证主体头。
- `backend/app/api/routes.py` 覆盖案件、上传、状态/运行/风险查询、人工队列、接收待办、提交决定、异议及交付 API。
- `backend/app/services/audit_service.py` 保存进程内权威业务投影，强制版本/运行/基线三元组、乐观 revision 与按主体/资源/动作范围的幂等键。
- 文件上传创建不可变文档版本；重新提交会将旧版本/运行置为只读并使旧 HITL 中断失效。
- 审核 Workflow 自动路径最多进入 `ready_for_delivery`，不会把案件写为 `approved`；只有当前有效上下文中授权的人工 `approve` 决定可写入 `approved`。
- finding 级 `edit`、`accept_risk`、`withdraw`、`correct` 不消费 LangGraph 中断：它们只追加人工决定并更新风险投影，原中断保持 `pending`。
- `approve` 的证据引用必须属于同一案件、文档版本和审核运行；交付只能引用有效的人工批准决定。
- `.env.example` 只包含 DeepSeek ChatOpenAI 兼容变量名与安全示例值；真实 `backend/.env` 未被实现写入或测试读取。

## 接口前提

本地 MVP 的认证主体由宿主层传入 `X-Actor-ID` 和 `X-Actor-Role`，用于验证服务端角色与数据可见性；生产环境需替换为真实认证中间件，不能信任来自公网客户端的该两项头。

## 验证

在 `backend/` 执行：

```bash
uv run --no-project --with 'fastapi>=0.116,<1' --with 'langgraph>=1.0,<2' --with 'langchain-openai>=1.1,<2' --with 'httpx>=0.28,<1' --with 'pytest>=8.4,<10' pytest -q
```

结果：`87 passed`。

另外已验证 `uvicorn app.main:app` 启动后：

- `GET /healthz` 返回 `200` 和 `{ "status": "ok" }`；
- `POST /api/v1/cases` 使用提交者主体和幂等键返回 `201`。

## 风险与下一阶段

- 当前存储和 checkpoint 均为进程内 MVP 实现，进程重启后不保留业务事实；生产阶段需以事务数据库和持久 checkpoint 替换。
- 本地认证头仅为联调接缝，生产部署必须在 API 网关或认证中间件中签发并验证主体。
- 真实 DeepSeek 调用已由 Workflow 的 ChatOpenAI 兼容适配层隔离；完整离线测试继续使用确定性 reviewer，避免测试依赖网络或真实密钥。
