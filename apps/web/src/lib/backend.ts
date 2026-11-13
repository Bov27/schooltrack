/**
 * Server-side calls from the Next.js BFF to the SchoolTrack API.
 *
 * Tokens never reach browser JavaScript: they live in httpOnly cookies and are attached
 * here. When the access token has expired, the refresh token is used once and the call
 * retried; if refreshing fails the session is cleared.
 *
 * Pure (fetch is injected), so the refresh logic is unit-tested without a server.
 */

export interface Tokens {
  accessToken: string | null;
  refreshToken: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface BackendResult {
  response: Response;
  /** New tokens to store, when a refresh happened. */
  rotated: TokenPair | null;
  /** True when the session is no longer valid and cookies must be cleared. */
  clearSession: boolean;
}

/** Request headers the BFF forwards to the API. Everything else is dropped. */
export const FORWARDED_HEADERS = ["content-type", "x-institution-id", "x-request-id"] as const;

export function pickForwardedHeaders(source: Headers): Headers {
  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = source.get(name);
    if (value !== null) headers.set(name, value);
  }
  return headers;
}

function withAuth(init: RequestInit, accessToken: string | null): RequestInit {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
  else headers.delete("authorization");
  return { ...init, headers };
}

export async function refreshTokens(
  fetchImpl: FetchLike,
  baseUrl: string,
  refreshToken: string,
): Promise<TokenPair | null> {
  const response = await fetchImpl(`${baseUrl}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return null;
  return (await response.json()) as TokenPair;
}

export async function callBackend(
  fetchImpl: FetchLike,
  baseUrl: string,
  path: string,
  init: RequestInit,
  tokens: Tokens,
): Promise<BackendResult> {
  const url = `${baseUrl}${path}`;
  // The body may be a one-shot stream; buffer it so a retry can resend it.
  const body = init.body === undefined || init.body === null ? undefined : await new Response(init.body).arrayBuffer();
  const request: RequestInit = { ...init, body };

  if (tokens.accessToken) {
    const first = await fetchImpl(url, withAuth(request, tokens.accessToken));
    if (first.status !== 401) return { response: first, rotated: null, clearSession: false };
  }
  if (!tokens.refreshToken) {
    const response = await fetchImpl(url, withAuth(request, null));
    return { response, rotated: null, clearSession: response.status === 401 };
  }

  const rotated = await refreshTokens(fetchImpl, baseUrl, tokens.refreshToken);
  if (rotated === null) {
    const response = await fetchImpl(url, withAuth(request, null));
    return { response, rotated: null, clearSession: true };
  }
  const retried = await fetchImpl(url, withAuth(request, rotated.access_token));
  return { response: retried, rotated, clearSession: false };
}

/** Only API paths under /api/v1 may be proxied; no traversal, no absolute URLs. */
export function safeApiPath(segments: string[], search: string): string | null {
  if (segments.length === 0) return null;
  for (const segment of segments) {
    if (segment === "" || segment === "." || segment === ".." || segment.includes("/") || segment.includes("\\")) {
      return null;
    }
  }
  const encoded = segments.map(encodeURIComponent).join("/");
  return `/api/v1/${encoded}${search}`;
}
