/** The CSRF contract the backend enforces (C3): every mutating request must
 * carry X-CSRF-Token; GETs must not trigger the csrf bootstrap. */
import { beforeEach, describe, expect, it, vi } from "vitest";

function mockFetch() {
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith("/auth/csrf")) {
      return new Response(JSON.stringify({ csrf_token: "tok.sig" }), { status: 200 });
    }
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }) as typeof fetch;
  return calls;
}

describe("api client CSRF handling", () => {
  beforeEach(() => {
    vi.resetModules(); // clear the module-level csrf token cache
  });

  it("GET does not fetch a CSRF token", async () => {
    const calls = mockFetch();
    const { api } = await import("./client");
    await api.get("/companies");
    expect(calls.map((c) => c.url)).toEqual(["/api/v1/companies"]);
  });

  it("POST bootstraps CSRF once and sends the header on every mutation", async () => {
    const calls = mockFetch();
    const { api } = await import("./client");
    await api.post("/companies", { cin: "X" });
    await api.patch("/calendar-rows/1", { status: "filed" });

    expect(calls[0].url).toBe("/api/v1/auth/csrf");
    const mutations = calls.slice(1);
    expect(mutations).toHaveLength(2);
    for (const call of mutations) {
      const headers = call.init?.headers as Record<string, string>;
      expect(headers["X-CSRF-Token"]).toBe("tok.sig");
      expect(call.init?.credentials).toBe("include");
    }
  });

  it("errors carry status and server detail", async () => {
    mockFetch();
    globalThis.fetch = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).endsWith("/auth/csrf")) {
        return new Response(JSON.stringify({ csrf_token: "tok.sig" }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "insufficient role" }), { status: 403 });
    }) as typeof fetch;
    const { api, ApiError } = await import("./client");
    try {
      await api.post("/companies", {});
      expect.unreachable("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as InstanceType<typeof ApiError>).status).toBe(403);
      expect((err as Error).message).toBe("insufficient role");
    }
  });
});
