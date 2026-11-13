import "server-only";

import type { NextResponse } from "next/server";

import type { TokenPair } from "./backend";

export const ACCESS_COOKIE = "st_access";
export const REFRESH_COOKIE = "st_refresh";

export function apiBaseUrl(): string {
  return process.env.SCHOOLTRACK_API_URL ?? "http://localhost:8000";
}

const secure = process.env.NODE_ENV === "production";

/** httpOnly + SameSite=Strict: browser JavaScript cannot read the tokens and other
 * sites cannot make the browser send them. */
export function storeTokens(response: NextResponse, pair: TokenPair): void {
  response.cookies.set(ACCESS_COOKIE, pair.access_token, {
    httpOnly: true,
    secure,
    sameSite: "strict",
    path: "/",
    maxAge: pair.expires_in,
  });
  response.cookies.set(REFRESH_COOKIE, pair.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: "strict",
    // Path "/" so the middleware can tell a resumable session from a missing one.
    path: "/",
    maxAge: 14 * 24 * 3600,
  });
}

export function clearTokens(response: NextResponse): void {
  response.cookies.set(ACCESS_COOKIE, "", { path: "/", maxAge: 0 });
  response.cookies.set(REFRESH_COOKIE, "", { path: "/", maxAge: 0 });
}
