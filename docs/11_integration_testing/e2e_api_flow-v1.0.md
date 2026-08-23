# 后端 MVP E2E API 链路测试记录 v1.0

## 1. 目标与输入

本记录验证后端 MVP 在不调用外部大模型、不使用真实密钥的条件下，是否按 API 契约完成案件、上传、审核、HITL 和交付的关键端到端链路。

输入依据：

- `docs/08_api_spec/api_spec-v1.0.md`
- `docs/04_core_interaction_flows/langchain_hitl_arch-v1.0.md`
- `backend/app/` 当前 API、服务、工作流及 HITL 实现

测试使用 `OfflineMvpReviewer` 和 FastAPI `TestClient`。每条用例创建独立应用实例及内存状态，因此不会产生网络调用、持久化数据或外部模型费用。

## 2. 覆盖范围

| 用例 | API 链路与断言 |
| --- | --- |
| 审批与交付闭环 | 创建案件 -> 创建上传批次 -> 上传内容 -> 提交 -> 审核队列 -> approver 接收 -> finding edit -> approve -> 幂等重放 -> operator 创建交付；确认终态为 `delivered`。 |
| 补件分支 | 创建并提交材料 -> reviewer 接收 -> `request_supplement`；确认案件为 `changes_requested`，提交者可读取当前版本的材料请求。 |
| 授权与并发 | 确认 submitter 无法读取审核队列；旧 `expected_revision` 接收待办返回 `revision_conflict`；reviewer 创建交付返回 `action_not_authorized`。 |
| 上下文失效 | V1 进入人工审核且待办已接收后提交基于 V1 的 V2；确认旧待办写入返回 `run_superseded` 或 `stale_human_task`，当前运行切换为 V2。 |

幂等覆盖包括案件级批准决定的同键同请求重放，返回同一 `decision_id` 且状态码均为 `201`。

## 3. TDD 记录

先新增只依赖 `client` fixture 的单测，并在 fixture 未实现时执行：

```text
uv run --extra test pytest tests/e2e/test_api_flow.py::test_e2e_client_fixture_is_available -q
结果：ERROR，fixture 'client' not found
```

随后在 `backend/tests/conftest.py` 提供隔离的离线应用 fixture，并完成 API 链路用例。

## 4. 执行结果

执行目录：`backend/`

```text
uv run --extra test pytest tests/e2e -q
....                                                                     [100%]
4 passed in 0.78s
```

### Lead 统一 MVP 验收（2026-08-15）

在 `backend/` 执行完整测试套件：

```text
uv run --extra test pytest -q
91 passed
```

随后以 `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001` 启动服务，
`GET /healthz` 返回 `{"status":"ok"}`；携带提交者主体和幂等键的
`POST /api/v1/cases` 返回 `201`，并返回新建案件的权威状态投影。验收服务已停止。

## 5. 结论与风险

离线 MVP 的核心 API 闭环、补件、授权/乐观并发、幂等重放和旧上下文失效均通过验证。测试只使用过程内内存存储与确定性审核器；未覆盖真实对象存储、数据库事务/重启恢复、认证提供方、异步任务队列、外部 DeepSeek/K3 调用及多进程并发。这些能力进入生产接入前需要针对实际基础设施补充集成和安全测试。

## 6. 下一阶段交付物

- 在部署环境中执行 API 冒烟测试（`/healthz` 与受认证写入/读取请求）。
- 接入实际持久化与认证后，补充事务、租户隔离、重启恢复和并发抢单测试。
- 将生产 LLM 适配器置于受密钥管理的环境变量配置下，并补充网络失败、限流和模型不可用的降级测试。
