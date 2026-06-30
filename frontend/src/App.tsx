import { useEffect, useMemo, useState } from "react";
import type { Dispatch, FormEvent, SetStateAction } from "react";
import {
  BarChart3,
  BookmarkCheck,
  BookmarkPlus,
  Calculator,
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
  ShieldCheck,
  Target,
  TrendingUp,
  Users,
  X
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { api, clearStoredToken, getStoredToken, setStoredToken } from "./api";
import type {
  AdminUser,
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
  TrendingRow,
  UniverseRow
} from "./types";

const tabs = ["Tear Sheet", "Valuation", "DCF Report", "Thesis", "Export"] as const;
type Tab = (typeof tabs)[number];
type AuthMode = "signin" | "signup" | "forgot" | "reset";
type SearchSurface = "rail" | "command";
type DcfForecastRow = {
  year: string;
  revenue: number;
  fcf: number;
  pvFcf: number;
};
type DcfSensitivityCell = {
  terminalGrowthPct: number;
  impliedPrice: number;
};
type DcfSensitivityRow = {
  waccPct: number;
  cells: DcfSensitivityCell[];
};
type DcfReportModel = {
  caseName: ScenarioKey;
  currentPrice: number;
  intrinsicValue: number;
  impliedReturnPct: number;
  waccPct: number;
  terminalGrowthPct: number;
  fcfMarginPct: number;
  revenueCagrPct: number;
  baseRevenue: number;
  shares: number;
  netDebt: number;
  forecast: DcfForecastRow[];
  pvFcf: number;
  terminalValue: number;
  pvTerminalValue: number;
  enterpriseValue: number;
  equityValue: number;
  sensitivityGrowths: number[];
  sensitivity: DcfSensitivityRow[];
};

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

function formatCompactBillions(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })}B`;
}

function formatMultiple(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${formatNumber(value)}x`;
}

function hasConcreteSource(source: string | null | undefined) {
  if (!source) return false;
  return !/(fixture|synthetic|scaffold|unavailable|no current|not returned|empty|rate limit|api information|invalid|missing)/i.test(source);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function calculateDcfValue({
  baseRevenue,
  revenueCagrPct,
  fcfMarginPct,
  waccPct,
  terminalGrowthPct,
  netDebt,
  shares
}: {
  baseRevenue: number;
  revenueCagrPct: number;
  fcfMarginPct: number;
  waccPct: number;
  terminalGrowthPct: number;
  netDebt: number;
  shares: number;
}) {
  const wacc = Math.max(waccPct / 100, 0.01);
  const terminalGrowth = Math.min(terminalGrowthPct / 100, wacc - 0.005);
  const revenueGrowth = revenueCagrPct / 100;
  const fcfMargin = fcfMarginPct / 100;
  const forecast = Array.from({ length: 5 }, (_, index) => {
    const year = index + 1;
    const revenue = baseRevenue * (1 + revenueGrowth) ** year;
    const fcf = revenue * fcfMargin;
    const pvFcf = fcf / (1 + wacc) ** year;
    return { year: `${new Date().getFullYear() + year}`, revenue, fcf, pvFcf };
  });
  const finalFcf = forecast[forecast.length - 1]?.fcf ?? 0;
  const terminalValue = finalFcf * (1 + terminalGrowth) / Math.max(wacc - terminalGrowth, 0.005);
  const pvTerminalValue = terminalValue / (1 + wacc) ** forecast.length;
  const pvFcf = forecast.reduce((sum, row) => sum + row.pvFcf, 0);
  const enterpriseValue = pvFcf + pvTerminalValue;
  const equityValue = enterpriseValue - netDebt;
  const impliedPrice = shares > 0 ? equityValue / shares : 0;

  return {
    forecast,
    pvFcf,
    terminalValue,
    pvTerminalValue,
    enterpriseValue,
    equityValue,
    impliedPrice
  };
}

function buildDcfReport(company: CompanyRecord, valuation: ScenarioValuation): DcfReportModel {
  const caseName = valuation.selected_case;
  const assumption = valuation[caseName];
  const currentPrice = company.market.price;
  const latestRevenue = company.financials.annual[company.financials.annual.length - 1]?.revenue ?? valuation.base_year_revenue;
  const baseRevenue = Math.max(valuation.base_year_revenue || latestRevenue || 0, 0);
  const sharesFromMarketCap = currentPrice > 0 ? company.profile.market_cap / currentPrice : 0;
  const shares = valuation.diluted_shares > 0 ? valuation.diluted_shares : sharesFromMarketCap;
  const fcfMarginPct =
    company.market.fcf_yield_pct && company.market.fcf_yield_pct > 0 && company.profile.market_cap > 0 && baseRevenue > 0
      ? clamp((company.profile.market_cap * (company.market.fcf_yield_pct / 100) / baseRevenue) * 100, 2, 45)
      : clamp(assumption.terminal_margin_pct, 2, 45);
  const terminalGrowthPct = 3;
  const baseDcf = calculateDcfValue({
    baseRevenue,
    revenueCagrPct: assumption.revenue_cagr_pct,
    fcfMarginPct,
    waccPct: assumption.discount_rate_pct,
    terminalGrowthPct,
    netDebt: valuation.net_cash_debt,
    shares
  });
  const intrinsicValue = baseDcf.impliedPrice || assumption.implied_price;
  const impliedReturnPct = currentPrice > 0 ? (intrinsicValue / currentPrice - 1) * 100 : assumption.implied_return_pct;
  const sensitivityGrowths = [2, 2.5, 3, 3.5, 4];
  const sensitivityWaccs = [-1, -0.5, 0, 0.5, 1].map((offset) => Math.max(assumption.discount_rate_pct + offset, 1));
  const sensitivity = sensitivityWaccs.map((waccPct) => ({
    waccPct,
    cells: sensitivityGrowths.map((growth) => ({
      terminalGrowthPct: growth,
      impliedPrice: calculateDcfValue({
        baseRevenue,
        revenueCagrPct: assumption.revenue_cagr_pct,
        fcfMarginPct,
        waccPct,
        terminalGrowthPct: growth,
        netDebt: valuation.net_cash_debt,
        shares
      }).impliedPrice
    }))
  }));

  return {
    caseName,
    currentPrice,
    intrinsicValue,
    impliedReturnPct,
    waccPct: assumption.discount_rate_pct,
    terminalGrowthPct,
    fcfMarginPct,
    revenueCagrPct: assumption.revenue_cagr_pct,
    baseRevenue,
    shares,
    netDebt: valuation.net_cash_debt,
    ...baseDcf,
    sensitivityGrowths,
    sensitivity
  };
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

function compactOverview(description: string) {
  const normalized = description.replace(/\s+/g, " ").trim();
  const firstSentence = normalized.split(/(?<=[.!?])\s+/)[0] || normalized;
  if (firstSentence.length <= 170) return firstSentence;
  return `${firstSentence.slice(0, 167).trim()}...`;
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
  const [adminOpen, setAdminOpen] = useState(false);
  const [adminKey, setAdminKey] = useState("");
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [adminStatus, setAdminStatus] = useState("");
  const [universe, setUniverse] = useState<UniverseRow[]>([]);
  const [watchlistRows, setWatchlistRows] = useState<UniverseRow[]>([]);
  const [trendingRows, setTrendingRows] = useState<TrendingRow[]>([]);
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
    setWatchlistRows([]);
    setTrendingRows([]);
    setCompany(null);
    setSavedIdeas([]);
    setAdminOpen(false);
    setAdminUsers([]);
    setAdminKey("");
    setStatus("Signed out.");
  }

  async function loadAdminUsers() {
    if (!adminKey.trim()) {
      setAdminStatus("Enter your admin key.");
      return;
    }
    setAdminStatus("Loading users...");
    try {
      const users = await api.adminUsers(adminKey.trim());
      setAdminUsers(users);
      setAdminStatus(`${users.length} user${users.length === 1 ? "" : "s"} loaded.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to load users.";
      setAdminUsers([]);
      if (message.includes("Sign in required") || message.includes("Session expired")) {
        setAdminStatus("Your login session expired after the last deploy. Sign in again, then reopen Admin.");
        return;
      }
      if (message.includes("Admin key is not configured")) {
        setAdminStatus("Render does not have VRW_ADMIN_KEY configured yet.");
        return;
      }
      if (message.includes("Invalid admin key")) {
        setAdminStatus("That admin key does not match VRW_ADMIN_KEY in Render.");
        return;
      }
      setAdminStatus(message);
    }
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

  async function loadWatchlist() {
    const rows = await api.watchlist();
    setWatchlistRows(rows);
  }

  async function loadTrending() {
    const rows = await api.trending();
    setTrendingRows(rows);
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
      setWatchlistRows([]);
      setTrendingRows([]);
      setCompany(null);
      setStatus("Session expired. Sign in again.");
    };
    window.addEventListener("vrw-auth-expired", expire);
    return () => window.removeEventListener("vrw-auth-expired", expire);
  }, []);

  useEffect(() => {
    if (!authToken || !authUser) return;
    Promise.all([loadUniverse(), loadSavedIdeas(), loadWatchlist(), loadTrending()])
      .then(() => setStatus("Research workspace ready"))
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
    const rows = [...watchlistRows];
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
      savedCount: rows.length,
      topGainers: [...rows].sort((a, b) => b.daily_change_pct - a.daily_change_pct).slice(0, 3),
      topLosers: [...rows].sort((a, b) => a.daily_change_pct - b.daily_change_pct).slice(0, 3),
      recommendationMix: { buys, holds, sells },
      watchlist: [...rows].sort((a, b) => b.relative_strength_pct - a.relative_strength_pct)
    };
  }, [watchlistRows]);

  const selectedScenario = valuationDraft ? valuationDraft[valuationDraft.selected_case] : null;

  async function refreshData() {
    setIsBusy(true);
    try {
      const result = await api.refresh();
      await loadUniverse();
      await loadWatchlist();
      await loadTrending();
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
      setQuery(record.profile.ticker);
      setSuggestions([]);
      setFocusedSearch(null);
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
      await loadWatchlist();
      await loadTrending();
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
      await loadWatchlist();
      await loadTrending();
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
    setQuery(normalized);
    setSuggestions([]);
    setFocusedSearch(null);
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
    <>
    <div className="app-shell">
      <aside className="coverage-rail">
          <div className="brand-block">
            <div className="brand-mark">VR</div>
            <div>
              <h1>Variant Research</h1>
              <p>General equities workbench</p>
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
          inputLabel="Search stocks"
          buttonLabel="Analyze"
          buttonIconSize={15}
        />

        <SavedIdeasPanel
          ideas={savedIdeas}
          activeTicker={company?.profile.ticker ?? selectedTicker}
          onOpen={(ticker) => void openTicker(ticker)}
          onRemove={(ticker) => void removeCurrentIdea(ticker)}
        />

        <div className="rail-section-heading compact">
          <span>Starter tape</span>
          <strong>{filteredUniverse.length}</strong>
        </div>
        <div className="universe-list" aria-label="Starter stock list">
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
          <button className="signout-button" type="button" onClick={() => setAdminOpen(true)} title="Open admin panel">
            <ShieldCheck size={15} aria-hidden="true" />
            Admin
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

            <MarketDeskOverview desk={marketDesk} trending={trendingRows} onOpen={(ticker) => void openTicker(ticker)} />

            <header className="company-header">
              <div>
                <span className="eyebrow">{company.profile.sector} / {company.profile.industry}</span>
                <h2>{company.profile.name}</h2>
                <p>{compactOverview(company.profile.description)}</p>
                <div className="data-source-chip">
                  <DatabaseZap size={14} aria-hidden="true" />
                  {company.recommendation.source_status}
                </div>
              </div>
              <div className="header-actions">
                <div className="price-tile">
                  <small>{company.profile.ticker}</small>
                  <strong>{hasConcreteSource(company.provenance.quote) ? formatMoney(company.market.price) : "n/a"}</strong>
                  <span className={company.market.daily_change_pct >= 0 ? "positive" : "negative"}>
                    {hasConcreteSource(company.provenance.quote) ? formatPct(company.market.daily_change_pct) : "n/a"}
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

            <TopRecommendationPanel company={company} />

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
              <Metric label="Market Cap" value={hasConcreteSource(company.provenance.market_cap) ? `${formatNumber(company.profile.market_cap, 0)}B` : "n/a"} />
              <Metric label="YTD" value={hasConcreteSource(company.provenance.quote) ? formatPct(company.market.ytd_change_pct) : "n/a"} tone={company.market.ytd_change_pct >= 0 ? "good" : "bad"} />
              <Metric label="Rel. Strength" value={hasConcreteSource(company.provenance.quote) ? formatPct(company.market.relative_strength_pct) : "n/a"} tone={company.market.relative_strength_pct >= 0 ? "good" : "bad"} />
              <Metric label="EV/Sales NTM" value={hasConcreteSource(company.provenance.financials) ? formatMultiple(company.market.ev_sales_ntm) : "n/a"} />
              <Metric label="EV/EBITDA NTM" value={hasConcreteSource(company.provenance.financials) ? formatMultiple(company.market.ev_ebitda_ntm) : "n/a"} />
              <Metric label="FCF Yield" value={hasConcreteSource(company.provenance.financials) ? formatPct(company.market.fcf_yield_pct) : "n/a"} />
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
                  {tab === "DCF Report" && <Calculator size={16} aria-hidden="true" />}
                  {tab === "Thesis" && <DatabaseZap size={16} aria-hidden="true" />}
                  {tab === "Export" && <FileText size={16} aria-hidden="true" />}
                  {tab}
                </button>
              ))}
            </nav>

            {activeTab === "Tear Sheet" && <TearSheet company={company} selectedScenario={selectedScenario} />}
            {activeTab === "Valuation" && (
              <ValuationPanel
                valuation={valuationDraft}
                updateScenario={updateScenario}
                setValuation={setValuationDraft}
                save={saveValuation}
                openReport={() => setActiveTab("DCF Report")}
              />
            )}
            {activeTab === "DCF Report" && <DcfReportPanel company={company} valuation={valuationDraft} />}
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
    {adminOpen && (
      <AdminPanel
        adminKey={adminKey}
        setAdminKey={setAdminKey}
        users={adminUsers}
        status={adminStatus}
        onClose={() => setAdminOpen(false)}
        onLoad={() => void loadAdminUsers()}
      />
    )}
    </>
  );
}

function AdminPanel({
  adminKey,
  setAdminKey,
  users,
  status,
  onClose,
  onLoad
}: {
  adminKey: string;
  setAdminKey: Dispatch<SetStateAction<string>>;
  users: AdminUser[];
  status: string;
  onClose: () => void;
  onLoad: () => void;
}) {
  return (
    <div className="admin-overlay" role="dialog" aria-modal="true" aria-label="Admin user panel">
      <section className="admin-panel">
        <div className="admin-heading">
          <div>
            <span className="eyebrow">Owner controls</span>
            <h2>Admin Users</h2>
            <p>Use your Render-only admin key to view registered accounts. Passwords and tokens are never shown.</p>
          </div>
          <button className="icon-button light" type="button" onClick={onClose} title="Close admin panel">
            <X size={17} aria-hidden="true" />
          </button>
        </div>

        <form
          className="admin-key-row"
          onSubmit={(event) => {
            event.preventDefault();
            onLoad();
          }}
        >
          <label>
            <span>Admin key</span>
            <input
              type="password"
              value={adminKey}
              onChange={(event) => setAdminKey(event.target.value)}
              placeholder="VRW_ADMIN_KEY"
              autoComplete="off"
            />
          </label>
          <button className="primary-button" type="submit">
            <Users size={16} aria-hidden="true" />
            Load users
          </button>
        </form>

        {status && <p className="admin-status">{status}</p>}

        <div className="admin-user-list">
          {users.map((user) => (
            <article key={user.email} className="admin-user-row">
              <div>
                <strong>{user.email}</strong>
                <span>Created {new Date(user.created_at).toLocaleDateString()}</span>
              </div>
              <div>
                <small>Active sessions</small>
                <strong>{user.active_sessions}</strong>
              </div>
              <div>
                <small>Updated</small>
                <span>{new Date(user.updated_at).toLocaleDateString()}</span>
              </div>
            </article>
          ))}
        </div>
      </section>
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
          onChange={(event) => {
            setFocusedSearch(surface);
            setQuery(event.target.value);
          }}
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

function TopRecommendationPanel({ company }: { company: CompanyRecord }) {
  return (
    <section className="top-recommendation-panel" aria-label="Recommendation summary">
      <div className="recommendation-callout">
        <span className="eyebrow">Recommendation</span>
        <div>
          <strong className={company.recommendation.rating.toLowerCase().replace(" ", "-")}>
            {company.recommendation.rating}
          </strong>
          <small>{company.recommendation.confidence} confidence / score {formatNumber(company.recommendation.score, 0)}</small>
        </div>
      </div>
      <div className="recommendation-reasoning">
        <p>{company.recommendation.rationale}</p>
        <div className="driver-strip">
          <div>
            <span>Positive drivers</span>
            <ul>
              {(company.recommendation.positives.length ? company.recommendation.positives : ["Awaiting source data."])
                .slice(0, 3)
                .map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          <div>
            <span>Negative drivers</span>
            <ul>
              {(company.recommendation.negatives.length ? company.recommendation.negatives : ["Awaiting source data."])
                .slice(0, 3)
                .map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketDeskOverview({
  desk,
  trending,
  onOpen
}: {
  desk: {
    averageDaily: number;
    averageYtd: number;
    breadth: number;
    savedCount: number;
    topGainers: UniverseRow[];
    topLosers: UniverseRow[];
    recommendationMix: { buys: number; holds: number; sells: number };
    watchlist: UniverseRow[];
  };
  trending: TrendingRow[];
  onOpen: (ticker: string) => void;
}) {
  const hasSaved = desk.savedCount > 0;
  return (
    <section className="market-desk" aria-label="Market overview">
      <div className="desk-metric">
        <Gauge size={17} aria-hidden="true" />
        <span>Saved watchlist</span>
        <strong>{desk.savedCount}</strong>
      </div>
      <div className="desk-metric">
        <Target size={17} aria-hidden="true" />
        <span>Saved breadth</span>
        <strong>{hasSaved ? formatPct(desk.breadth, 0) : "n/a"}</strong>
      </div>
      <div className="desk-metric">
        <TrendingUp size={17} aria-hidden="true" />
        <span>Saved avg YTD</span>
        <strong className={hasSaved ? signalClass(desk.averageYtd) : ""}>{hasSaved ? formatPct(desk.averageYtd) : "n/a"}</strong>
      </div>
      <div className="desk-metric">
        <Flame size={17} aria-hidden="true" />
        <span>Saved signal mix</span>
        <strong>{hasSaved ? `${desk.recommendationMix.buys}B / ${desk.recommendationMix.holds}H / ${desk.recommendationMix.sells}S` : "n/a"}</strong>
      </div>

      <div className="mover-panel">
        <span>Saved gainers</span>
        {desk.topGainers.length ? (
          desk.topGainers.map((row) => (
            <button key={row.ticker} type="button" onClick={() => onOpen(row.ticker)}>
              <strong>{row.ticker}</strong>
              <em className="positive">{formatPct(row.daily_change_pct)}</em>
            </button>
          ))
        ) : (
          <p>Save stocks to track movers.</p>
        )}
      </div>
      <div className="mover-panel">
        <span>Saved losers</span>
        {desk.topLosers.length ? (
          desk.topLosers.map((row) => (
            <button key={row.ticker} type="button" onClick={() => onOpen(row.ticker)}>
              <strong>{row.ticker}</strong>
              <em className="negative">{formatPct(row.daily_change_pct)}</em>
            </button>
          ))
        ) : (
          <p>Bookmark names first.</p>
        )}
      </div>
      <div className="heatmap-strip" aria-label="Saved watchlist heatmap">
        {desk.watchlist.length ? (
          desk.watchlist.map((row) => (
            <button
              key={row.ticker}
              type="button"
              className={row.relative_strength_pct >= 0 ? "heat-positive" : "heat-negative"}
              onClick={() => onOpen(row.ticker)}
              title={`${row.ticker} relative strength ${formatPct(row.relative_strength_pct)}`}
            >
              {row.ticker}
            </button>
          ))
        ) : (
          <p>No saved watchlist yet. Save a stock to make these dashboard stats personal.</p>
        )}
      </div>
      <div className="trending-tape" aria-label="Trending research tape">
        <div>
          <span>Trending tape</span>
          <small>Ranked by available news count, recent move, and tracked/saved traction.</small>
        </div>
        {trending.map((row) => (
          <button
            key={row.ticker}
            type="button"
            className={row.daily_change_pct >= 0 ? "heat-positive" : "heat-negative"}
            onClick={() => onOpen(row.ticker)}
            title={`${row.name}: ${row.reason}`}
          >
            <strong>{row.ticker}</strong>
            <em>{formatPct(row.daily_change_pct)}</em>
          </button>
        ))}
      </div>
    </section>
  );
}

function DataQualityPanel({ company }: { company: CompanyRecord }) {
  const sourceRows = [
    ["Quote", company.provenance.quote],
    ["Market cap", company.provenance.market_cap],
    ["Financials", company.provenance.financials],
    ["Valuation", company.provenance.valuation],
    ["News", company.provenance.news],
    ["Analyst", company.analyst_snapshot.source],
    ["Thesis", company.provenance.thesis]
  ];

  return (
    <section className="data-quality-panel" aria-label="Data provenance">
      <div className="panel-heading">
        <div>
          <h3>Data Provenance</h3>
          <span>Refreshed {company.provenance.refreshed_date}</span>
        </div>
        <DatabaseZap size={18} aria-hidden="true" />
      </div>
      <div className="source-grid">
        {sourceRows.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      {company.provenance.warnings.length > 0 && (
        <div className="warning-list">
          {company.provenance.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </section>
  );
}

function priceForEvent(company: CompanyRecord, eventDate: string) {
  const target = new Date(`${eventDate}T00:00:00Z`).getTime();
  let best: { date: string; close: number; distance: number } | null = null;
  for (const point of company.price_history) {
    const pointTime = new Date(`${point.date}T00:00:00Z`).getTime();
    const distance = Math.abs(pointTime - target);
    if (distance <= 1000 * 60 * 60 * 24 * 5 && (!best || distance < best.distance)) {
      best = { date: point.date, close: point.close, distance };
    }
  }
  return best;
}

function StockEventPanel({ company }: { company: CompanyRecord }) {
  const chartData = company.price_history.slice(-120);
  const markers = company.event_flags
    .map((event) => ({ event, point: priceForEvent(company, event.date) }))
    .filter((item): item is { event: CompanyRecord["event_flags"][number]; point: { date: string; close: number; distance: number } } => Boolean(item.point))
    .slice(0, 10);
  const visibleEvents = company.event_flags.slice(0, 8);

  return (
    <div className="panel event-chart-panel">
      <div className="panel-heading">
        <div>
          <h3>Stock Chart & Event Flags</h3>
          <span>{visibleEvents.length ? `${visibleEvents.length} recent flags from price, news, filings, and earnings` : "No event flags loaded"}</span>
        </div>
        <LineChartIcon size={18} aria-hidden="true" />
      </div>
      <div className="chart-frame">
        {chartData.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 14, right: 14, left: 0, bottom: 6 }}>
              <CartesianGrid stroke="#e6e1d8" vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={26} />
              <YAxis tickLine={false} axisLine={false} width={44} domain={["auto", "auto"]} />
              <Tooltip />
              <Line type="monotone" dataKey="close" name="Close" stroke="#256f78" strokeWidth={3} dot={false} />
              {markers.map(({ event, point }) => (
                <ReferenceDot
                  key={`${event.category}-${event.title}-${event.date}`}
                  x={point.date}
                  y={point.close}
                  r={5}
                  fill={event.sentiment === "Positive" ? "#247146" : event.sentiment === "Negative" ? "#9c3838" : "#b56b38"}
                  stroke="#fffaf2"
                  strokeWidth={2}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="empty-panel-copy">Price history is unavailable for this ticker.</p>
        )}
      </div>
      <div className="event-flag-list">
        {visibleEvents.map((event) => (
          <a key={`${event.category}-${event.title}-${event.date}`} href={event.url ?? undefined} target="_blank" rel="noreferrer" className="event-flag-row">
            <span className={`event-badge ${event.category.toLowerCase().replace(" ", "-")}`}>{event.category}</span>
            <div>
              <strong>{event.title}</strong>
              <small>{event.date} / {event.source}</small>
              <p>{event.description}</p>
            </div>
            {event.price_change_pct !== null && <em className={signalClass(event.price_change_pct)}>{formatPct(event.price_change_pct)}</em>}
          </a>
        ))}
        {!visibleEvents.length && <p className="empty-panel-copy">Add Alpha Vantage or refresh the ticker to populate events.</p>}
      </div>
    </div>
  );
}

function AnalystSentimentPanel({ company }: { company: CompanyRecord }) {
  const snapshot = company.analyst_snapshot;
  const ratings: Array<[string, number | null]> = [
    ["Strong Buy", snapshot.strong_buy],
    ["Buy", snapshot.buy],
    ["Hold", snapshot.hold],
    ["Sell", snapshot.sell],
    ["Strong Sell", snapshot.strong_sell]
  ];
  const totalRatings = ratings.reduce((sum, [, value]) => sum + (value ?? 0), 0);
  const targetReturn =
    snapshot.target_price && company.market.price ? (snapshot.target_price / company.market.price - 1) * 100 : null;
  const hasAnalystTarget = targetReturn !== null;
  const analystStatus =
    snapshot.source === "Alpha Vantage key missing"
      ? "The backend does not see ALPHAVANTAGE_API_KEY yet. Check Render environment variables, save changes, and redeploy."
      : !hasConcreteSource(snapshot.source)
        ? "Alpha Vantage did not return usable analyst sentiment for this ticker. Do not treat the blank distribution as Hold, Buy, or Sell."
        : hasAnalystTarget
          ? "No full buy/hold/sell distribution is available, so the app is using target price and consensus only."
          : "No usable analyst sentiment was returned for this ticker.";

  return (
    <div className="panel analyst-panel">
      <div className="panel-heading">
        <div>
          <h3>Analyst Sentiment</h3>
          <span>{snapshot.source}</span>
        </div>
        <Target size={18} aria-hidden="true" />
      </div>
      <div className="analyst-summary">
        <div>
          <span>Consensus</span>
          <strong>{snapshot.consensus}</strong>
        </div>
        <div>
          <span>Target Price</span>
          <strong>{snapshot.target_price ? formatMoney(snapshot.target_price) : "n/a"}</strong>
        </div>
        <div>
          <span>Target Return</span>
          <strong className={targetReturn === null ? "" : signalClass(targetReturn)}>{targetReturn === null ? "n/a" : formatPct(targetReturn)}</strong>
        </div>
      </div>
      {totalRatings > 0 && (
        <div className="rating-bars">
          {ratings.map(([label, value]) => {
            const width = totalRatings ? `${Math.max(((value ?? 0) / totalRatings) * 100, value ? 4 : 0)}%` : "0%";
            return (
              <div key={label}>
                <span>{label}</span>
                <div><i style={{ width }} /></div>
                <strong>{value ?? 0}</strong>
              </div>
            );
          })}
        </div>
      )}
      {!totalRatings && <p className="empty-panel-copy">{analystStatus}</p>}
    </div>
  );
}

function TearSheet({ company, selectedScenario }: { company: CompanyRecord; selectedScenario: ScenarioAssumption | null }) {
  const revenueData = company.financials.annual.map((point) => ({
    period: point.period,
    revenue: point.revenue,
    margin: point.ebitda_margin_pct ?? 0
  }));
  const rankedNews = [...company.news].sort((a, b) => newsRank(b) - newsRank(a));
  const relativeStrengthSignal =
    Math.abs(company.market.relative_strength_pct) > 500
      ? `Relative strength is extreme at ${formatPct(company.market.relative_strength_pct)}; validate split or corporate-action adjustments before using it as a signal.`
      : `Relative strength is ${formatPct(company.market.relative_strength_pct)}, which ${company.market.relative_strength_pct >= 0 ? "supports" : "pressures"} the current signal.`;
  const weeklySignals = [
    `${company.profile.ticker} moved ${formatPct(company.market.daily_change_pct)} today and ${formatPct(company.market.ytd_change_pct)} YTD.`,
    relativeStrengthSignal,
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

      <StockEventPanel company={company} />

      <AnalystSentimentPanel company={company} />

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
  save,
  openReport
}: {
  valuation: ScenarioValuation;
  updateScenario: (caseName: ScenarioKey, field: keyof ScenarioAssumption, value: number) => void;
  setValuation: Dispatch<SetStateAction<ScenarioValuation | null>>;
  save: () => void;
  openReport: () => void;
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
          <h3>Scenario Assumptions</h3>
          <div className="button-row">
            <button className="secondary-button" type="button" onClick={openReport}>
              <Calculator size={16} aria-hidden="true" />
              View DCF Report
            </button>
            <button className="secondary-button" type="button" onClick={save}>
              <Save size={16} aria-hidden="true" />
              Save
            </button>
          </div>
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

function DcfReportPanel({ company, valuation }: { company: CompanyRecord; valuation: ScenarioValuation }) {
  const report = buildDcfReport(company, valuation);
  const upsideLabel = report.impliedReturnPct >= 0 ? "Implied Upside" : "Implied Downside";
  const sensitivityBaseGrowth = report.sensitivityGrowths.find((growth) => growth === report.terminalGrowthPct) ?? report.sensitivityGrowths[0];
  const topNews = [...company.news].sort((a, b) => newsRank(b) - newsRank(a)).slice(0, 2);
  const conclusionTone =
    company.recommendation.rating === "Buy"
      ? "The current setup screens positively, but the case still depends on validating the forecast and news drivers."
      : company.recommendation.rating === "Sell"
        ? "The current setup screens negatively, so the main work is checking whether the downside is already priced in."
        : "The current setup is balanced, so the name belongs on the watchlist until the valuation or news flow improves.";

  return (
    <section className="dcf-report-panel" aria-label={`${company.profile.ticker} DCF report`}>
      <header className="dcf-report-header">
        <div>
          <h3>{company.profile.name} ({company.profile.ticker})</h3>
          <p>Equity Research - DCF Valuation Summary | Sector: {company.profile.sector || "n/a"} | {new Date().toLocaleDateString(undefined, { month: "long", year: "numeric" })}</p>
        </div>
        <strong className={`dcf-rating ${company.recommendation.rating.toLowerCase().replace(" ", "-")}`}>
          {company.recommendation.rating}
        </strong>
      </header>

      <div className="dcf-summary-grid">
        <DcfSummaryTile label="Current Price" value={formatMoney(report.currentPrice)} />
        <DcfSummaryTile label="Intrinsic Value" value={formatMoney(report.intrinsicValue)} />
        <DcfSummaryTile label={upsideLabel} value={formatPct(report.impliedReturnPct)} tone={report.impliedReturnPct >= 0 ? "positive" : "negative"} />
        <DcfSummaryTile label="WACC" value={`${formatNumber(report.waccPct, 2)}%`} />
      </div>

      <div className="dcf-report-grid">
        <section>
          <h4>Revenue & FCF Forecast ($B)</h4>
          <div className="table-shell">
            <table className="dcf-table">
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Revenue</th>
                  <th>FCF</th>
                </tr>
              </thead>
              <tbody>
                {report.forecast.map((row) => (
                  <tr key={row.year}>
                    <td>{row.year}</td>
                    <td>{formatNumber(row.revenue, 1)}</td>
                    <td>{formatNumber(row.fcf, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h4>Valuation Bridge ($B, except per-share)</h4>
          <div className="table-shell">
            <table className="dcf-table bridge-table">
              <tbody>
                <tr>
                  <td>Sum of PV of FCF</td>
                  <td>{formatNumber(report.pvFcf, 1)}</td>
                </tr>
                <tr>
                  <td>+ PV of Terminal Value</td>
                  <td>{formatNumber(report.pvTerminalValue, 1)}</td>
                </tr>
                <tr>
                  <td>= Enterprise Value</td>
                  <td>{formatNumber(report.enterpriseValue, 1)}</td>
                </tr>
                <tr>
                  <td>{report.netDebt >= 0 ? "- Net Debt" : "+ Net Cash"}</td>
                  <td>{formatNumber(Math.abs(report.netDebt), 1)}</td>
                </tr>
                <tr>
                  <td>= Equity Value</td>
                  <td>{formatNumber(report.equityValue, 1)}</td>
                </tr>
                <tr>
                  <td>/ Shares Outstanding (B)</td>
                  <td>{formatNumber(report.shares, 2)}</td>
                </tr>
                <tr className="highlight-row">
                  <td>= Implied Share Price</td>
                  <td>{formatMoney(report.intrinsicValue)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="dcf-assumptions">
        <h4>Key Assumptions</h4>
        <div className="assumption-grid">
          <DcfAssumption label="Selected Case" value={report.caseName.toUpperCase()} />
          <DcfAssumption label="Base Revenue" value={formatCompactBillions(report.baseRevenue, 1)} />
          <DcfAssumption label="Revenue CAGR" value={`${formatNumber(report.revenueCagrPct, 1)}%`} />
          <DcfAssumption label="FCF Margin" value={`${formatNumber(report.fcfMarginPct, 1)}%`} />
          <DcfAssumption label="Terminal Growth" value={`${formatNumber(report.terminalGrowthPct, 1)}%`} />
          <DcfAssumption label="Net Debt / (Cash)" value={formatCompactBillions(report.netDebt, 1)} />
        </div>
        <p>
          This report uses the selected valuation case, Yahoo/yfinance quote and profile fields where available, and your editable model assumptions.
        </p>
      </section>

      <section className="dcf-sensitivity">
        <h4>Sensitivity: Implied Share Price ($) - WACC vs. Terminal Growth Rate</h4>
        <div className="table-shell">
          <table className="dcf-table sensitivity-table">
            <thead>
              <tr>
                <th>WACC \ g</th>
                {report.sensitivityGrowths.map((growth) => (
                  <th key={growth}>{formatNumber(growth, 1)}%</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.sensitivity.map((row) => (
                <tr key={row.waccPct}>
                  <th>{formatNumber(row.waccPct, 2)}%</th>
                  {row.cells.map((cell) => (
                    <td
                      key={`${row.waccPct}-${cell.terminalGrowthPct}`}
                      className={row.waccPct === report.waccPct && cell.terminalGrowthPct === sensitivityBaseGrowth ? "highlight-cell" : ""}
                    >
                      {formatNumber(cell.impliedPrice, 2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <small>Base case highlighted: WACC {formatNumber(report.waccPct, 2)}%, terminal growth {formatNumber(report.terminalGrowthPct, 1)}%.</small>
      </section>

      <section className="dcf-conclusion">
        <h4>Conclusion</h4>
        <p>
          Under the selected {report.caseName} case, the model indicates {formatPct(report.impliedReturnPct)} implied return versus the current quote. {conclusionTone}
        </p>
        {topNews.length > 0 && (
          <ul>
            {topNews.map((item) => (
              <li key={`${item.title}-${item.published_at}`}>{item.title}</li>
            ))}
          </ul>
        )}
        <small>
          Disclaimer: This is an independent, educational DCF exercise. Forecasts and assumptions are simplified and should not be treated as investment advice.
        </small>
      </section>
    </section>
  );
}

function DcfSummaryTile({ label, value, tone }: { label: string; value: string; tone?: "positive" | "negative" }) {
  return (
    <div className={`dcf-summary-tile ${tone ?? ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function DcfAssumption({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
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
        <input
          type="number"
          step={prefix ? "0.01" : suffix === "x" ? "0.1" : "0.1"}
          value={Number.isFinite(value) ? Number(value.toFixed(prefix ? 2 : suffix === "x" ? 1 : 1)) : 0}
          onChange={(event) => onChange(Number(event.target.value))}
        />
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
