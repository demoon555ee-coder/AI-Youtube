export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

let csrfToken: string | null = null;

const CSRF_EXEMPT_PREFIXES = [
  "/api/v1/auth/register",
  "/api/v1/auth/login",
  "/api/v1/auth/google/start",
  "/api/v1/billing/webhooks",
];

function requiresCsrf(path: string, method?: string): boolean {
  const unsafe = ["POST", "PUT", "PATCH", "DELETE"].includes((method || "GET").toUpperCase());
  if (!unsafe) return false;
  return !CSRF_EXEMPT_PREFIXES.some((prefix) => path.startsWith(prefix));
}

async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  const response = await fetch(`${API_BASE}/api/v1/auth/csrf`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: Unable to initialize CSRF protection`);
  }
  const data = (await response.json()) as { csrf_token?: string | null };
  if (!data.csrf_token) throw new Error("CSRF token unavailable");
  csrfToken = data.csrf_token;
  return csrfToken;
}

export function clearCsrfToken(): void {
  csrfToken = null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (requiresCsrf(path, init?.method)) {
    headers["X-CSRF-Token"] = await ensureCsrfToken();
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
    cache: "no-store",
    headers,
  });

  if (!response.ok) {
    let detail = await response.text();
    try {
      const parsed = JSON.parse(detail);
      detail = parsed.detail || detail;
    } catch {
      // Keep raw response when it is not JSON.
    }
    if (response.status === 403 && requiresCsrf(path, init?.method)) {
      csrfToken = null;
    }
    if (response.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.localStorage.removeItem("youtube_ai_channel_id");
      window.location.assign("/login?reason=session-expired");
    }
    throw new Error(`API ${response.status}: ${detail}`);
  }

  return response.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function getStoredChannelId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("youtube_ai_channel_id");
}

export function storeChannelId(channelId: string): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem("youtube_ai_channel_id", channelId);
  }
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> { return request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) }); }
