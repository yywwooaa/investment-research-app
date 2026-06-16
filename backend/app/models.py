from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Stance = Literal["Buy", "Hold", "Sell", "Under Review"]
Sentiment = Literal["Positive", "Neutral", "Negative"]


class CompanyProfile(BaseModel):
    ticker: str
    name: str
    sector: str
    industry: str
    market_cap: float = Field(description="Market capitalization in billions")
    currency: str
    description: str


class MarketSnapshot(BaseModel):
    price: float
    daily_change_pct: float
    ytd_change_pct: float
    relative_strength_pct: float
    ev_sales_ntm: float
    ev_ebitda_ntm: float | None = None
    pe_ntm: float | None = None
    fcf_yield_pct: float | None = None


class FinancialPoint(BaseModel):
    period: str
    revenue: float
    ebitda: float | None = None
    ebitda_margin_pct: float | None = None
    fcf: float | None = None
    eps: float | None = None


class FinancialSeries(BaseModel):
    annual: list[FinancialPoint]
    quarterly: list[FinancialPoint]


class Catalyst(BaseModel):
    title: str
    timing: str
    impact: Literal["High", "Medium", "Low"]
    status: Literal["Upcoming", "Active", "Resolved", "Monitoring"]


class NewsItem(BaseModel):
    title: str
    source: str
    published_at: date
    sentiment: Sentiment = "Neutral"
    summary: str
    url: str | None = None


class Recommendation(BaseModel):
    ticker: str
    rating: Literal["Buy", "Hold", "Sell", "Under Review"] = "Under Review"
    confidence: Literal["High", "Medium", "Low"] = "Low"
    score: float = Field(ge=0, le=100)
    rationale: str
    positives: list[str] = Field(default_factory=list)
    negatives: list[str] = Field(default_factory=list)
    source_status: str = "Snapshot demo"
    updated_date: date = Field(default_factory=date.today)


class Thesis(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    stance: Stance = "Under Review"
    horizon: str = "6-24 months"
    one_liner: str = ""
    variant_view: str = ""
    evidence: list[str] = Field(default_factory=list)
    catalysts: list[Catalyst] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    updated_date: date = Field(default_factory=date.today)


class ScenarioAssumption(BaseModel):
    revenue_cagr_pct: float
    terminal_margin_pct: float
    exit_multiple: float
    discount_rate_pct: float
    implied_price: float
    implied_return_pct: float


class ScenarioValuation(BaseModel):
    ticker: str
    base_year_revenue: float
    net_cash_debt: float
    diluted_shares: float
    bull: ScenarioAssumption
    base: ScenarioAssumption
    bear: ScenarioAssumption
    selected_case: Literal["bull", "base", "bear"] = "base"
    notes: str = ""
    updated_date: date = Field(default_factory=date.today)


class PeerMetric(BaseModel):
    ticker: str
    name: str
    ev_sales_ntm: float
    ev_ebitda_ntm: float | None = None
    revenue_growth_ntm_pct: float
    ebitda_margin_ntm_pct: float | None = None
    fcf_yield_pct: float | None = None


class CompanyRecord(BaseModel):
    profile: CompanyProfile
    market: MarketSnapshot
    financials: FinancialSeries
    thesis: Thesis
    valuation: ScenarioValuation
    peers: list[PeerMetric]
    news: list[NewsItem] = Field(default_factory=list)
    recommendation: Recommendation


class UniverseRow(BaseModel):
    ticker: str
    name: str
    sector: str
    industry: str
    price: float
    daily_change_pct: float
    ytd_change_pct: float
    relative_strength_pct: float
    ev_sales_ntm: float
    ev_ebitda_ntm: float | None = None
    pe_ntm: float | None = None
    fcf_yield_pct: float | None = None
    stance: Stance
    recommendation: Literal["Buy", "Hold", "Sell", "Under Review"]
    confidence: Literal["High", "Medium", "Low"]
    source_status: str
    horizon: str
    catalyst_count: int
    news_count: int
    thesis_updated: date


class RefreshResult(BaseModel):
    source: Literal["snapshot", "bloomberg", "yahoo"]
    refreshed: bool
    message: str
    tickers: list[str]


class MarkdownExport(BaseModel):
    ticker: str
    filename: str
    markdown: str
