# DocAuditAgent Mock SPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `frontend/` 交付可运行的 React 单页应用，以 MSW Mock HTTP API 实现 Pencil 设计中的 P1-P7 审核工作台流程。

**Architecture:** React Router 提供页面上下文，页面仅通过类型化 `src/api/` 请求 `/api/v1`。MSW 在开发与测试环境拦截这些请求，`src/mocks/` 维护内存案例状态；移除 Mock 启动后，组件不需要修改即可连接真实后端。

**Tech Stack:** React 19、TypeScript、Vite、React Router、MSW、Vitest、Testing Library、Lucide。

---

## 范围与覆盖关系

- 实现 P1-P7：案件列表、新建与上传、案件详情、补件、风险证据、人工审核和决定确认。
- 以 Mock 成功/失败路径替代此前规划文档中的“仅未开发占位”限制。这是用户在本轮对原规划的明确覆盖，仅限本地前端演示。
- 不实现真实认证、文件存储、后端业务判定、LangGraph 恢复或真实审批。
- 不修改 `backend/`、已有前端规划文档或 Pencil 文件。

## 文件结构

| 路径 | 职责 |
| --- | --- |
| `frontend/package.json` | 前端命令和依赖。 |
| `frontend/vite.config.ts`、`tsconfig*.json`、`index.html` | Vite 与 TypeScript 配置。 |
| `frontend/src/types/domain.ts` | 共享领域与 API envelope 类型。 |
| `frontend/src/api/client.ts`、`frontend/src/api/cases.ts`、`frontend/src/api/review.ts` | 仅含 HTTP 调用与错误映射。 |
| `frontend/src/mocks/store.ts`、`frontend/src/mocks/handlers.ts`、`frontend/src/mocks/browser.ts` | 可重置的 Mock 数据和 HTTP 处理器。 |
| `frontend/src/components/*` | 应用壳、状态、面板、表单与通知等共享 UI。 |
| `frontend/src/pages/*` | P1-P7 页面组件。 |
| `frontend/src/App.tsx`、`frontend/src/main.tsx`、`frontend/src/styles.css` | 路由、Mock 启动和设计系统。 |
| `frontend/src/**/*.test.tsx` | Mock 行为、API 客户端与关键流程测试。 |

### Task 1: 初始化独立前端工程

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/src/test/setup.ts`

- [ ] **Step 1: 写入会失败的工具链冒烟测试**

```ts
import { expect, test } from 'vitest';

test('test environment is available', () => {
  expect(import.meta.env.MODE).toBe('test');
});
```

- [ ] **Step 2: 执行测试并确认因缺少前端工程失败**

Run: `npm test -- --run src/test/smoke.test.ts`

Expected: 命令失败，提示 `package.json` 或测试命令不存在。

- [ ] **Step 3: 创建 Vite、Vitest 与 Testing Library 配置**

`package.json` 必须包含 `dev`、`build`、`test`、`test:watch` 脚本；测试环境使用 `jsdom` 与 `src/test/setup.ts`。

- [ ] **Step 4: 安装依赖并确认冒烟测试通过**

Run: `npm install && npm test -- --run src/test/smoke.test.ts`

Expected: `1 passed`。

### Task 2: 定义 API 类型和错误 envelope

**Files:**
- Create: `frontend/src/types/domain.ts`
- Create: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: 写入失败测试，验证错误 envelope 保留 `request_id`**

```ts
test('throws ApiError with safe message and request id', async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: 'revision_conflict', message: '当前任务已发生变化，请刷新后重试', request_id: 'req_42' },
  }), { status: 409 }));

  await expect(apiRequest('/api/v1/cases/case_1')).rejects.toMatchObject({
    code: 'revision_conflict', requestId: 'req_42', message: '当前任务已发生变化，请刷新后重试',
  });
});
```

- [ ] **Step 2: 运行测试并确认 `apiRequest` 未定义而失败**

Run: `npm test -- --run src/api/client.test.ts`

Expected: FAIL，原因是模块或导出不存在。

- [ ] **Step 3: 实现最小类型和 `apiRequest`**

`ApiError` 仅暴露 `code`、安全 `message`、`requestId`、`retryable` 和 `details`；非成功响应读取标准 envelope，不抛出内部响应体。

- [ ] **Step 4: 重新运行测试**

Run: `npm test -- --run src/api/client.test.ts`

Expected: PASS。

### Task 3: 建立 MSW 状态与案件生命周期接口

**Files:**
- Create: `frontend/src/mocks/store.ts`
- Create: `frontend/src/mocks/handlers.ts`
- Create: `frontend/src/mocks/browser.ts`
- Create: `frontend/src/api/cases.ts`
- Test: `frontend/src/mocks/handlers.test.ts`

- [ ] **Step 1: 写入失败测试，创建案件后返回 `created` 和可创建上传批次动作**

```ts
test('creates a case through the documented endpoint shape', async () => {
  const result = await createCase({ case_reference: 'nda-2026-099', audit_scope_id: 'scope_nda_v1', contract_type: 'nda', business_context: { purpose: '合作洽谈' } });

  expect(result.status).toBe('created');
  expect(result.allowed_actions).toContain('create_upload_batch');
});
```

- [ ] **Step 2: 运行测试并确认 API 模块不存在而失败**

Run: `npm test -- --run src/mocks/handlers.test.ts`

Expected: FAIL，原因是 `createCase` 尚未实现。

- [ ] **Step 3: 实现内存 store、MSW 处理器和案件 API**

实现 `GET /api/v1/cases`、`POST /api/v1/cases`、案件详情、上传批次创建、文件内容接收、批次提交、补件版本创建和风险查询。补件必须生成新的 `document_version_id`，提交后的案件状态必须是 `uploading`，不是 `approved`。

- [ ] **Step 4: 重跑生命周期测试**

Run: `npm test -- --run src/mocks/handlers.test.ts`

Expected: PASS。

### Task 4: 建立人工审核接口与并发冲突

**Files:**
- Create: `frontend/src/api/review.ts`
- Modify: `frontend/src/mocks/store.ts`
- Modify: `frontend/src/mocks/handlers.ts`
- Test: `frontend/src/api/review.test.ts`

- [ ] **Step 1: 写入失败测试，过期 revision 拒绝人工决定**

```ts
test('rejects a decision with an outdated expected revision', async () => {
  await expect(submitDecision('case_1', 'assignment_1', {
    action: 'approve', reason: '证据已核验', expected_revision: 0,
  })).rejects.toMatchObject({ code: 'revision_conflict' });
});
```

- [ ] **Step 2: 运行测试并确认 `submitDecision` 尚未实现**

Run: `npm test -- --run src/api/review.test.ts`

Expected: FAIL，原因是模块或导出不存在。

- [ ] **Step 3: 实现待办列表、待办接收与决定提交处理器**

实现 `GET /api/v1/review-queues/legal_review/assignments`、接收待办、决定提交；只有已接收待办且 revision 一致时允许提交。保留 `changes_requested`、`rejected`、`approved` 及转交状态。

- [ ] **Step 4: 重跑审核 API 测试**

Run: `npm test -- --run src/api/review.test.ts`

Expected: PASS。

### Task 5: 实现应用壳与共享业务组件

**Files:**
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/Notice.tsx`
- Create: `frontend/src/components/Panel.tsx`
- Create: `frontend/src/components/ContextStrip.tsx`
- Create: `frontend/src/styles.css`
- Test: `frontend/src/components/StatusBadge.test.tsx`

- [ ] **Step 1: 写入失败测试，未知状态降级为待确认**

```tsx
test('renders an unknown status as 待确认 without claiming approval', () => {
  render(<StatusBadge status="future_state" />);
  expect(screen.getByText('待确认')).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试并确认组件不存在而失败**

Run: `npm test -- --run src/components/StatusBadge.test.tsx`

Expected: FAIL，原因是 `StatusBadge` 尚未定义。

- [ ] **Step 3: 实现共享组件和 Pencil 风格 token**

应用浅灰背景、白色边框面板、深蓝主按钮、青绿色链接，提供键盘焦点。状态徽标必须包含文字，不以颜色作为唯一信息。

- [ ] **Step 4: 重跑共享组件测试**

Run: `npm test -- --run src/components/StatusBadge.test.tsx`

Expected: PASS。

### Task 6: 实现提交者流程页面 P1-P4

**Files:**
- Create: `frontend/src/pages/CaseListPage.tsx`
- Create: `frontend/src/pages/NewCasePage.tsx`
- Create: `frontend/src/pages/CaseDetailPage.tsx`
- Create: `frontend/src/pages/SupplementPage.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/pages/CaseListPage.test.tsx`
- Test: `frontend/src/pages/NewCasePage.test.tsx`

- [ ] **Step 1: 写入失败测试，筛选后列表只显示匹配状态案件**

```tsx
test('filters cases by the selected status', async () => {
  renderRoute('/cases');
  await userEvent.selectOptions(screen.getByLabelText('案件状态'), 'changes_requested');
  expect(await screen.findByText('contract-2026-001')).toBeInTheDocument();
  expect(screen.queryByText('msa-2026-006')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试并确认页面不存在而失败**

Run: `npm test -- --run src/pages/CaseListPage.test.tsx`

Expected: FAIL，原因是路由或页面组件尚未实现。

- [ ] **Step 3: 实现 P1-P4 和页面导航**

P1 使用可访问的筛选控件；P2/P4 校验案件信息和一个正文文件；P3 显示版本、运行、时间线和 `allowed_actions`；P4 提交后显示新版本处理状态。小于 768px 时列表表格替换为摘要卡片，双栏改为单列。

- [ ] **Step 4: 写入并运行新建案件流程测试**

```tsx
test('creates and submits a new case into an uploading detail view', async () => {
  renderRoute('/cases/new');
  await userEvent.type(screen.getByLabelText('案件参考号'), 'nda-2026-099');
  await userEvent.click(screen.getByRole('button', { name: '提交材料' }));
  expect(await screen.findByText('材料已提交，正在受控处理')).toBeInTheDocument();
});
```

Run: `npm test -- --run src/pages/CaseListPage.test.tsx src/pages/NewCasePage.test.tsx`

Expected: PASS。

### Task 7: 实现风险、人工审核与决定页面 P5-P7

**Files:**
- Create: `frontend/src/pages/EvidencePage.tsx`
- Create: `frontend/src/pages/ReviewWorkbenchPage.tsx`
- Create: `frontend/src/pages/DecisionConfirmPage.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/pages/EvidencePage.test.tsx`
- Test: `frontend/src/pages/DecisionConfirmPage.test.tsx`

- [ ] **Step 1: 写入失败测试，选择风险项会替换证据摘录**

```tsx
test('updates the evidence panel after selecting a finding', async () => {
  renderRoute('/cases/case_1/evidence');
  await userEvent.click(await screen.findByRole('button', { name: '保密期限' }));
  expect(screen.getByText(/保密义务持续/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试并确认证据页面不存在而失败**

Run: `npm test -- --run src/pages/EvidencePage.test.tsx`

Expected: FAIL，原因是页面组件尚未定义。

- [ ] **Step 3: 实现 P5-P7**

P5 使用可切换风险列表和证据查看器；P6 展示待办、接收动作和审核上下文；P7 显示决定、理由、并发上下文和交付预览。没有证据时阻止批准，并明确显示“待人工确认”。

- [ ] **Step 4: 写入并运行决定阻断测试**

```tsx
test('blocks approval without a decision reason', async () => {
  renderRoute('/review/confirm');
  await userEvent.click(await screen.findByRole('button', { name: '确认并提交决定' }));
  expect(screen.getByText('请填写决定理由')).toBeInTheDocument();
});
```

Run: `npm test -- --run src/pages/EvidencePage.test.tsx src/pages/DecisionConfirmPage.test.tsx`

Expected: PASS。

### Task 8: 全量验证与文档记录

**Files:**
- Modify: `docs/11_integration_testing/e2e_api_flow-v1.0.md`
- Modify: `docs/00_setup/plans/2026-08-14-frontend-mock-spa-implementation-plan.md`

- [ ] **Step 1: 运行静态检查、测试和构建**

Run: `npm run test -- --run && npm run build`

Expected: 全部测试通过，Vite 生成生产构建。

- [ ] **Step 2: 启动开发服务并在 1440px 与 390px 宽度验证所有路由**

Run: `npm run dev -- --host 127.0.0.1`

Expected: P1-P7 均可导航，窄屏无文字溢出或横向页面滚动。

- [ ] **Step 3: 记录验证结果和已知 Mock 限制**

记录命令、通过数量、浏览器视口和 Mock 仅用于本地演示的限制。

## 风险与回滚

- MSW 内存状态在刷新后重置，不可用于真实审批或文件存储。
- 后续真实 API 的路径或字段改变时，仅更新 `src/api/` 与契约测试，不在页面内修补。
- 回滚前端实现时删除 `frontend/` 新增文件；不触碰后端或已有规划文档。
