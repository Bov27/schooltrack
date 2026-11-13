import { type NextRequest, NextResponse } from "next/server";

import { REFRESH_COOKIE, apiBaseUrl, clearTokens } from "@/lib/session";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (refreshToken) {
    // Revoke the login server-side; ignore failures, cookies are cleared regardless.
    await fetch(`${apiBaseUrl()}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    }).catch(() => undefined);
  }
  const response = new NextResponse(null, { status: 204 });
  clearTokens(response);
  return response;
}
