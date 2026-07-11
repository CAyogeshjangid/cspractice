/** Typed API client. Handles the CSRF bootstrap: every mutating request
 * carries X-CSRF-Token matching the praxis_csrf cookie (charter C3). */

let csrfToken: string | null = null;

async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const res = await fetch("/api/v1/auth/csrf", { credentials: "include" });
  const body = (await res.json()) as { csrf_token: string };
  csrfToken = body.csrf_token;
  return csrfToken;
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = await ensureCsrf();
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "include",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiError(res.status, (detail as { detail?: string }).detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export interface Company {
  id: string;
  cin: string;
  name: string;
  agm_date: string | null;
  fy_end_month: number;
  fy_end_day: number;
}
