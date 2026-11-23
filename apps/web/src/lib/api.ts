/**
 * Typed fetch wrapper for the CareerPilot API (same-origin /api/v1, proxied by Next.js rewrites).
 * Sends the CSRF token (read from the non-HttpOnly cp_csrf cookie) on state-changing requests.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId?: string,
  ) {
    super(message);
  }
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : undefined;
}

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  formData?: FormData;
};

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (method !== "GET") {
    const csrf = readCookie("cp_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  let body: BodyInit | undefined;
  if (opts.formData) body = opts.formData;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = undefined;
  }
  if (!res.ok) {
    const err = (data as { error?: { code: string; message: string; details?: Record<string, unknown>; request_id?: string } })?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "http_error",
      err?.message ?? "Something went wrong. Please try again.",
      err?.details ?? {},
      err?.request_id,
    );
  }
  return data as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const fields = (err.details?.fields as { loc: string[]; msg: string }[] | undefined) ?? [];
    const pw = err.details?.password as string[] | undefined;
    if (pw?.length) return pw.join(" ");
    if (fields.length) return fields.map((f) => `${f.loc.slice(-1)[0]}: ${f.msg}`).join("; ");
    return err.message;
  }
  return "Something went wrong. Please try again.";
}

export function newIdempotencyKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
