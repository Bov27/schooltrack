"use client";

import { useCallback, useEffect, useState } from "react";

import type { ApiErrorBody } from "./types";

const INSTITUTION_KEY = "schooltrack.institution";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export function getInstitution(): string | null {
  try {
    return window.localStorage.getItem(INSTITUTION_KEY);
  } catch {
    return null;
  }
}

export function setInstitution(id: string): void {
  try {
    window.localStorage.setItem(INSTITUTION_KEY, id);
  } catch {
    // Storage unavailable: the API falls back to the user's only membership.
  }
}

export function errorMessage(body: ApiErrorBody, status: number): string {
  const error = body.error;
  if (error?.details?.length) {
    return error.details.map((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join("; ");
  }
  return error?.message ?? `La solicitud falló (error ${status})`;
}

/** Calls the API through the BFF proxy (cookies carry the session). */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("content-type", "application/json");
  const institution = getInstitution();
  if (institution) headers.set("x-institution-id", institution);

  const response = await fetch(`/api/backend/${path.replace(/^\//, "")}`, { ...init, headers });
  if (response.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new ApiError(401, "La sesión expiró");
  }
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, errorMessage(body as ApiErrorBody, response.status));
  return body as T;
}

export function useApi<T>(path: string | null): {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
} {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setLoading(true);
    api<T>(path)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, loading, reload };
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
