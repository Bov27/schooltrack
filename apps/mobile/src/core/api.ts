/**
 * API client for the mobile app. Platform-independent: fetch and secure storage are
 * injected, so the token logic is unit-tested in Node.
 *
 * - The access token lives only in memory.
 * - The refresh token lives in the OS keystore (expo-secure-store).
 * - Refreshing is single-flight: concurrent 401s share ONE refresh request. Two parallel
 *   refreshes with the same token would look like token theft to the server, which
 *   revokes the whole login (ADR / docs/api/authentication.md).
 */

export interface SecureStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
  ) {
    super(message);
  }
}

/** Raised when the session cannot be resumed; the app must show the login screen. */
export class SessionExpiredError extends ApiError {
  constructor() {
    super(401, "Tu sesión expiró. Inicia sesión de nuevo.", "unauthorized");
  }
}

export const REFRESH_KEY = "schooltrack.refresh_token";
export const INSTITUTION_KEY = "schooltrack.institution";

interface ErrorBody {
  error?: { code?: string; message?: string };
}

export interface ApiClientOptions {
  baseUrl: string;
  fetch: FetchLike;
  storage: SecureStorage;
}

export class ApiClient {
  private accessToken: string | null = null;
  private refreshing: Promise<boolean> | null = null;
  institutionId: string | null = null;

  constructor(private readonly options: ApiClientOptions) {}

  async login(email: string, password: string): Promise<void> {
    const response = await this.options.fetch(`${this.options.baseUrl}/api/v1/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw await toApiError(response);
    await this.store((await response.json()) as TokenPair);
  }

  /** Resume a previous session from the keystore (app start). */
  async resume(): Promise<boolean> {
    this.institutionId = await this.options.storage.get(INSTITUTION_KEY);
    return this.refresh();
  }

  async logout(): Promise<void> {
    const refreshToken = await this.options.storage.get(REFRESH_KEY);
    this.accessToken = null;
    await this.options.storage.remove(REFRESH_KEY);
    if (refreshToken) {
      await this.options
        .fetch(`${this.options.baseUrl}/api/v1/auth/logout`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
        .catch(() => undefined);
    }
  }

  async selectInstitution(id: string): Promise<void> {
    this.institutionId = id;
    await this.options.storage.set(INSTITUTION_KEY, id);
  }

  async request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
    let response = await this.send(path, init);
    if (response.status === 401) {
      if (!(await this.refresh())) throw new SessionExpiredError();
      response = await this.send(path, init);
      if (response.status === 401) throw new SessionExpiredError();
    }
    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  /** Like request(), but also returns the status (201 = new, 200 = idempotent replay). */
  async requestWithStatus<T>(path: string, init: { method?: string; body?: unknown }): Promise<{ status: number; data: T }> {
    let response = await this.send(path, init);
    if (response.status === 401) {
      if (!(await this.refresh())) throw new SessionExpiredError();
      response = await this.send(path, init);
    }
    if (!response.ok) throw await toApiError(response);
    return { status: response.status, data: (await response.json()) as T };
  }

  private send(path: string, init: { method?: string; body?: unknown }): Promise<Response> {
    const headers: Record<string, string> = {};
    if (this.accessToken) headers.authorization = `Bearer ${this.accessToken}`;
    if (this.institutionId) headers["x-institution-id"] = this.institutionId;
    if (init.body !== undefined) headers["content-type"] = "application/json";
    return this.options.fetch(`${this.options.baseUrl}/api/v1/${path.replace(/^\//, "")}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  }

  private refresh(): Promise<boolean> {
    this.refreshing ??= this.doRefresh().finally(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  private async doRefresh(): Promise<boolean> {
    const refreshToken = await this.options.storage.get(REFRESH_KEY);
    if (!refreshToken) return false;
    let response: Response;
    try {
      response = await this.options.fetch(`${this.options.baseUrl}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      return false; // offline: keep the stored token, try again later
    }
    if (!response.ok) {
      if (response.status === 401) await this.options.storage.remove(REFRESH_KEY);
      this.accessToken = null;
      return false;
    }
    await this.store((await response.json()) as TokenPair);
    return true;
  }

  private async store(pair: TokenPair): Promise<void> {
    this.accessToken = pair.access_token;
    await this.options.storage.set(REFRESH_KEY, pair.refresh_token);
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as ErrorBody;
  return new ApiError(
    response.status,
    body.error?.message ?? `Error ${response.status}`,
    body.error?.code,
  );
}
