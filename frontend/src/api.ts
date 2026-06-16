import type { CompanyRecord, MarkdownExport, RefreshResult, ScenarioValuation, Thesis, UniverseRow } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  universe: () => request<UniverseRow[]>("/api/universe"),
  company: (ticker: string) => request<CompanyRecord>(`/api/company/${ticker}`),
  research: (ticker: string) => request<CompanyRecord>(`/api/research/${ticker}`, { method: "POST" }),
  refresh: () => request<RefreshResult>("/api/data/refresh", { method: "POST" }),
  saveThesis: (ticker: string, thesis: Thesis) =>
    request<Thesis>(`/api/theses/${ticker}`, { method: "PUT", body: JSON.stringify(thesis) }),
  saveValuation: (ticker: string, valuation: ScenarioValuation) =>
    request<ScenarioValuation>(`/api/valuation/${ticker}`, { method: "PUT", body: JSON.stringify(valuation) }),
  exportSubstack: (ticker: string) =>
    request<MarkdownExport>(`/api/export/${ticker}/substack`, { method: "POST" })
};
