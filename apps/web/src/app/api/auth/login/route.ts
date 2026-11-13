import { type NextRequest, NextResponse } from "next/server";

import type { TokenPair } from "@/lib/backend";
import { apiBaseUrl, storeTokens } from "@/lib/session";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.text();
  const upstream = await fetch(`${apiBaseUrl()}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    cache: "no-store",
  });
  const payload: unknown = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(payload, { status: upstream.status });
  }
  const response = NextResponse.json({ ok: true });
  storeTokens(response, payload as TokenPair);
  return response;
}
