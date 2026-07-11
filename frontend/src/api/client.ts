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

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (!options.form) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = await ensureCsrf();
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "include",
    body: options.form ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
  });
  if (!res.ok) {
    const payload = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = payload.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "title" in detail
          ? String((detail as { title: unknown }).title)
          : res.statusText;
    throw new ApiError(res.status, message, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  put: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  patch: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  upload: <T,>(path: string, form: FormData) => request<T>(path, { method: "POST", form }),
  del: <T,>(path: string, body?: unknown) => request<T>(path, { method: "DELETE", body }),
};
