import { afterEach, describe, expect, it, vi } from "vitest";
import { submitDocument } from "./cases";

afterEach(() => vi.restoreAllMocks());

describe("case API", () => {
  it("creates a case, uploads its bytes, and submits the batch in contract order", async () => {
    const responses = [
      { data: { case_id: "case_1" } },
      { data: { upload_batch_id: "batch_1", document_version_id: "docv_1", revision: 1, files: [{ upload_session_id: "ups_1", role: "primary_contract" }] } },
      { data: { upload_session_id: "ups_1", status: "completed" } },
      { data: { case_id: "case_1", document_version_id: "docv_1", audit_run_id: "run_1", case_status: "human_reviewing" } },
    ];
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(responses.shift()), { headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);

    const result = await submitDocument(
      {
        case_reference: "nda-2026-099",
        audit_scope_id: "scope_nda_v1",
        contract_type: "nda",
        business_context: { purpose: "合作洽谈" },
      },
      [new File(["contract text"], "contract.txt", { type: "text/plain" })],
    );

    expect(result).toMatchObject({ case_id: "case_1", audit_run_id: "run_1" });
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/cases",
      "/api/v1/cases/case_1/upload-batches",
      "/api/v1/upload-sessions/ups_1/content",
      "/api/v1/upload-batches/batch_1/submit",
    ]);
  });
});
