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
  impact_reason: string;
}

export interface PricePoint {
  date: string;
  close: number;
  volume: number | null;
}

export type EventCategory = "Earnings" | "Filing" | "News" | "Price Move" | "Analyst" | "User";

export interface EventFlag {
  date: string;
  category: EventCategory;
  title: string;
  description: string;
  source: string;
  sentiment: Sentiment;
  price_change_pct: number | null;
  url: string | null;
}

export interface AnalystSnapshot {
  source: string;
  target_price: number | null;
  strong_buy: number | null;
  buy: number | null;
  hold: number | null;
  sell: number | null;
  strong_sell: number | null;
  consensus: string;
  as_of: string;
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

export interface DataProvenance {
  quote: string;
  market_cap: string;
  financials: string;
  valuation: string;
  news: string;
  thesis: string;
  recommendation: string;
  warnings: string[];
  refreshed_date: string;
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
  price_history: PricePoint[];
  event_flags: EventFlag[];
  analyst_snapshot: AnalystSnapshot;
  recommendation: Recommendation;
  provenance: DataProvenance;
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

export interface TrendingRow {
  ticker: string;
  name: string;
  price: number;
  daily_change_pct: number;
  news_count: number;
  traction_score: number;
  reason: string;
  source_status: string;
}

export interface SavedIdea {
  ticker: string;
  note: string;
  priority: "High" | "Medium" | "Low";
  created_at: string;
  updated_date: string;
}

export interface SearchSuggestion {
  ticker: string;
  name: string;
  exchange: string;
  quote_type: string;
  sector: string;
  industry: string;
  source: string;
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

export interface AuthUser {
  email: string;
  created_at: string;
}

export interface AdminUser {
  email: string;
  created_at: string;
  updated_at: string;
  active_sessions: number;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface MessageResponse {
  message: string;
}
