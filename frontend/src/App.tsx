import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import {
  BarChart3,
  Clipboard,
  DatabaseZap,
  FileText,
  LineChart as LineChartIcon,
  Newspaper,
  RefreshCw,
  Save,
  Search,
  Sparkles,
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
import { api } from "./api";
import type {
  CompanyRecord,
  MarkdownExport,
  ScenarioAssumption,
  ScenarioKey,
  ScenarioValuation,
  Stance,
  Thesis,
  UniverseRow
} from "./types";

const tabs = ["Tear Sheet", "Valuation", "Thesis", "Export"] as const;
type Tab = (typeof tabs)[number];

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

export default function App() {
  const [universe, setUniverse] = useState<UniverseRow[]>([]);
  const [selectedTicker, setSelectedTicker] = useState("NVDA");
  const [company, setCompany] = useState<CompanyRecord | null>(null);
  const [thesisDraft, setThesisDraft] = useState<Thesis | null>(null);
  const [valuationDraft, setValuationDraft] = useState<ScenarioValuation | null>(null);
  const [exportDraft, setExportDraft] = useState<MarkdownExport | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Tear Sheet");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("Loading research workspace...");
  const [isBusy, setIsBusy] = useState(false);

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
    loadUniverse()
      .then(() => setStatus("Snapshot universe ready"))
      .catch((error) => setStatus(error instanceof Error ? error.message : "Unable to load universe"));
  }, []);

  useEffect(() => {
    if (universe.length === 0 || universe.some((row) => row.ticker === selectedTicker)) {
      void loadCompany(selectedTicker);
    }
  }, [selectedTicker, universe]);

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
    const ticker = query.trim().toUpperCase();
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

        <form
          className="search-box"
          onSubmit={(event) => {
            event.preventDefault();
            void analyzeTicker();
          }}
        >
          <Search size={16} aria-hidden="true" />
          <input
            aria-label="Search universe"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search or type ticker"
          />
          <button type="submit" disabled={isBusy} title="Analyze typed ticker">
            <Sparkles size={15} aria-hidden="true" />
            Analyze
          </button>
        </form>

        <div className="universe-list" aria-label="Coverage universe">
          {filteredUniverse.map((row) => (
            <button
              key={row.ticker}
              className={`universe-row ${row.ticker === selectedTicker ? "selected" : ""}`}
              onClick={() => setSelectedTicker(row.ticker)}
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
        </div>
      </aside>

      <main className="workbench">
        {company && thesisDraft && valuationDraft ? (
          <>
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
                <button className="primary-button" type="button" onClick={exportSubstack} disabled={isBusy}>
                  <FileText size={17} aria-hidden="true" />
                  Export
                </button>
              </div>
            </header>

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

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className={`metric-card ${tone ?? ""}`}>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function TearSheet({ company, selectedScenario }: { company: CompanyRecord; selectedScenario: ScenarioAssumption | null }) {
  const revenueData = company.financials.annual.map((point) => ({
    period: point.period,
    revenue: point.revenue,
    margin: point.ebitda_margin_pct ?? 0
  }));

  return (
    <section className="content-grid two-column">
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
          {company.news.map((item) => (
            <article key={`${item.title}-${item.published_at}`} className="news-row">
              <div>
                <strong>{item.title}</strong>
                <span>{item.source} / {item.published_at}</span>
              </div>
              <span className={`sentiment ${item.sentiment.toLowerCase()}`}>{item.sentiment}</span>
              <p>{item.summary}</p>
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
