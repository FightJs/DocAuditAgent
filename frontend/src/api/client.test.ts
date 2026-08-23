import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest, submitterActor } from "./client";

describe("apiRequest", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws ApiError with safe message and request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "revision_conflict",
              message: "当前任务已发生变化，请刷新后重试",
              request_id: "req_42",
              retryable: false,
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(apiRequest("/api/v1/cases/case_1")).rejects.toMatchObject({
      code: "revision_conflict",
      requestId: "req_42",
      message: "当前任务已发生变化，请刷新后重试",
    });
  });

  it("sends the local MVP actor and idempotency key for state-changing requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { case_id: "case_1" } }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/api/v1/cases", {
      method: "POST",
      actor: submitterActor,
      idempotencyKey: "case-create-1",
      body: { case_reference: "nda-1" },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/cases",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Actor-ID": "frontend-submitter",
          "X-Actor-Role": "submitter",
          "Idempotency-Key": "case-create-1",
          "Content-Type": "application/json",
        }),
      }),
    );
  });
});
