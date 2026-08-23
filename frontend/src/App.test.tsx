import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { App } from "./App";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const assignment = {
  assignment_id: "assignment_1", case_id: "case_1", document_version_id: "docv_1",
  audit_run_id: "run_1", baseline_version_id: "baseline_1", queue_code: "legal_review",
  assignment_status: "queued", expected_revision: 2, allowed_actions: ["accept"],
  highest_severity: "high", risk_count: 1,
};

const jsonResponse = (data: unknown) => new Response(JSON.stringify({ data }), {
  headers: { "Content-Type": "application/json" },
});

test("renders real case data without a generic unavailable capability notice", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    data: [{
      case_id: "case_1", case_reference: "contract-2026-001", contract_type: "nda",
      audit_scope_id: "scope_nda_v1", status: "human_reviewing", revision: 2,
      current_document_version: { document_version_id: "docv_1", version_number: 1, status: "ready" },
      current_audit_run: { audit_run_id: "run_1", baseline_version_id: "baseline_mvp_v1", status: "triaged" },
      allowed_actions: ["view_findings"], updated_at: "2026-08-15T00:00:00Z",
    }],
  }), { headers: { "Content-Type": "application/json" } })));
  window.history.pushState({}, "", "/cases");
  render(<App />);
  expect(await screen.findByRole("heading", { name: "审核案件" })).toBeInTheDocument();
  expect(screen.getByText("contract-2026-001")).toBeInTheDocument();
  expect(screen.getByText("本地真实后端联调")).toBeInTheDocument();
  expect(screen.queryByText(/界面能力尚未完成真实 API 接入/)).not.toBeInTheDocument();
});

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

test("assignment detail returns to the fixed review queue route", async () => {
  vi.stubGlobal("fetch", vi.fn((path: string) => Promise.resolve(jsonResponse(
    path.endsWith("/assignments/assignment_1") ? assignment : []
  ))));
  window.history.pushState({}, "", "/cases/case_1/assignments/assignment_1");
  render(<App />);
  expect(await screen.findByRole("link", { name: /返回审核队列/ })).toHaveAttribute("href", "/review");
});

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
