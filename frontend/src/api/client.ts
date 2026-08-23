import { ApiError, type ApiErrorEnvelope, type ApiSuccess } from "../types/domain";

export type ApiActor = {
  id: string;
  role: "submitter" | "reviewer" | "approver" | "operator";
};

export const submitterActor: ApiActor = { id: "frontend-submitter", role: "submitter" };
export const approverActor: ApiActor = { id: "frontend-approver", role: "approver" };

type RequestOptions = Omit<RequestInit, "body" | "headers"> & {
  actor?: ApiActor;
  body?: unknown;
  rawBody?: BodyInit;
  headers?: HeadersInit;
  idempotencyKey?: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

export function newIdempotencyKey(scope: string): string {
  return `${scope}-${crypto.randomUUID()}`;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { actor, body, rawBody, headers, idempotencyKey, ...init } = options;
  if (body !== undefined && rawBody !== undefined) {
    throw new Error("JSON body and raw body cannot be supplied together");
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(actor ? { "X-Actor-ID": actor.id, "X-Actor-Role": actor.role } : {}),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      ...headers,
    },
    body: rawBody ?? (body === undefined ? undefined : JSON.stringify(body)),
  });
  const payload = (await response.json()) as ApiSuccess<T> | ApiErrorEnvelope;
  if (!response.ok) {
    throw new ApiError((payload as ApiErrorEnvelope).error);
  }
  return (payload as ApiSuccess<T>).data;
}
