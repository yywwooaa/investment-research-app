import { useEffect, useMemo, useState } from "react";
import type { Dispatch, FormEvent, SetStateAction } from "react";
import {
  BarChart3,
  BookmarkCheck,
  BookmarkPlus,
  Clipboard,
  DatabaseZap,
  FileText,
  Flame,
  Gauge,
  KeyRound,
  LineChart as LineChartIcon,
  Lock,
  LogOut,
  Mail,
  Newspaper,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Target,
  TrendingUp
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { api, clearStoredToken, getStoredToken, setStoredToken } from "./api";
import type {
  AuthResponse,
  AuthUser,
  CompanyRecord,
  MarkdownExport,
  SavedIdea,
  SearchSuggestion,
  ScenarioAssumption,
  ScenarioKey,
  ScenarioValuation,
  Stance,
  Thesis,
  UniverseRow
} from "./types";

const tabs = ["Tear Sheet", "Valuation", "Thesis", "Export"] as const;
type Tab = (typeof tabs)[number];
type AuthMode = "signin" | "signup" | "forgot" | "reset";
type SearchSurface = "rail" | "command";

const stanceOptions: Stance[] = ["Buy", "Hold", "Sell", "Under Review"];
const scenarioKeys: ScenarioKey[] = ["bull", "base", "bear"];

function formatNumber(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatPct(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value > 0 ? "+" : ""}${formatNumber(value, digits)}%`;
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatMultiple(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${formatNumber(value)}x`;
}

function linesToText(lines: string[]) {
  return lines.join("\n");
}

function textToLines(text: string) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function signalClass(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "";
}

function ideaForTicker(ticker: string, note = ""): SavedIdea {
  const date = today();
  return {
    ticker,
    note,
    priority: "Medium",
    created_at: date,
    updated_date: date
  };
}

function newsRank(item: CompanyRecord["news"][number]) {
  const sentimentWeight = item.sentiment === "Negative" ? 3 : item.sentiment === "Positive" ? 2 : 1;
  const keywordWeight = /earnings|revenue|margin|guidance|forecast|ai|chip|cloud|deal|contract|export|lawsuit|upgrade|downgrade/i.test(
    `${item.title} ${item.summary} ${item.impact_reason}`
  )
    ? 2
    : 0;
  return sentimentWeight + keywordWeight;
}

export default function App() {
  const [authToken, setAuthToken] = useState(() => getStoredToken());
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authReady, setAuthReady] = useState(!getStoredToken());
  const [universe, setUniverse] = useState<UniverseRow[]>([]);
  const [selectedTicker, setSelectedTicker] = useState("NVDA");
  const [company, setCompany] = useState<CompanyRecord | null>(null);
  const [thesisDraft, setThesisDraft] = useState<Thesis | null>(null);
  const [valuationDraft, setValuationDraft] = useState<ScenarioValuation | null>(null);
  const [exportDraft, setExportDraft] = useState<MarkdownExport | null>(null);
  const [savedIdeas, setSavedIdeas] = useState<SavedIdea[]>([]);
  const [ideaNote, setIdeaNote] = useState("");
  const [ideaPriority, setIdeaPriority] = useState<SavedIdea["priority"]>("Medium");
  const [activeTab, setActiveTab] = useState<Tab>("Tear Sheet");
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [focusedSearch, setFocusedSearch] = useState<SearchSurface | null>(null);
  const [status, setStatus] = useState("Loading research workspace...");
  const [isBusy, setIsBusy] = useState(false);

  function handleAuth(response: AuthResponse) {
    setStoredToken(response.token);
    setAuthToken(response.token);
    setAuthUser(response.user);
    setStatus("Signed in. Loading research workspace...");
  }

  async function signOut() {
    try {
      await api.signout();
    } catch {
      // Session may already be expired; local cleanup is enough.
    }
    clearStoredToken();
    setAuthToken(null);
    setAuthUser(null);
    setUniverse([]);
    setCompany(null);
    setSavedIdeas([]);
    setStatus("Signed out.");
  }

  function hydrateCompany(record: CompanyRecord, message = `${record.profile.ticker} loaded`) {
    setCompany(record);
    setThesisDraft(record.thesis);
    setValuationDraft(record.valuation);
    setExportDraft(null);
    setStatus(message);
  }

  async function loadUniverse() {
    const rows = await api.universe();
    setUniverse(rows);
    if (!rows.some((row) => row.ticker === selectedTicker) && rows[0]) {
      setSelectedTicker(rows[0].ticker);
    }
  }

  async function loadSavedIdeas() {
    const ideas = await api.saved();
    setSavedIdeas(ideas);
  }

  async function loadCompany(ticker: string) {
    setIsBusy(true);
    try {
      const record = await api.company(ticker);
      hydrateCompany(record);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to load company");
    } finally {
      setIsBusy(false);
    }
  }

  useEffect(() => {
    if (!authToken) {
      setAuthReady(true);
      return;
    }
    api.me()
      .then((user) => setAuthUser(user))
      .catch(() => {
        clearStoredToken();
        setAuthToken(null);
        setAuthUser(null);
      })
      .finally(() => setAuthReady(true));
  }, [authToken]);

  useEffect(() => {
    const expire = () => {
      setAuthToken(null);
      setAuthUser(null);
      setUniverse([]);
      setCompany(null);
      setStatus("Session expired. Sign in again.");
    };
    window.addEventListener("vrw-auth-expired", expire);
    return () => window.removeEventListener("vrw-auth-expired", expire);
  }, []);

  useEffect(() => {
    if (!authToken || !authUser) return;
    Promise.all([loadUniverse(), loadSavedIdeas()])
      .then(() => setStatus("Snapshot universe ready"))
      .catch((error) => setStatus(error instanceof Error ? error.message : "Unable to load workspace"));
  }, [authToken, authUser]);

  useEffect(() => {
    if (!authToken || !authUser) return;
    if (universe.length === 0 || universe.some((row) => row.ticker === selectedTicker)) {
      void loadCompany(selectedTicker);
    }
  }, [selectedTicker, universe, authToken, authUser]);

  useEffect(() => {
    if (!company) return;
    const saved = savedIdeas.find((idea) => idea.ticker === company.profile.ticker);
    setIdeaNote(saved?.note ?? "");
    setIdeaPriority(saved?.priority ?? "Medium");
  }, [company, savedIdeas]);

  useEffect(() => {
    if (!authToken || !authUser) return;
    const search = query.trim();
    if (!search) {
      setSuggestions([]);
      return;
    }
    const handle = window.setTimeout(() => {
      api
        .search(search)
        .then(setSuggestions)
        .catch(() => setSuggestions([]));
    }, 180);
    return () => window.clearTimeout(handle);
  }, [query, authToken, authUser]);

  const filteredUniverse = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) return universe;
    return universe.filter(
      (row) =>
        row.ticker.toLowerCase().includes(search) ||
        row.name.toLowerCase().includes(search) ||
        row.industry.toLowerCase().includes(search)
    );
  }, [query, universe]);

  const selectedSavedIdea = useMemo(
    () => (company ? savedIdeas.find((idea) => idea.ticker === company.profile.ticker) ?? null : null),
    [company, savedIdeas]
  );

  const marketDesk = useMemo(() => {
    const rows = [...universe];
    const averageDaily = rows.length ? rows.reduce((sum, row) => sum + row.daily_change_pct, 0) / rows.length : 0;
    const averageYtd = rows.length ? rows.reduce((sum, row) => sum + row.ytd_change_pct, 0) / rows.length : 0;
    const positiveCount = rows.filter((row) => row.daily_change_pct >= 0).length;
    const buys = rows.filter((row) => row.recommendation === "Buy").length;
    const holds = rows.filter((row) => row.recommendation === "Hold").length;
    const sells = rows.filter((row) => row.recommendation === "Sell").length;
    return {
      averageDaily,
      averageYtd,
      breadth: rows.length ? (positiveCount / rows.length) * 100 : 0,
      topGainers: [...rows].sort((a, b) => b.daily_change_pct - a.daily_change_pct).slice(0, 3),
      topLosers: [...rows].sort((a, b) => a.daily_change_pct - b.daily_change_pct).slice(0, 3),
      recommendationMix: { buys, holds, sells },
      heatmap: [...rows].sort((a, b) => b.relative_strength_pct - a.relative_strength_pct)
    };
  }, [universe]);

  const selectedScenario = valuationDraft ? valuationDraft[valuationDraft.selected_case] : null;

  async function refreshData() {
    setIsBusy(true);
    try {
      const result = await api.refresh();
      await loadUniverse();
      await loadCompany(selectedTicker);
      setStatus(result.message);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Refresh failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function analyzeTicker() {
    const raw = query.trim();
    const exactSuggestion = suggestions.find((suggestion) => suggestion.ticker.toLowerCase() === raw.toLowerCase());
    const shouldUseSuggestion = raw.length > 1 && suggestions[0] && !exactSuggestion;
    const ticker = (exactSuggestion?.ticker ?? (shouldUseSuggestion ? suggestions[0].ticker : raw)).toUpperCase();
    if (!ticker) {
      setStatus("Type a ticker to analyze");
      return;
    }
    setIsBusy(true);
    try {
      const record = await api.research(ticker);
      hydrateCompany(record, `${record.profile.ticker} research view ready`);
      if (universe.some((row) => row.ticker === record.profile.ticker)) {
        setSelectedTicker(record.profile.ticker);
      }
      setActiveTab("Tear Sheet");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to analyze ticker");
    } finally {
      setIsBusy(false);
    }
  }

  async function saveThesis() {
    if (!thesisDraft) return;
    setIsBusy(true);
    try {
      const saved = await api.saveThesis(thesisDraft.ticker, { ...thesisDraft, updated_date: today() });
      setThesisDraft(saved);
      await loadUniverse();
      setStatus(`${saved.ticker} thesis saved`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to save thesis");
    } finally {
      setIsBusy(false);
    }
  }

  async function saveValuation() {
    if (!valuationDraft) return;
    setIsBusy(true);
    try {
      const saved = await api.saveValuation(valuationDraft.ticker, { ...valuationDraft, updated_date: today() });
      setValuationDraft(saved);
      setStatus(`${saved.ticker} valuation saved`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to save valuation");
    } finally {
      setIsBusy(false);
    }
  }

  async function exportSubstack() {
    if (!company) return;
    setIsBusy(true);
    try {
      const exported = await api.exportSubstack(company.profile.ticker);
      setExportDraft(exported);
      setStatus(`${exported.filename} ready`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to export draft");
    } finally {
      setIsBusy(false);
    }
  }

  async function saveCurrentIdea() {
    if (!company) return;
    setIsBusy(true);
    try {
      const saved = await api.saveIdea(company.profile.ticker, {
        ...(selectedSavedIdea ?? ideaForTicker(company.profile.ticker)),
        note: ideaNote.trim(),
        priority: ideaPriority,
        updated_date: today()
      });
      setSavedIdeas((current) => [saved, ...current.filter((idea) => idea.ticker !== saved.ticker)]);
      setStatus(`${saved.ticker} saved to idea board`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to save idea");
    } finally {
      setIsBusy(false);
    }
  }

  async function removeCurrentIdea(ticker = company?.profile.ticker) {
    if (!ticker) return;
    setIsBusy(true);
    try {
      await api.deleteIdea(ticker);
      setSavedIdeas((current) => current.filter((idea) => idea.ticker !== ticker));
      setStatus(`${ticker} removed from saved ideas`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to remove saved idea");
    } finally {
      setIsBusy(false);
    }
  }

  async function openTicker(ticker: string) {
    const normalized = ticker.trim().toUpperCase();
    if (!normalized) return;
    if (universe.some((row) => row.ticker === normalized)) {
      setSelectedTicker(normalized);
      return;
    }
    setIsBusy(true);
    try {
      const record = await api.research(normalized);
      hydrateCompany(record, `${record.profile.ticker} research view ready`);
      setActiveTab("Tear Sheet");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to open ticker");
    } finally {
      setIsBusy(false);
    }
  }

  async function selectSuggestion(suggestion: SearchSuggestion) {
    setQuery(suggestion.ticker);
    setSuggestions([]);
    setFocusedSearch(null);
    await openTicker(suggestion.ticker);
  }

  function updateScenario(caseName: ScenarioKey, field: keyof ScenarioAssumption, value: number) {
    setValuationDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        [caseName]: {
          ...current[caseName],
          [field]: value
        }
      };
    });
  }

  if (!authReady) {
    return (
      <div className="auth-shell">
        <div className="auth-card compact">
          <div className="brand-mark">VR</div>
          <p>Checking session...</p>
        </div>
      </div>
    );
  }

  if (!authToken || !authUser) {
    return <AuthScreen onAuth={handleAuth} />;
  }

  return (
    <div className="app-shell">
      <aside className="coverage-rail">
        <div className="brand-block">
          <div className="brand-mark">VR</div>
          <div>
            <h1>Variant Research</h1>
            <p>AI infrastructure coverage</p>
          </div>
        </div>

        <TickerSearch
          surface="rail"
          formClassName="search-box"
          iconSize={16}
          query={query}
          setQuery={setQuery}
          suggestions={suggestions}
          focusedSearch={focusedSearch}
          setFocusedSearch={setFocusedSearch}
          onSubmit={() => void analyzeTicker()}
          onSelect={(suggestion) => void selectSuggestion(suggestion)}
          isBusy={isBusy}
          placeholder="Search name or ticker"
          inputLabel="Search universe"
          buttonLabel="Analyze"
          buttonIconSize={15}
        />

        <SavedIdeasPanel
          ideas={savedIdeas}
          activeTicker={company?.profile.ticker ?? selectedTicker}
          onOpen={(ticker) => void openTicker(ticker)}
          onRemove={(ticker) => void removeCurrentIdea(ticker)}
        />

        <div className="universe-list" aria-label="Coverage universe">
          {filteredUniverse.map((row) => (
            <button
              key={row.ticker}
              className={`universe-row ${row.ticker === selectedTicker ? "selected" : ""}`}
              onClick={() => void openTicker(row.ticker)}
            >
              <span>
                <strong>{row.ticker}</strong>
                <small>{row.name}</small>
              </span>
              <span className={`stance-pill ${row.recommendation.toLowerCase().replace(" ", "-")}`}>{row.recommendation}</span>
            </button>
          ))}
        </div>

        <div className="rail-footer">
          <button className="icon-button" type="button" onClick={refreshData} disabled={isBusy} title="Refresh data">
            <RefreshCw size={17} aria-hidden="true" />
          </button>
          <span>{status}</span>
          <button className="signout-button" type="button" onClick={() => void signOut()} title={`Sign out ${authUser.email}`}>
            <LogOut size={15} aria-hidden="true" />
            Sign out
          </button>
        </div>
      </aside>

      <main className="workbench">
        {company && thesisDraft && valuationDraft ? (
          <>
            <section className="research-command">
              <div>
                <span className="eyebrow">Equity research workflow</span>
                <h2>Type a ticker, pressure-test the thesis, save the idea.</h2>
              </div>
              <TickerSearch
                surface="command"
                formClassName="command-form"
                iconSize={18}
                query={query}
                setQuery={setQuery}
                suggestions={suggestions}
                focusedSearch={focusedSearch}
                setFocusedSearch={setFocusedSearch}
                onSubmit={() => void analyzeTicker()}
                onSelect={(suggestion) => void selectSuggestion(suggestion)}
                isBusy={isBusy}
                placeholder="Apple, SanDisk, JPM..."
                inputLabel="Analyze ticker"
                buttonLabel="Analyze"
                buttonIconSize={16}
              />
            </section>

            <MarketDeskOverview desk={marketDesk} onOpen={(ticker) => void openTicker(ticker)} />

            <header className="company-header">
              <div>
                <span className="eyebrow">{company.profile.sector} / {company.profile.industry}</span>
                <h2>{company.profile.name}</h2>
                <p>{company.profile.description}</p>
              </div>
              <div className="header-actions">
                <div className="price-tile">
                  <small>{company.profile.ticker}</small>
                  <strong>{formatMoney(company.market.price)}</strong>
                  <span className={company.market.daily_change_pct >= 0 ? "positive" : "negative"}>
                    {formatPct(company.market.daily_change_pct)}
                  </span>
                </div>
                <div className={`recommendation-tile ${company.recommendation.rating.toLowerCase().replace(" ", "-")}`}>
                  <small>Recommendation</small>
                  <strong>{company.recommendation.rating}</strong>
                  <span>{company.recommendation.confidence} confidence</span>
                </div>
                <button
                  className={`bookmark-button ${selectedSavedIdea ? "saved" : ""}`}
                  type="button"
                  onClick={() => void saveCurrentIdea()}
                  disabled={isBusy}
                  title={selectedSavedIdea ? "Update saved idea" : "Save idea"}
                >
                  {selectedSavedIdea ? <BookmarkCheck size={17} aria-hidden="true" /> : <BookmarkPlus size={17} aria-hidden="true" />}
                  {selectedSavedIdea ? "Saved" : "Save"}
                </button>
                <button className="primary-button" type="button" onClick={exportSubstack} disabled={isBusy}>
                  <FileText size={17} aria-hidden="true" />
                  Export
                </button>
              </div>
            </header>

            <section className="idea-note-panel">
              <div>
                <span className="eyebrow">Saved idea note</span>
                <p>{selectedSavedIdea ? "Capture why this name deserves follow-up." : "Bookmark this ticker and write the variant angle you want to revisit."}</p>
              </div>
              <select
                aria-label="Idea priority"
                value={ideaPriority}
                onChange={(event) => setIdeaPriority(event.target.value as SavedIdea["priority"])}
              >
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
              <textarea
                rows={2}
                value={ideaNote}
                onChange={(event) => setIdeaNote(event.target.value)}
                placeholder="Why this could work, what you need to verify, or what would change your mind..."
              />
              <button className="secondary-button" type="button" onClick={() => void saveCurrentIdea()} disabled={isBusy}>
                <Save size={16} aria-hidden="true" />
                Save note
              </button>
            </section>

            <section className="metric-grid" aria-label="Market snapshot">
              <Metric label="Market Cap" value={`${formatNumber(company.profile.market_cap, 0)}B`} />
              <Metric label="YTD" value={formatPct(company.market.ytd_change_pct)} tone={company.market.ytd_change_pct >= 0 ? "good" : "bad"} />
              <Metric label="Rel. Strength" value={formatPct(company.market.relative_strength_pct)} tone={company.market.relative_strength_pct >= 0 ? "good" : "bad"} />
              <Metric label="EV/Sales NTM" value={formatMultiple(company.market.ev_sales_ntm)} />
              <Metric label="EV/EBITDA NTM" value={formatMultiple(company.market.ev_ebitda_ntm)} />
              <Metric label="FCF Yield" value={formatPct(company.market.fcf_yield_pct)} />
              <Metric label="Signal Score" value={formatNumber(company.recommendation.score, 0)} />
            </section>

            <nav className="tab-strip" aria-label="Workbench tabs">
              {tabs.map((tab) => (
                <button
                  key={tab}
                  className={tab === activeTab ? "active" : ""}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                >
                  {tab === "Tear Sheet" && <BarChart3 size={16} aria-hidden="true" />}
                  {tab === "Valuation" && <TrendingUp size={16} aria-hidden="true" />}
                  {tab === "Thesis" && <DatabaseZap size={16} aria-hidden="true" />}
                  {tab === "Export" && <FileText size={16} aria-hidden="true" />}
                  {tab}
                </button>
              ))}
            </nav>

            {activeTab === "Tear Sheet" && <TearSheet company={company} selectedScenario={selectedScenario} />}
            {activeTab === "Valuation" && (
              <ValuationPanel valuation={valuationDraft} updateScenario={updateScenario} setValuation={setValuationDraft} save={saveValuation} />
            )}
            {activeTab === "Thesis" && <ThesisPanel thesis={thesisDraft} setThesis={setThesisDraft} save={saveThesis} />}
            {activeTab === "Export" && (
              <ExportPanel exportDraft={exportDraft} exportSubstack={exportSubstack} company={company} />
            )}
          </>
        ) : (
          <div className="empty-state">
            <LineChartIcon size={32} aria-hidden="true" />
            <p>{status}</p>
          </div>
        )}
      </main>
    </div>
  );
}

function AuthScreen({ onAuth }: { onAuth: (response: AuthResponse) => void }) {
  const resetToken = new URLSearchParams(window.location.search).get("reset_token") ?? "";
  const [mode, setMode] = useState<AuthMode>(resetToken ? "reset" : "signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [message, setMessage] = useState(resetToken ? "Enter a new password to finish resetting your account." : "");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setMessage("");
    try {
      if (mode === "signin") {
        const response = await api.signin(email, password);
        onAuth(response);
        return;
      }
      if (mode === "signup") {
        const response = await api.signup(email, password, inviteCode);
        onAuth(response);
        return;
      }
      if (mode === "forgot") {
        const response = await api.forgotPassword(email);
        setMessage(response.message);
        return;
      }
      const response = await api.resetPassword(resetToken, password);
      setMessage(response.message);
      window.history.replaceState({}, "", window.location.pathname);
      setMode("signin");
      setPassword("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark">VR</div>
          <div>
            <span className="eyebrow">Private research workspace</span>
            <h1>Variant Research Workbench</h1>
          </div>
        </div>
        <p className="auth-copy">
          Sign in to access the live research dashboard, ticker analysis, saved ideas, and Substack export tools.
        </p>

        <div className="auth-tabs" aria-label="Authentication mode">
          <button type="button" className={mode === "signin" ? "active" : ""} onClick={() => setMode("signin")}>
            Sign in
          </button>
          <button type="button" className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>
            Sign up
          </button>
        </div>

        <form className="auth-form" onSubmit={(event) => void submitAuth(event)}>
          {mode !== "reset" && (
            <label className="auth-field">
              <span>Email</span>
              <div>
                <Mail size={16} aria-hidden="true" />
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  required
                />
              </div>
            </label>
          )}

          {mode !== "forgot" && (
            <label className="auth-field">
              <span>{mode === "reset" ? "New password" : "Password"}</span>
              <div>
                <Lock size={16} aria-hidden="true" />
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="At least 8 characters"
                  required
                  minLength={8}
                />
              </div>
            </label>
          )}

          {mode === "signup" && (
            <label className="auth-field">
              <span>Invite code</span>
              <div>
                <KeyRound size={16} aria-hidden="true" />
                <input
                  value={inviteCode}
                  onChange={(event) => setInviteCode(event.target.value)}
                  placeholder="Required on the public deployment"
                />
              </div>
            </label>
          )}

          <button className="auth-submit" type="submit" disabled={isSubmitting || (mode === "reset" && !resetToken)}>
            {mode === "signin" && "Sign in"}
            {mode === "signup" && "Create account"}
            {mode === "forgot" && "Send reset email"}
            {mode === "reset" && "Reset password"}
          </button>
        </form>

        {message && <p className="auth-message">{message}</p>}

        <div className="auth-links">
          {mode !== "forgot" && mode !== "reset" && (
            <button type="button" onClick={() => setMode("forgot")}>
              Forgot password?
            </button>
          )}
          {mode !== "signin" && (
            <button type="button" onClick={() => setMode("signin")}>
              Back to sign in
            </button>
          )}
        </div>
      </section>
    </main>
  );
}

function TickerSearch({
  surface,
  formClassName,
  iconSize,
  query,
  setQuery,
  suggestions,
  focusedSearch,
  setFocusedSearch,
  onSubmit,
  onSelect,
  isBusy,
  placeholder,
  inputLabel,
  buttonLabel,
  buttonIconSize
}: {
  surface: SearchSurface;
  formClassName: string;
  iconSize: number;
  query: string;
  setQuery: Dispatch<SetStateAction<string>>;
  suggestions: SearchSuggestion[];
  focusedSearch: SearchSurface | null;
  setFocusedSearch: Dispatch<SetStateAction<SearchSurface | null>>;
  onSubmit: () => void;
  onSelect: (suggestion: SearchSuggestion) => void;
  isBusy: boolean;
  placeholder: string;
  inputLabel: string;
  buttonLabel: string;
  buttonIconSize: number;
}) {
  const showDropdown = focusedSearch === surface && query.trim().length > 0 && suggestions.length > 0;

  return (
    <div className={`ticker-search-shell ${surface}`}>
      <form
        className={formClassName}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <Search size={iconSize} aria-hidden="true" />
        <input
          aria-label={inputLabel}
          value={query}
          onFocus={() => setFocusedSearch(surface)}
          onBlur={() => window.setTimeout(() => setFocusedSearch(null), 140)}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
          autoComplete="off"
        />
        <button type="submit" disabled={isBusy} title="Analyze typed ticker">
          <Sparkles size={buttonIconSize} aria-hidden="true" />
          {buttonLabel}
        </button>
      </form>

      {showDropdown && (
        <div className="suggestion-menu" role="listbox" aria-label="Ticker suggestions">
          {suggestions.map((suggestion) => (
            <button
              key={`${suggestion.ticker}-${suggestion.source}`}
              type="button"
              role="option"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => onSelect(suggestion)}
            >
              <span className="suggestion-ticker">{suggestion.ticker}</span>
              <span>
                <strong>{suggestion.name}</strong>
                <small>
                  {[suggestion.exchange, suggestion.quote_type, suggestion.source].filter(Boolean).join(" / ")}
                </small>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className={`metric-card ${tone ?? ""}`}>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function SavedIdeasPanel({
  ideas,
  activeTicker,
  onOpen,
  onRemove
}: {
  ideas: SavedIdea[];
  activeTicker: string;
  onOpen: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}) {
  return (
    <section className="saved-rail" aria-label="Saved ideas">
      <div className="rail-section-heading">
        <span>Saved ideas</span>
        <strong>{ideas.length}</strong>
      </div>
      {ideas.length ? (
        <div className="saved-list">
          {ideas.map((idea) => (
            <article key={idea.ticker} className={`saved-card ${idea.ticker === activeTicker ? "active" : ""}`}>
              <button type="button" onClick={() => onOpen(idea.ticker)}>
                <span>
                  <strong>{idea.ticker}</strong>
                  <small>{idea.priority} priority</small>
                </span>
                <BookmarkCheck size={15} aria-hidden="true" />
              </button>
              {idea.note && <p>{idea.note}</p>}
              <button className="text-button" type="button" onClick={() => onRemove(idea.ticker)}>
                Remove
              </button>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-rail-note">Bookmark names you want to revisit and write the angle you are underwriting.</p>
      )}
    </section>
  );
}

function MarketDeskOverview({
  desk,
  onOpen
}: {
  desk: {
    averageDaily: number;
    averageYtd: number;
    breadth: number;
    topGainers: UniverseRow[];
    topLosers: UniverseRow[];
    recommendationMix: { buys: number; holds: number; sells: number };
    heatmap: UniverseRow[];
  };
  onOpen: (ticker: string) => void;
}) {
  return (
    <section className="market-desk" aria-label="Market overview">
      <div className="desk-metric">
        <Gauge size={17} aria-hidden="true" />
        <span>AI infra basket</span>
        <strong className={signalClass(desk.averageDaily)}>{formatPct(desk.averageDaily)}</strong>
      </div>
      <div className="desk-metric">
        <Target size={17} aria-hidden="true" />
        <span>Positive breadth</span>
        <strong>{formatPct(desk.breadth, 0)}</strong>
      </div>
      <div className="desk-metric">
        <TrendingUp size={17} aria-hidden="true" />
        <span>Avg YTD</span>
        <strong className={signalClass(desk.averageYtd)}>{formatPct(desk.averageYtd)}</strong>
      </div>
      <div className="desk-metric">
        <Flame size={17} aria-hidden="true" />
        <span>Signal mix</span>
        <strong>{desk.recommendationMix.buys}B / {desk.recommendationMix.holds}H / {desk.recommendationMix.sells}S</strong>
      </div>

      <div className="mover-panel">
        <span>Top gainers</span>
        {desk.topGainers.map((row) => (
          <button key={row.ticker} type="button" onClick={() => onOpen(row.ticker)}>
            <strong>{row.ticker}</strong>
            <em className="positive">{formatPct(row.daily_change_pct)}</em>
          </button>
        ))}
      </div>
      <div className="mover-panel">
        <span>Top losers</span>
        {desk.topLosers.map((row) => (
          <button key={row.ticker} type="button" onClick={() => onOpen(row.ticker)}>
            <strong>{row.ticker}</strong>
            <em className="negative">{formatPct(row.daily_change_pct)}</em>
          </button>
        ))}
      </div>
      <div className="heatmap-strip" aria-label="Watchlist heatmap">
        {desk.heatmap.map((row) => (
          <button
            key={row.ticker}
            type="button"
            className={row.relative_strength_pct >= 0 ? "heat-positive" : "heat-negative"}
            onClick={() => onOpen(row.ticker)}
            title={`${row.ticker} relative strength ${formatPct(row.relative_strength_pct)}`}
          >
            {row.ticker}
          </button>
        ))}
      </div>
    </section>
  );
}

function TearSheet({ company, selectedScenario }: { company: CompanyRecord; selectedScenario: ScenarioAssumption | null }) {
  const revenueData = company.financials.annual.map((point) => ({
    period: point.period,
    revenue: point.revenue,
    margin: point.ebitda_margin_pct ?? 0
  }));
  const rankedNews = [...company.news].sort((a, b) => newsRank(b) - newsRank(a));
  const weeklySignals = [
    `${company.profile.ticker} moved ${formatPct(company.market.daily_change_pct)} today and ${formatPct(company.market.ytd_change_pct)} YTD.`,
    `Relative strength is ${formatPct(company.market.relative_strength_pct)}, which ${company.market.relative_strength_pct >= 0 ? "supports" : "pressures"} the current signal.`,
    `${rankedNews.length} ticker-specific news item(s) are available for the current research refresh.`,
    `Base scenario shows ${selectedScenario ? formatPct(selectedScenario.implied_return_pct) : "n/a"} implied return.`
  ];

  return (
    <section className="content-grid two-column">
      <div className="panel weekly-panel">
        <div className="panel-heading">
          <h3>What Changed This Week</h3>
          <span>{company.recommendation.updated_date}</span>
        </div>
        <div className="weekly-list">
          {weeklySignals.map((signal) => (
            <div key={signal} className="weekly-row">
              <span />
              <p>{signal}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Financial Trajectory</h3>
          <LineChartIcon size={18} aria-hidden="true" />
        </div>
        <div className="chart-frame">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={revenueData} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e6e1d8" vertical={false} />
              <XAxis dataKey="period" tickLine={false} axisLine={false} />
              <YAxis yAxisId="left" tickLine={false} axisLine={false} width={42} />
              <YAxis yAxisId="right" orientation="right" tickLine={false} axisLine={false} width={42} />
              <Tooltip />
              <Line yAxisId="left" type="monotone" dataKey="revenue" name="Revenue" stroke="#256f78" strokeWidth={3} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="margin" name="EBITDA margin" stroke="#b56b38" strokeWidth={3} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Variant View</h3>
          <span className={`stance-pill ${company.thesis.stance.toLowerCase().replace(" ", "-")}`}>{company.thesis.stance}</span>
        </div>
        <p className="lead-copy">{company.thesis.one_liner}</p>
        <p>{company.thesis.variant_view}</p>
        {selectedScenario && (
          <div className="return-strip">
            <span>Base risk/reward</span>
            <strong>{formatPct(selectedScenario.implied_return_pct)}</strong>
          </div>
        )}
      </div>

      <div className="panel recommendation-panel">
        <div className="panel-heading">
          <h3>Recommendation</h3>
          <span className={`stance-pill ${company.recommendation.rating.toLowerCase().replace(" ", "-")}`}>
            {company.recommendation.rating}
          </span>
        </div>
        <p className="lead-copy">{company.recommendation.rationale}</p>
        <div className="source-line">
          <Sparkles size={15} aria-hidden="true" />
          {company.recommendation.source_status}
        </div>
        <div className="pros-cons">
          <div>
            <strong>Positive drivers</strong>
            <ul>
              {company.recommendation.positives.length ? (
                company.recommendation.positives.map((item) => <li key={item}>{item}</li>)
              ) : (
                <li>Awaiting source data.</li>
              )}
            </ul>
          </div>
          <div>
            <strong>Negative drivers</strong>
            <ul>
              {company.recommendation.negatives.length ? (
                company.recommendation.negatives.map((item) => <li key={item}>{item}</li>)
              ) : (
                <li>Awaiting source data.</li>
              )}
            </ul>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Recent News</h3>
          <Newspaper size={18} aria-hidden="true" />
        </div>
        <div className="news-list">
          {rankedNews.map((item) => (
            <article key={`${item.title}-${item.published_at}`} className="news-row">
              <div>
                <strong>{item.title}</strong>
                <span>{item.source} / {item.published_at}</span>
              </div>
              <span className={`sentiment ${item.sentiment.toLowerCase()}`}>{item.sentiment}</span>
              <p>{item.summary}</p>
              <small>Why it matters: {item.impact_reason}</small>
            </article>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Peer Comps</h3>
          <BarChart3 size={18} aria-hidden="true" />
        </div>
        <div className="chart-frame short">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={company.peers}>
              <CartesianGrid stroke="#e6e1d8" vertical={false} />
              <XAxis dataKey="ticker" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} width={38} />
              <Tooltip />
              <Bar dataKey="ev_sales_ntm" name="EV/Sales" fill="#256f78" radius={[5, 5, 0, 0]} />
              <Bar dataKey="revenue_growth_ntm_pct" name="Growth %" fill="#b56b38" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Catalysts & Risks</h3>
          <span>{company.thesis.catalysts.length} catalysts</span>
        </div>
        <div className="catalyst-list">
          {company.thesis.catalysts.map((catalyst) => (
            <div key={`${catalyst.title}-${catalyst.timing}`} className="catalyst-row">
              <strong>{catalyst.title}</strong>
              <span>{catalyst.timing}</span>
              <small>{catalyst.impact} / {catalyst.status}</small>
            </div>
          ))}
        </div>
        <ul className="risk-list">
          {company.thesis.risks.map((risk) => (
            <li key={risk}>{risk}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function ValuationPanel({
  valuation,
  updateScenario,
  setValuation,
  save
}: {
  valuation: ScenarioValuation;
  updateScenario: (caseName: ScenarioKey, field: keyof ScenarioAssumption, value: number) => void;
  setValuation: Dispatch<SetStateAction<ScenarioValuation | null>>;
  save: () => void;
}) {
  const scenarioData = scenarioKeys.map((key) => ({
    case: key.toUpperCase(),
    return: valuation[key].implied_return_pct,
    price: valuation[key].implied_price
  }));

  return (
    <section className="content-grid valuation-layout">
      <div className="panel">
        <div className="panel-heading">
          <h3>Scenario DCF</h3>
          <button className="secondary-button" type="button" onClick={save}>
            <Save size={16} aria-hidden="true" />
            Save
          </button>
        </div>
        <div className="scenario-grid">
          {scenarioKeys.map((caseName) => (
            <div key={caseName} className={`scenario-box ${valuation.selected_case === caseName ? "selected" : ""}`}>
              <button
                className="scenario-title"
                type="button"
                onClick={() => setValuation((current) => current && { ...current, selected_case: caseName })}
              >
                {caseName}
              </button>
              <NumberField label="Revenue CAGR" value={valuation[caseName].revenue_cagr_pct} suffix="%" onChange={(value) => updateScenario(caseName, "revenue_cagr_pct", value)} />
              <NumberField label="Terminal Margin" value={valuation[caseName].terminal_margin_pct} suffix="%" onChange={(value) => updateScenario(caseName, "terminal_margin_pct", value)} />
              <NumberField label="Exit Multiple" value={valuation[caseName].exit_multiple} suffix="x" onChange={(value) => updateScenario(caseName, "exit_multiple", value)} />
              <NumberField label="Discount Rate" value={valuation[caseName].discount_rate_pct} suffix="%" onChange={(value) => updateScenario(caseName, "discount_rate_pct", value)} />
              <NumberField label="Implied Price" value={valuation[caseName].implied_price} prefix="$" onChange={(value) => updateScenario(caseName, "implied_price", value)} />
              <NumberField label="Implied Return" value={valuation[caseName].implied_return_pct} suffix="%" onChange={(value) => updateScenario(caseName, "implied_return_pct", value)} />
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Risk/Reward</h3>
          <TrendingUp size={18} aria-hidden="true" />
        </div>
        <div className="chart-frame short">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={scenarioData}>
              <CartesianGrid stroke="#e6e1d8" vertical={false} />
              <XAxis dataKey="case" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} width={38} />
              <Tooltip />
              <Bar dataKey="return" name="Implied return %" fill="#256f78" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <label className="field-block">
          <span>Valuation Notes</span>
          <textarea
            rows={7}
            value={valuation.notes}
            onChange={(event) => setValuation((current) => current && { ...current, notes: event.target.value })}
          />
        </label>
      </div>
    </section>
  );
}

function NumberField({
  label,
  value,
  onChange,
  prefix = "",
  suffix = ""
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  prefix?: string;
  suffix?: string;
}) {
  return (
    <label className="number-field">
      <span>{label}</span>
      <div>
        {prefix && <small>{prefix}</small>}
        <input type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />
        {suffix && <small>{suffix}</small>}
      </div>
    </label>
  );
}

function ThesisPanel({
  thesis,
  setThesis,
  save
}: {
  thesis: Thesis;
  setThesis: Dispatch<SetStateAction<Thesis | null>>;
  save: () => void;
}) {
  return (
    <section className="content-grid thesis-layout">
      <div className="panel thesis-editor">
        <div className="panel-heading">
          <h3>Thesis Memo</h3>
          <button className="secondary-button" type="button" onClick={save}>
            <Save size={16} aria-hidden="true" />
            Save
          </button>
        </div>
        <div className="form-row">
          <label className="field-block">
            <span>Stance</span>
            <select value={thesis.stance} onChange={(event) => setThesis({ ...thesis, stance: event.target.value as Stance })}>
              {stanceOptions.map((stance) => (
                <option key={stance}>{stance}</option>
              ))}
            </select>
          </label>
          <label className="field-block">
            <span>Horizon</span>
            <input value={thesis.horizon} onChange={(event) => setThesis({ ...thesis, horizon: event.target.value })} />
          </label>
        </div>
        <label className="field-block">
          <span>One-liner</span>
          <input value={thesis.one_liner} onChange={(event) => setThesis({ ...thesis, one_liner: event.target.value })} />
        </label>
        <label className="field-block">
          <span>Variant View</span>
          <textarea rows={6} value={thesis.variant_view} onChange={(event) => setThesis({ ...thesis, variant_view: event.target.value })} />
        </label>
        <label className="field-block">
          <span>Evidence</span>
          <textarea rows={7} value={linesToText(thesis.evidence)} onChange={(event) => setThesis({ ...thesis, evidence: textToLines(event.target.value) })} />
        </label>
      </div>

      <div className="panel">
        <div className="panel-heading">
          <h3>Risks & Watch Items</h3>
          <span>{thesis.updated_date}</span>
        </div>
        <label className="field-block">
          <span>Risks</span>
          <textarea rows={8} value={linesToText(thesis.risks)} onChange={(event) => setThesis({ ...thesis, risks: textToLines(event.target.value) })} />
        </label>
        <label className="field-block">
          <span>Watch Items</span>
          <textarea rows={8} value={linesToText(thesis.watch_items)} onChange={(event) => setThesis({ ...thesis, watch_items: textToLines(event.target.value) })} />
        </label>
        <div className="catalyst-list">
          {thesis.catalysts.map((catalyst) => (
            <div key={`${catalyst.title}-${catalyst.timing}`} className="catalyst-row">
              <strong>{catalyst.title}</strong>
              <span>{catalyst.timing}</span>
              <small>{catalyst.impact} / {catalyst.status}</small>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ExportPanel({
  exportDraft,
  exportSubstack,
  company
}: {
  exportDraft: MarkdownExport | null;
  exportSubstack: () => void;
  company: CompanyRecord;
}) {
  const text = exportDraft?.markdown ?? "";

  return (
    <section className="content-grid export-layout">
      <div className="panel">
        <div className="panel-heading">
          <h3>Substack Draft</h3>
          <div className="button-row">
            <button className="secondary-button" type="button" onClick={exportSubstack}>
              <FileText size={16} aria-hidden="true" />
              Generate
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={!text}
              onClick={() => void navigator.clipboard.writeText(text)}
            >
              <Clipboard size={16} aria-hidden="true" />
              Copy
            </button>
          </div>
        </div>
        <textarea className="markdown-box" value={text} readOnly placeholder={`${company.profile.ticker} thesis draft`} />
      </div>
      <div className="panel">
        <div className="panel-heading">
          <h3>Draft Inputs</h3>
          <FileText size={18} aria-hidden="true" />
        </div>
        <dl className="export-checklist">
          <div>
            <dt>One-liner</dt>
            <dd>{company.thesis.one_liner}</dd>
          </div>
          <div>
            <dt>Evidence points</dt>
            <dd>{company.thesis.evidence.length}</dd>
          </div>
          <div>
            <dt>Catalysts</dt>
            <dd>{company.thesis.catalysts.length}</dd>
          </div>
          <div>
            <dt>Selected scenario</dt>
            <dd>{company.valuation.selected_case}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
