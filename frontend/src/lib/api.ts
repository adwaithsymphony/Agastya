// Thin fetch wrapper: same-origin cookies, CSRF double-submit header, typed errors.

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (Array.isArray(this.details)) {
      for (const d of this.details as { field?: string; message?: string }[]) {
        if (d.field) out[d.field] = (d.message ?? "").replace(/^Value error, /, "");
      }
    }
    return out;
  }
}

function csrfToken(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)agastya_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

type Opts = { method?: string; body?: unknown; form?: FormData; headers?: Record<string, string>; signal?: AbortSignal };

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (method !== "GET") {
    const t = csrfToken();
    if (t) headers["X-CSRF-Token"] = t;
  }
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Can't reach the AGASTYA server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = (data as { error?: { code: string; message: string; details?: unknown } })?.error;
    const apiErr = new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `Request failed (${res.status}).`, err?.details);
    if (res.status === 401) window.dispatchEvent(new CustomEvent("agastya:unauthorized"));
    throw apiErr;
  }
  return data as T;
}

export function idempotencyKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
