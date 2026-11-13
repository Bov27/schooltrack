/**
 * BFF proxy: /api/backend/<path> -> SchoolTrack API /api/v1/<path>, with the access
 * token taken from the httpOnly cookie (and refreshed transparently when it expires).
 */
import { type NextRequest, NextResponse } from "next/server";

import { callBackend, pickForwardedHeaders, safeApiPath } from "@/lib/backend";
import { ACCESS_COOKIE, REFRESH_COOKIE, apiBaseUrl, clearTokens, storeTokens } from "@/lib/session";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context): Promise<NextResponse> {
  const { path } = await context.params;
  const target = safeApiPath(path, request.nextUrl.search);
  if (target === null) {
    return NextResponse.json({ error: { code: "not_found", message: "Not found" } }, { status: 404 });
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const result = await callBackend(
    (input, init) => fetch(input, { ...init, cache: "no-store" }),
    apiBaseUrl(),
    target,
    {
      method: request.method,
      headers: pickForwardedHeaders(request.headers),
      body: hasBody ? await request.arrayBuffer() : undefined,
    },
    {
      accessToken: request.cookies.get(ACCESS_COOKIE)?.value ?? null,
      refreshToken: request.cookies.get(REFRESH_COOKIE)?.value ?? null,
    },
  );

  const body = result.response.status === 204 ? null : await result.response.arrayBuffer();
  const response = new NextResponse(body, { status: result.response.status });
  const contentType = result.response.headers.get("content-type");
  if (contentType) response.headers.set("content-type", contentType);
  if (result.rotated) storeTokens(response, result.rotated);
  if (result.clearSession) clearTokens(response);
  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
