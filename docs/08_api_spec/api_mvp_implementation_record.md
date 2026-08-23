# API MVP 实施记录

## 目标

将 API v1.0 契约落地为可离线运行的 FastAPI MVP，覆盖案件、版本化上传、状态查询、HITL 队列/人工决定、异议和交付。

## 输入

- `docs/08_api_spec/api_spec-v1.0.md`
- `docs/06_system_architecture/backend_service_architecture_spec-v1.0.md`
- `docs/07_data_model/human_interaction_decision_models.md`
- `docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md`

## 结论与关键决策

1. MVP 使用内存服务，保留案件、文档版本、上传会话、运行、待办、决定、异议和交付的不可变标识与历史投影；后续可替换持久化实现而不改变 API。
2. 写接口统一校验主体角色、`Idempotency-Key`、`expected_revision` 和文档版本/运行/基线三元组；错误使用 `error.code/message/details/retryable/request_id` envelope。
3. 人工决定是批准、驳回、补件、转交和风险接受的唯一业务入口；上传完成或运行完成不会自动表达 `approved`。
4. Kimi 通过 `KimiChatModel` 兼容适配层读取 `KIMI_BASE_URL`、`KIMI_MODEL`、`KIMI_API_KEY`；默认 stub 保障离线测试，不写入真实密钥。

## 验证

- `python3 -m compileall backend/app`：通过。
- `PYTHONPATH=. uv run --extra test pytest`：18 passed，1 个 Starlette/httpx 弃用警告。
- Lead 启动 `uv run uvicorn app.main:app` 并验证 `/healthz` 返回 `{"status":"ok"}`，创建案件 smoke 请求返回 `201`。
- 首轮测试发现接收待办的 revision 未写回权威 assignment，已修复并重跑全套测试通过。

## 风险与下一阶段交付物

- 当前服务为进程内内存存储，重启后数据丢失；生产阶段需接入事务数据库、对象存储和队列，并保持版本/运行只读边界。
- 当前模型适配器不主动联网；生产配置需显式注入 `ChatOpenAI` 客户端并增加超时、重试和审计。
- 下一阶段：接入真实认证与持久化、补充端到端 API 测试、将 workflow/HITL 恢复与服务决定提交做事务化关联。
