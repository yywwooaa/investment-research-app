import type {
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
  UniverseRow
} from "./types";

const TOKEN_KEY = "vrw_auth_token";

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const message = await response.text();
    if (response.status === 401) {
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
  signout: () => request<MessageResponse>("/api/auth/signout", { method: "POST" }),
  forgotPassword: (email: string) =>
    request<MessageResponse>("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token: string, password: string) =>
    request<MessageResponse>("/api/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) }),
  search: (query: string) => request<SearchSuggestion[]>(`/api/search?q=${encodeURIComponent(query)}`),
  universe: () => request<UniverseRow[]>("/api/universe"),
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
