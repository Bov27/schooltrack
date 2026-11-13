import { describe, expect, it } from "vitest";

import { ApiClient, type FetchLike, REFRESH_KEY, type SecureStorage, SessionExpiredError } from "./api";

class MemoryStorage implements SecureStorage {
  data = new Map<string, string>();
  async get(key: string) {
    return this.data.get(key) ?? null;
  }
  async set(key: string, value: string) {
    this.data.set(key, value);
  }
  async remove(key: string) {
    this.data.delete(key);
  }
}

/** Fake server: one valid access token at a time; refresh tokens are single-use. */
function fakeServer() {
  let counter = 0;
  let currentAccess: string | null = null;
  const calls: string[] = [];
  const validRefresh = new Set<string>(["refresh-0"]);
  const issue = () => {
    counter++;
    currentAccess = `access-${counter}`;
    validRefresh.add(`refresh-${counter}`);
    return Response.json({
      access_token: currentAccess,
      refresh_token: `refresh-${counter}`,
      expires_in: 900,
    });
  };
  const fetch: FetchLike = async (url, init) => {
    const path = url.replace("http://api.test/api/v1/", "");
    calls.push(path);
    if (path === "auth/login") return issue();
    if (path === "auth/logout") return new Response(null, { status: 204 });
    if (path === "auth/refresh") {
      const { refresh_token } = JSON.parse(String(init?.body)) as { refresh_token: string };
      if (!validRefresh.delete(refresh_token)) return Response.json({}, { status: 401 });
      return issue();
    }
    const auth = new Headers(init?.headers).get("authorization");
    if (currentAccess === null || auth !== `Bearer ${currentAccess}`) {
      return Response.json({}, { status: 401 });
    }
    return Response.json({ path });
  };
  return {
    fetch,
    calls,
    expireAccess: () => {
      currentAccess = "expired-on-server";
    },
  };
}

function client(server: ReturnType<typeof fakeServer>, storage = new MemoryStorage()) {
  return { api: new ApiClient({ baseUrl: "http://api.test", fetch: server.fetch, storage }), storage };
}

describe("ApiClient", () => {
  it("logs in, keeps the refresh token in secure storage and calls the API", async () => {
    const server = fakeServer();
    const { api, storage } = client(server);
    await api.login("ana@colegio.test", "pw");
    expect(storage.data.get(REFRESH_KEY)).toBe("refresh-1");
    expect(await api.request<{ path: string }>("users/me")).toEqual({ path: "users/me" });
  });

  it("refreshes once when the access token expires and retries", async () => {
    const server = fakeServer();
    const { api } = client(server);
    await api.login("ana@colegio.test", "pw");
    server.expireAccess();
    const result = await api.request<{ path: string }>("attendance/state");
    expect(result).toEqual({ path: "attendance/state" });
    expect(server.calls.filter((c) => c === "auth/refresh")).toHaveLength(1);
  });

  it("shares one refresh between concurrent requests (no token-reuse alarm)", async () => {
    const server = fakeServer();
    const storage = new MemoryStorage();
    storage.data.set(REFRESH_KEY, "refresh-0");
    const { api } = client(server, storage);
    const results = await Promise.all([api.request("a"), api.request("b"), api.request("c")]);
    expect(results).toEqual([{ path: "a" }, { path: "b" }, { path: "c" }]);
    expect(server.calls.filter((c) => c === "auth/refresh")).toHaveLength(1);
  });

  it("resumes a session from secure storage", async () => {
    const server = fakeServer();
    const storage = new MemoryStorage();
    storage.data.set(REFRESH_KEY, "refresh-0");
    const { api } = client(server, storage);
    expect(await api.resume()).toBe(true);
    expect(storage.data.get(REFRESH_KEY)).toBe("refresh-1");
  });

  it("drops a revoked refresh token and reports the expired session", async () => {
    const server = fakeServer();
    const storage = new MemoryStorage();
    storage.data.set(REFRESH_KEY, "revoked");
    const { api } = client(server, storage);
    await expect(api.request("users/me")).rejects.toBeInstanceOf(SessionExpiredError);
    expect(storage.data.has(REFRESH_KEY)).toBe(false);
  });

  it("keeps the refresh token when offline", async () => {
    const storage = new MemoryStorage();
    storage.data.set(REFRESH_KEY, "refresh-0");
    const offline: FetchLike = async () => {
      throw new TypeError("Network request failed");
    };
    const api = new ApiClient({ baseUrl: "http://api.test", fetch: offline, storage });
    expect(await api.resume()).toBe(false);
    expect(storage.data.get(REFRESH_KEY)).toBe("refresh-0");
  });

  it("sends the selected institution and clears tokens on logout", async () => {
    const server = fakeServer();
    const seen: (string | null)[] = [];
    const storage = new MemoryStorage();
    const api = new ApiClient({
      baseUrl: "http://api.test",
      storage,
      fetch: (url, init) => {
        seen.push(new Headers(init?.headers).get("x-institution-id"));
        return server.fetch(url, init);
      },
    });
    await api.login("ana@colegio.test", "pw");
    await api.selectInstitution("inst-1");
    await api.request("campuses");
    expect(seen.at(-1)).toBe("inst-1");
    await api.logout();
    expect(storage.data.has(REFRESH_KEY)).toBe(false);
    expect(server.calls.at(-1)).toBe("auth/logout");
  });
});
