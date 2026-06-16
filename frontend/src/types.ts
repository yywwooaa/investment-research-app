export type Stance = "Buy" | "Hold" | "Sell" | "Under Review";
export type Impact = "High" | "Medium" | "Low";
export type CatalystStatus = "Upcoming" | "Active" | "Resolved" | "Monitoring";
export type ScenarioKey = "bull" | "base" | "bear";
export type Sentiment = "Positive" | "Neutral" | "Negative";
export type Confidence = "High" | "Medium" | "Low";

export interface CompanyProfile {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  market_cap: number;
  currency: string;
  description: string;
}

export interface MarketSnapshot {
  price: number;
  daily_change_pct: number;
  ytd_change_pct: number;
  relative_strength_pct: number;
  ev_sales_ntm: number;
  ev_ebitda_ntm: number | null;
  pe_ntm: number | null;
  fcf_yield_pct: number | null;
}

export interface FinancialPoint {
  period: string;
  revenue: number;
  ebitda: number | null;
  ebitda_margin_pct: number | null;
  fcf: number | null;
  eps: number | null;
}

export interface FinancialSeries {
  annual: FinancialPoint[];
  quarterly: FinancialPoint[];
}

export interface Catalyst {
  title: string;
  timing: string;
  impact: Impact;
  status: CatalystStatus;
}

export interface NewsItem {
  title: string;
  source: string;
  published_at: string;
  sentiment: Sentiment;
  summary: string;
  url: string | null;
}

export interface Recommendation {
  ticker: string;
  rating: Stance;
  confidence: Confidence;
  score: number;
  rationale: string;
  positives: string[];
  negatives: string[];
  source_status: string;
  updated_date: string;
}

export interface Thesis {
  ticker: string;
  stance: Stance;
  horizon: string;
  one_liner: string;
  variant_view: string;
  evidence: string[];
  catalysts: Catalyst[];
  risks: string[];
  watch_items: string[];
  updated_date: string;
}

export interface ScenarioAssumption {
  revenue_cagr_pct: number;
  terminal_margin_pct: number;
  exit_multiple: number;
  discount_rate_pct: number;
  implied_price: number;
  implied_return_pct: number;
}

export interface ScenarioValuation {
  ticker: string;
  base_year_revenue: number;
  net_cash_debt: number;
  diluted_shares: number;
  bull: ScenarioAssumption;
  base: ScenarioAssumption;
  bear: ScenarioAssumption;
  selected_case: ScenarioKey;
  notes: string;
  updated_date: string;
}

export interface PeerMetric {
  ticker: string;
  name: string;
  ev_sales_ntm: number;
  ev_ebitda_ntm: number | null;
  revenue_growth_ntm_pct: number;
  ebitda_margin_ntm_pct: number | null;
  fcf_yield_pct: number | null;
}

export interface CompanyRecord {
  profile: CompanyProfile;
  market: MarketSnapshot;
  financials: FinancialSeries;
  thesis: Thesis;
  valuation: ScenarioValuation;
  peers: PeerMetric[];
  news: NewsItem[];
  recommendation: Recommendation;
}

export interface UniverseRow {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  price: number;
  daily_change_pct: number;
  ytd_change_pct: number;
  relative_strength_pct: number;
  ev_sales_ntm: number;
  ev_ebitda_ntm: number | null;
  pe_ntm: number | null;
  fcf_yield_pct: number | null;
  stance: Stance;
  recommendation: Stance;
  confidence: Confidence;
  source_status: string;
  horizon: string;
  catalyst_count: number;
  news_count: number;
  thesis_updated: string;
}

export interface RefreshResult {
  source: "snapshot" | "bloomberg" | "yahoo";
  refreshed: boolean;
  message: string;
  tickers: string[];
}

export interface MarkdownExport {
  ticker: string;
  filename: string;
  markdown: string;
}
