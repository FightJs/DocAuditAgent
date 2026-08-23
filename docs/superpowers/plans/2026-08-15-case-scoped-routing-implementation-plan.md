# Case-Scoped Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make review assignment and approval pages recoverable from their case-scoped URLs, with deterministic parent navigation and URL-derived breadcrumbs.

**Architecture:** Keep `BrowserRouter` and the existing API client. Add one real `GET` assignment reader to the review API module, then make assignment detail and confirm pages use `caseId` and `assignmentId` route parameters as their only context source. Extract only a focused breadcrumb component so all changed pages show navigation generated from their concrete URL context; leave workflow, backend contracts, and out-of-scope pages unchanged.

**Tech Stack:** React 19, React Router 7, TypeScript, Vite, Vitest, React Testing Library, FastAPI backend API v1.

---

## Scope and Contract Guardrails

- Implement only the approved routes in [`case-scoped-routing-design.md`](../specs/2026-08-15-case-scoped-routing-design.md).
- Do not change `backend/`, API paths, API response envelopes, authorization actors, or workflow status transitions.
- Do not add routes or simulated actions for supplement, delivery, objection, reject, or request-materials flows.
- Assignment reads and actions use `approverActor`, because the live review queue and HITL action API require that actor in the current frontend contract.
- A stale or missing assignment must display the backend-safe error and offer only an explicit parent route, never a browser-history fallback.

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `frontend/src/api/review.ts` | Modify | Add the typed, real case-scoped assignment read function. |
| `frontend/src/api/review.test.ts` | Modify | Verify the assignment read URL and actor headers without changing existing HITL request checks. |
| `frontend/src/components/Breadcrumbs.tsx` | Create | Render URL-derived, accessible breadcrumbs without owning data fetching. |
| `frontend/src/components/Breadcrumbs.test.tsx` | Create | Verify breadcrumb labels and parent links. |
| `frontend/src/App.tsx` | Modify | Add case-scoped assignment/detail routes, replace state/history navigation, and attach breadcrumbs. |
| `frontend/src/App.test.tsx` | Modify | Verify queue-to-assignment navigation, refresh-safe confirmation, and explicit parent destinations. |
| `frontend/src/styles.css` | Modify only if needed | Apply minimal styling for the breadcrumb list using existing color and spacing tokens. |
| `docs/11_integration_testing/frontend_backend_integration-v1.0.md` | Modify | Record the executed route-level real API regression and its result. |

### Task 1: Add the Real Assignment Read API

**Files:**
- Modify: `frontend/src/api/review.ts`
- Modify: `frontend/src/api/review.test.ts`

- [ ] **Step 1: Write the failing API contract test**

  Add `getAssignment` to the test import and append this test. It fixes the endpoint, actor, and data envelope expected by the route pages.

  ```ts
  test("reads one assignment through the real case-scoped endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      data: { assignment_id: "assignment_1", case_id: "case_1", expected_revision: 4 },
    }), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAssignment("case_1", "assignment_1")).resolves.toMatchObject({
      assignment_id: "assignment_1", case_id: "case_1", expected_revision: 4,
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/cases/case_1/assignments/assignment_1", expect.objectContaining({
      headers: expect.objectContaining({ "X-Actor-ID": "frontend-approver", "X-Actor-Role": "approver" }),
    }));
  });
  ```

- [ ] **Step 2: Run the focused test and confirm it fails because `getAssignment` is not exported**

  Run: `npm test -- --run frontend/src/api/review.test.ts`

  Expected: TypeScript/Vitest reports that `getAssignment` is not exported from `./review`.

- [ ] **Step 3: Implement the smallest API wrapper**

  Add this export below `listAssignments` in `frontend/src/api/review.ts`:

  ```ts
  export const getAssignment = (caseId: string, assignmentId: string) =>
    apiRequest<Assignment>(`/api/v1/cases/${caseId}/assignments/${assignmentId}`, {
      actor: approverActor,
    });
  ```

- [ ] **Step 4: Run the API tests and confirm the route contract passes**

  Run: `npm test -- --run frontend/src/api/review.test.ts`

  Expected: all `review.test.ts` tests pass, including `reads one assignment through the real case-scoped endpoint`.

- [ ] **Step 5: Commit the contract change**

  ```bash
  git add frontend/src/api/review.ts frontend/src/api/review.test.ts
  git commit -m "feat: read review assignments by case-scoped route"
  ```

### Task 2: Add a Focused URL Breadcrumb Component

**Files:**
- Create: `frontend/src/components/Breadcrumbs.tsx`
- Create: `frontend/src/components/Breadcrumbs.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing breadcrumb rendering tests**

  Create `frontend/src/components/Breadcrumbs.test.tsx` with these assertions. The component intentionally receives display labels and route destinations rather than inferring backend data.

  ```tsx
  import { render, screen } from "@testing-library/react";
  import { MemoryRouter } from "react-router-dom";
  import { expect, test } from "vitest";
  import { Breadcrumbs } from "./Breadcrumbs";

  test("links every non-current URL context and marks the current context", () => {
    render(<MemoryRouter><Breadcrumbs items={[
      { label: "案件列表", to: "/cases" },
      { label: "case_1", to: "/cases/case_1" },
      { label: "风险与证据" },
    ]}/></MemoryRouter>);

    expect(screen.getByRole("link", { name: "案件列表" })).toHaveAttribute("href", "/cases");
    expect(screen.getByRole("link", { name: "case_1" })).toHaveAttribute("href", "/cases/case_1");
    expect(screen.getByText("风险与证据")).toHaveAttribute("aria-current", "page");
  });
  ```

- [ ] **Step 2: Run the focused test and confirm it fails because the component does not exist**

  Run: `npm test -- --run frontend/src/components/Breadcrumbs.test.tsx`

  Expected: Vitest cannot resolve `./Breadcrumbs`.

- [ ] **Step 3: Create the presentational component**

  Create `frontend/src/components/Breadcrumbs.tsx`:

  ```tsx
  import { Link } from "react-router-dom";

  export type BreadcrumbItem = { label: string; to?: string };

  export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
    return <nav aria-label="面包屑"><ol className="breadcrumbs">
      {items.map((item, index) => <li key={`${item.label}-${index}`}>
        {item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}
      </li>)}
    </ol></nav>;
  }
  ```

  Add only the following layout rule to `frontend/src/styles.css`; preserve all existing declarations:

  ```css
  .breadcrumbs { display: flex; gap: 8px; align-items: center; margin: 0 0 16px; padding: 0; list-style: none; }
  .breadcrumbs li + li::before { content: "/"; margin-right: 8px; color: var(--muted); }
  ```

- [ ] **Step 4: Run component tests and TypeScript build**

  Run: `npm test -- --run frontend/src/components/Breadcrumbs.test.tsx && npm run build`

  Expected: breadcrumb test and production build both pass.

- [ ] **Step 5: Commit the shared navigation primitive**

  ```bash
  git add frontend/src/components/Breadcrumbs.tsx frontend/src/components/Breadcrumbs.test.tsx frontend/src/styles.css
  git commit -m "feat: add explicit route breadcrumbs"
  ```

### Task 3: Establish Route-Level Failure Tests

**Files:**
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add controlled fetch helpers and the failing behavior tests**

  Import `fireEvent` from `@testing-library/react`. Add a helper which dispatches real contract-shaped envelopes by request path and tests that express the approved behavior:

  ```tsx
  const assignment = {
    assignment_id: "assignment_1", case_id: "case_1", document_version_id: "docv_1",
    audit_run_id: "run_1", baseline_version_id: "baseline_1", queue_code: "legal_review",
    assignment_status: "queued", expected_revision: 2, allowed_actions: ["accept"],
    highest_severity: "high", risk_count: 1,
  };

  test("accepting a queue item goes to its case-scoped assignment page", async () => {
    vi.stubGlobal("fetch", vi.fn((path: string, init?: RequestInit) => {
      if (path.includes("review-queues")) return Promise.resolve(jsonResponse([assignment]));
      if (path.endsWith("/accept")) return Promise.resolve(jsonResponse({ ...assignment, assignment_status: "accepted", expected_revision: 3 }));
      if (path.endsWith("/assignments/assignment_1")) return Promise.resolve(jsonResponse({ ...assignment, assignment_status: "accepted", expected_revision: 3 }));
      if (path.includes("/findings")) return Promise.resolve(jsonResponse([]));
      return Promise.reject(new Error(`unexpected request ${path} ${init?.method ?? "GET"}`));
    }));
    window.history.pushState({}, "", "/review");
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "接收待办" }));
    expect(await screen.findByRole("heading", { name: "待办详情" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/cases/case_1/assignments/assignment_1");
  });

  test("confirmation refresh loads assignment from URL without location state", async () => {
    vi.stubGlobal("fetch", vi.fn((path: string) => {
      if (path.endsWith("/assignments/assignment_1")) return Promise.resolve(jsonResponse({ ...assignment, assignment_status: "accepted" }));
      if (path.endsWith("/findings")) return Promise.resolve(jsonResponse([{ finding_id: "finding_1", title: "风险", severity: "high", status: "open" }]));
      if (path.endsWith("/findings/finding_1")) return Promise.resolve(jsonResponse({ finding_id: "finding_1", title: "风险", severity: "high", status: "open", summary: "需要复核", source_locator: { locator_id: "locator_1", locator_status: "available", quote: "原文" } }));
      return Promise.reject(new Error(`unexpected request ${path}`));
    }));
    window.history.pushState({}, "", "/cases/case_1/assignments/assignment_1/confirm");
    render(<App />);
    expect(await screen.findByText("docv_1 · run_1 · baseline_1")).toBeInTheDocument();
    expect(screen.queryByText("请先从真实待办队列接收任务。")).not.toBeInTheDocument();
  });
  ```

  Define the helper at test-module scope so every stub returns the response envelope consumed by `apiRequest`:

  ```tsx
  const jsonResponse = (data: unknown) => new Response(JSON.stringify({ data }), {
    headers: { "Content-Type": "application/json" },
  });
  ```

- [ ] **Step 2: Run the route behavior tests and confirm they fail on the existing global confirm route**

  Run: `npm test -- --run frontend/src/App.test.tsx`

  Expected: the queue test remains at `/review/confirm` and the refresh test shows the existing “请先从真实待办队列接收任务。” fallback.

### Task 4: Refactor Review Queue into Case-Scoped Assignment Detail

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Implement explicit queue-to-detail navigation and the assignment detail page**

  In `frontend/src/App.tsx`, import `Breadcrumbs` and `getAssignment`; remove the `useLocation` import. Change the successful queue accept navigation to:

  ```tsx
  navigate(`/cases/${accepted.case_id}/assignments/${accepted.assignment_id}`);
  ```

  Add an `AssignmentDetail` component which reads route values, fetches its authoritative assignment, and offers only explicit routes:

  ```tsx
  function AssignmentDetail() {
    const { caseId = "", assignmentId = "" } = useParams();
    const [assignment, setAssignment] = useState<Assignment>();
    const [error, setError] = useState("");
    useEffect(() => { getAssignment(caseId, assignmentId).then(setAssignment).catch((cause) => setError(errorText(cause))); }, [caseId, assignmentId]);
    if (error) return <Shell><Breadcrumbs items={[{ label: "审核队列", to: "/review" }, { label: "待办详情" }]}/><Notice tone="danger">{error}</Notice><Link to="/review">返回审核队列</Link></Shell>;
    if (!assignment) return <Shell><Breadcrumbs items={[{ label: "审核队列", to: "/review" }, { label: "待办详情" }]}/><p>正在读取待办…</p></Shell>;
    return <Shell><Breadcrumbs items={[{ label: "审核队列", to: "/review" }, { label: assignment.case_id, to: `/cases/${assignment.case_id}` }, { label: "待办详情" }]}/><PageHeader title="待办详情" description="待办上下文、责任和 revision 由真实后端响应决定。"/><Panel title="当前待办"><p>{assignment.document_version_id} · {assignment.audit_run_id} · {assignment.baseline_version_id}</p><p>{assignment.highest_severity} · {assignment.risk_count} 项风险</p></Panel><div className="actions"><Link className="button secondary" to="/review"><ArrowLeft size={16}/>返回审核队列</Link><Link className="button" to={`/cases/${assignment.case_id}/assignments/${assignment.assignment_id}/confirm`}>进入决定确认</Link></div></Shell>;
  }
  ```

  Add route-level breadcrumb calls to `Detail` and `Evidence` with the approved hierarchy. `Evidence` must include an explicit `<Link to={`/cases/${caseId}`}>` return control, rather than a history navigation call.

- [ ] **Step 2: Update route declarations**

  Replace the global confirm declaration with the two approved case-scoped declarations:

  ```tsx
  <Route path="/cases/:caseId/assignments/:assignmentId" element={<AssignmentDetail/>}/>
  <Route path="/cases/:caseId/assignments/:assignmentId/confirm" element={<Confirm/>}/>
  ```

  Delete `<Route path="/review/confirm" element={<Confirm/>}/>` so unsupported global deep links cannot render a context-free page.

- [ ] **Step 3: Run the failing queue test and confirm it now passes**

  Run: `npm test -- --run frontend/src/App.test.tsx -t "accepting a queue item"`

  Expected: the page heading is `待办详情` and `window.location.pathname` equals `/cases/case_1/assignments/assignment_1`.

- [ ] **Step 4: Add and run an explicit parent-navigation test**

  Append this test to `frontend/src/App.test.tsx`:

  ```tsx
  test("assignment detail returns to the fixed review queue route", async () => {
    vi.stubGlobal("fetch", vi.fn((path: string) => Promise.resolve(jsonResponse(
      path.endsWith("/assignments/assignment_1") ? assignment : []
    ))));
    window.history.pushState({}, "", "/cases/case_1/assignments/assignment_1");
    render(<App />);
    expect(await screen.findByRole("link", { name: /返回审核队列/ })).toHaveAttribute("href", "/review");
  });
  ```

  Run: `npm test -- --run frontend/src/App.test.tsx -t "fixed review queue"`

  Expected: PASS.

- [ ] **Step 5: Commit the detail route implementation**

  ```bash
  git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/Breadcrumbs.tsx frontend/src/styles.css
  git commit -m "feat: add case-scoped review assignment detail"
  ```

### Task 5: Make Confirmation Refresh-Safe and Remove History/State Navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Replace `location.state` with URL parameters and assignment retrieval**

  Replace the beginning of `Confirm` with the following state setup and read effect. This makes a fresh browser load use only the route and live backend result.

  ```tsx
  function Confirm() {
    const { caseId = "", assignmentId = "" } = useParams();
    const [assignment, setAssignment] = useState<Assignment>();
    const [finding, setFinding] = useState<FindingDetail>();
    const [reason, setReason] = useState("");
    const [message, setMessage] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [revision, setRevision] = useState<number>();
    const [findingReviewed, setFindingReviewed] = useState(false);

    useEffect(() => {
      getAssignment(caseId, assignmentId).then(setAssignment).catch((cause) => setMessage(errorText(cause)));
    }, [caseId, assignmentId]);

    useEffect(() => {
      if (!assignment) return;
      listFindings(assignment.case_id, assignment.audit_run_id, approverActor)
        .then(async (items) => {
          if (!items[0]) throw new Error("当前运行没有可审批的风险项");
          setFinding(await getFinding(assignment.case_id, assignment.audit_run_id, items[0].finding_id, approverActor));
        })
        .catch((cause) => setMessage(errorText(cause)));
    }, [assignment]);
  ```

  Keep all action payload fields sourced from the fetched `assignment`. Continue using `revision ?? assignment.expected_revision` so an edit response immediately supplies the revision for approval.

- [ ] **Step 2: Replace all history-based return behavior with the approved explicit parent route**

  Delete `useNavigate()` from `Confirm`, delete the `if (!assignment)` state fallback, and replace the return button with a `Link`:

  ```tsx
  <Link className="button secondary" to={`/cases/${caseId}/assignments/${assignmentId}`}>
    <ArrowLeft size={16}/>返回待办详情
  </Link>
  ```

  Prepend the confirmation hierarchy in its successful, loading, and error states:

  ```tsx
  <Breadcrumbs items={[
    { label: "审核队列", to: "/review" },
    { label: caseId, to: `/cases/${caseId}` },
    { label: "待办详情", to: `/cases/${caseId}/assignments/${assignmentId}` },
    { label: "决定确认" },
  ]}/>
  ```

  Do not call `navigate(-1)` anywhere in `frontend/src/App.tsx`; remove any now-unused `useNavigate` import only where no longer used by another page.

- [ ] **Step 3: Run the refresh test and confirm it passes without router state**

  Run: `npm test -- --run frontend/src/App.test.tsx -t "confirmation refresh"`

  Expected: PASS, displaying `docv_1 · run_1 · baseline_1` after a direct load of `/cases/case_1/assignments/assignment_1/confirm`.

- [ ] **Step 4: Add and run the confirmation parent-link assertion**

  Append this test:

  ```tsx
  test("confirmation returns to its exact assignment detail parent", async () => {
    vi.stubGlobal("fetch", vi.fn((path: string) => {
      if (path.endsWith("/assignments/assignment_1")) return Promise.resolve(jsonResponse(assignment));
      if (path.endsWith("/findings")) return Promise.resolve(jsonResponse([]));
      return Promise.reject(new Error(`unexpected request ${path}`));
    }));
    window.history.pushState({}, "", "/cases/case_1/assignments/assignment_1/confirm");
    render(<App />);
    expect(await screen.findByRole("link", { name: /返回待办详情/ })).toHaveAttribute("href", "/cases/case_1/assignments/assignment_1");
  });
  ```

  Run: `npm test -- --run frontend/src/App.test.tsx -t "exact assignment detail parent"`

  Expected: PASS.

- [ ] **Step 5: Verify banned navigation mechanisms are gone**

  Run: `rg -n "useLocation|location\.state|navigate\(-1\)|/review/confirm" frontend/src`

  Expected: no matches.

- [ ] **Step 6: Commit refresh-safe confirmation**

  ```bash
  git add frontend/src/App.tsx frontend/src/App.test.tsx
  git commit -m "feat: recover approval confirmation from case-scoped URL"
  ```

### Task 6: Full Verification and Integration Record

**Files:**
- Modify: `docs/11_integration_testing/frontend_backend_integration-v1.0.md`

- [ ] **Step 1: Run the complete frontend verification suite**

  Run: `npm test -- --run && npm run build`

  Working directory: `/Users/xiaochao/Desktop/DocAuditAgent/frontend`

  Expected: every Vitest file passes and `tsc -b && vite build` exits with code 0. Record the test count and build result in the integration record.

- [ ] **Step 2: Run the backend regression suite unchanged**

  Run: `uv run pytest`

  Working directory: `/Users/xiaochao/Desktop/DocAuditAgent/backend`

  Expected: the existing backend test suite passes. Do not alter backend code to accommodate this frontend-only refactor.

- [ ] **Step 3: Execute a real API route regression through the Vite proxy**

  With backend running at `http://127.0.0.1:8000` and frontend running at `http://127.0.0.1:5175`, repeat the existing supported chain using the proxy base URL:

  ```text
  POST /api/v1/cases
  POST /api/v1/cases/{case_id}/upload-batches
  PUT  /api/v1/upload-sessions/{upload_session_id}/content
  POST /api/v1/upload-batches/{upload_batch_id}/submit
  GET  /api/v1/review-queues/legal_review/assignments?status=queued
  POST /api/v1/cases/{case_id}/assignments/{assignment_id}/accept
  GET  /api/v1/cases/{case_id}/assignments/{assignment_id}
  GET  /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/findings
  GET  /api/v1/cases/{case_id}/audit-runs/{audit_run_id}/findings/{finding_id}
  POST /api/v1/cases/{case_id}/assignments/{assignment_id}/decisions (edit)
  POST /api/v1/cases/{case_id}/assignments/{assignment_id}/decisions (approve)
  ```

  Expected statuses: `201`, `201`, `200`, `202`, `200`, `200`, `200`, `200`, `200`, `201`, `201`; the final case status is `approved`.

- [ ] **Step 4: Record concrete results and commit verification documentation**

  Append the command results, backend/frontend endpoints, exact route regression statuses, and any environment constraint to `docs/11_integration_testing/frontend_backend_integration-v1.0.md`. Do not record secrets or request credentials.

  ```bash
  git add docs/11_integration_testing/frontend_backend_integration-v1.0.md
  git commit -m "docs: record case-scoped routing integration verification"
  ```

## Self-Review

- Spec coverage: Task 1 adds the required real assignment query; Tasks 3-5 implement all approved case-scoped routes, queue navigation, refresh recovery, explicit return routes, and URL-derived breadcrumbs; Task 6 runs the required frontend, backend, build, and real API regression checks.
- Contract consistency: every assignment route is `/api/v1/cases/${caseId}/assignments/${assignmentId}`; confirmation remains `/cases/${caseId}/assignments/${assignmentId}/confirm`; all HITL mutations retain fetched assignment context and revision.
- Non-goals: no task changes backend routes, roles, workflow state machine, or unimplemented supplement/delivery/objection functionality.
- Placeholder scan: this document contains no implementation placeholders or deferred behavior; all code and commands required by each task are included above.
