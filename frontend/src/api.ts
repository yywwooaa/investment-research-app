import type {
  AdminUser,
  AuthResponse,
  AuthUser,
  CompanyRecord,
  MarkdownExport,
  MessageResponse,
  RefreshResult,
  SavedIdea,
  SearchSuggestion,
  ScenarioValuation,
  Thesis,
  TrendingRow,
  UniverseRow
} from "./types";

const TOKEN_KEY = "vrw_auth_token";

type ApiRequestInit = RequestInit & {
  expireOnUnauthorized?: boolean;
};

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function readErrorMessage(response: Response) {
  const text = await response.text();
  if (!text) {
    return `Request failed: ${response.status}`;
  }
  try {
    const payload = JSON.parse(text) as { detail?: unknown; message?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (typeof payload.message === "string") {
      return payload.message;
    }
  } catch {
    // Plain-text errors are fine to show as-is.
  }
  return text;
}

async function request<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const { expireOnUnauthorized = true, ...requestInit } = init;
  const token = getStoredToken();
  const headers = new Headers(requestInit.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, {
    ...requestInit,
    headers
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    if (response.status === 401 && expireOnUnauthorized) {
      clearStoredToken();
      window.dispatchEvent(new CustomEvent("vrw-auth-expired"));
    }
    throw new Error(message || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  signup: (email: string, password: string, inviteCode: string) =>
    request<AuthResponse>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, invite_code: inviteCode || null })
    }),
  signin: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/signin", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<AuthUser>("/api/auth/me"),
  adminUsers: (adminKey: string) =>
    request<AdminUser[]>("/api/admin/users", {
      headers: { "X-Admin-Key": adminKey },
      expireOnUnauthorized: false
    }),
  signout: () => request<MessageResponse>("/api/auth/signout", { method: "POST" }),
  forgotPassword: (email: string) =>
    request<MessageResponse>("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token: string, password: string) =>
    request<MessageResponse>("/api/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) }),
  search: (query: string) => request<SearchSuggestion[]>(`/api/search?q=${encodeURIComponent(query)}`),
  universe: () => request<UniverseRow[]>("/api/universe"),
  watchlist: () => request<UniverseRow[]>("/api/watchlist"),
  trending: () => request<TrendingRow[]>("/api/trending"),
  company: (ticker: string) => request<CompanyRecord>(`/api/company/${ticker}`),
  research: (ticker: string) => request<CompanyRecord>(`/api/research/${ticker}`, { method: "POST" }),
  refresh: () => request<RefreshResult>("/api/data/refresh", { method: "POST" }),
  saved: () => request<SavedIdea[]>("/api/saved"),
  saveIdea: (ticker: string, idea: SavedIdea) =>
    request<SavedIdea>(`/api/saved/${ticker}`, { method: "PUT", body: JSON.stringify(idea) }),
  deleteIdea: (ticker: string) => request<{ deleted: boolean }>(`/api/saved/${ticker}`, { method: "DELETE" }),
  saveThesis: (ticker: string, thesis: Thesis) =>
    request<Thesis>(`/api/theses/${ticker}`, { method: "PUT", body: JSON.stringify(thesis) }),
  saveValuation: (ticker: string, valuation: ScenarioValuation) =>
    request<ScenarioValuation>(`/api/valuation/${ticker}`, { method: "PUT", body: JSON.stringify(valuation) }),
  exportSubstack: (ticker: string) =>
    request<MarkdownExport>(`/api/export/${ticker}/substack`, { method: "POST" })
};
