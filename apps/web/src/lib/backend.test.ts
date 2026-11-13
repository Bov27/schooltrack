import { describe, expect, it } from "vitest";

import { type FetchLike, callBackend, pickForwardedHeaders, safeApiPath } from "./backend";

const BASE = "http://api.test";
const PAIR = { access_token: "new-access", refresh_token: "new-refresh", expires_in: 900 };

interface Call {
  url: string;
  auth: string | null;
  body: string | null;
}

/** A fake API: answers 401 to the expired token, accepts the new one. */
function fakeApi(options: { refreshOk: boolean }): { fetch: FetchLike; calls: Call[] } {
  const calls: Call[] = [];
  const fetch: FetchLike = async (url, init) => {
    const headers = new Headers(init?.headers);
    const raw = init?.body;
    const body =
      raw === undefined || raw === null
        ? null
        : typeof raw === "string"
          ? raw
          : new TextDecoder().decode(raw as ArrayBuffer);
    calls.push({ url, auth: headers.get("authorization"), body });
    if (url.endsWith("/auth/refresh")) {
      return options.refreshOk
        ? new Response(JSON.stringify(PAIR), { status: 200 })
        : new Response("{}", { status: 401 });
    }
    const ok = headers.get("authorization") === "Bearer new-access";
    return new Response(ok ? '{"ok":true}' : "{}", { status: ok ? 200 : 401 });
  };
  return { fetch, calls };
}

describe("callBackend", () => {
  it("passes through when the access token is valid", async () => {
    const api = fakeApi({ refreshOk: true });
    const result = await callBackend(api.fetch, BASE, "/api/v1/users/me", {}, {
      accessToken: "new-access",
      refreshToken: "r",
    });
    expect(result.response.status).toBe(200);
    expect(result.rotated).toBeNull();
    expect(api.calls).toHaveLength(1);
  });

  it("refreshes once on 401 and retries with the same body", async () => {
    const api = fakeApi({ refreshOk: true });
    const result = await callBackend(
      api.fetch,
      BASE,
      "/api/v1/campuses",
      { method: "POST", body: '{"name":"Sede"}' },
      { accessToken: "expired", refreshToken: "old-refresh" },
    );
    expect(result.response.status).toBe(200);
    expect(result.rotated).toEqual(PAIR);
    expect(result.clearSession).toBe(false);
    expect(api.calls.map((c) => c.url)).toEqual([
      `${BASE}/api/v1/campuses`,
      `${BASE}/api/v1/auth/refresh`,
      `${BASE}/api/v1/campuses`,
    ]);
    expect(api.calls[2]?.body).toBe('{"name":"Sede"}');
    expect(api.calls[1]?.body).toBe('{"refresh_token":"old-refresh"}');
  });

  it("clears the session when refreshing fails", async () => {
    const api = fakeApi({ refreshOk: false });
    const result = await callBackend(api.fetch, BASE, "/api/v1/users/me", {}, {
      accessToken: "expired",
      refreshToken: "revoked",
    });
    expect(result.response.status).toBe(401);
    expect(result.clearSession).toBe(true);
    expect(result.rotated).toBeNull();
  });

  it("uses the refresh token when there is no access token", async () => {
    const api = fakeApi({ refreshOk: true });
    const result = await callBackend(api.fetch, BASE, "/api/v1/users/me", {}, {
      accessToken: null,
      refreshToken: "old-refresh",
    });
    expect(result.response.status).toBe(200);
    expect(api.calls).toHaveLength(2);
  });

  it("never sends a stale authorization header without tokens", async () => {
    const api = fakeApi({ refreshOk: true });
    const result = await callBackend(
      api.fetch,
      BASE,
      "/api/v1/users/me",
      { headers: { authorization: "Bearer injected" } },
      { accessToken: null, refreshToken: null },
    );
    expect(api.calls[0]?.auth).toBeNull();
    expect(result.clearSession).toBe(true);
  });
});

describe("safeApiPath", () => {
  it("maps segments under /api/v1", () => {
    expect(safeApiPath(["attendance", "events"], "?limit=5")).toBe("/api/v1/attendance/events?limit=5");
  });

  it.each([[[]], [[".."]], [["users", ".."]], [["a/b"]], [[""]], [["a\\b"]]])(
    "rejects %j",
    (segments) => {
      expect(safeApiPath(segments, "")).toBeNull();
    },
  );

  it("encodes segments", () => {
    expect(safeApiPath(["geofences", "a b"], "")).toBe("/api/v1/geofences/a%20b");
  });
});

describe("pickForwardedHeaders", () => {
  it("forwards only the allow-listed headers", () => {
    const picked = pickForwardedHeaders(
      new Headers({
        "content-type": "application/json",
        "x-institution-id": "abc",
        cookie: "st_access=secret",
        authorization: "Bearer from-browser",
      }),
    );
    expect([...picked.keys()].sort()).toEqual(["content-type", "x-institution-id"]);
  });
});
