from __future__ import annotations

from datetime import date

from backend.app.models import (
    CompanyProfile,
    CompanyRecord,
    FinancialPoint,
    FinancialSeries,
    MarketSnapshot,
    NewsItem,
    Recommendation,
    ScenarioAssumption,
    ScenarioValuation,
    Thesis,
)


def build_research_intake_record(ticker: str) -> CompanyRecord:
    """Return an honest placeholder for tickers that lack a connected data source."""

    normalized = ticker.upper().strip()
    today = date.today()
    empty_case = ScenarioAssumption(
        revenue_cagr_pct=0,
        terminal_margin_pct=0,
        exit_multiple=0,
        discount_rate_pct=10,
        implied_price=0,
        implied_return_pct=0,
    )

    return CompanyRecord(
        profile=CompanyProfile(
            ticker=normalized,
            name=f"{normalized} Research Intake",
            sector="Pending source data",
            industry="Pending source data",
            market_cap=0,
            currency="USD",
            description=(
                "This ticker is not in the seeded coverage universe. Connect Bloomberg/news data "
                "or add a sanctioned fixture before generating a real thesis."
            ),
        ),
        market=MarketSnapshot(
            price=0,
            daily_change_pct=0,
            ytd_change_pct=0,
            relative_strength_pct=0,
            ev_sales_ntm=0,
            ev_ebitda_ntm=None,
            pe_ntm=None,
            fcf_yield_pct=None,
        ),
        financials=FinancialSeries(
            annual=[FinancialPoint(period="Pending", revenue=0)],
            quarterly=[FinancialPoint(period="Pending", revenue=0)],
        ),
        thesis=Thesis(
            ticker=normalized,
            stance="Under Review",
            one_liner="No automated thesis yet because financials and news are not connected for this ticker.",
            variant_view=(
                "Use Bloomberg mode or a licensed market/news API to pull financials, valuation, "
                "recent news, and transcripts before assigning a buy/hold/sell recommendation."
            ),
            evidence=["Ticker search captured.", "Awaiting financial data.", "Awaiting recent news context."],
            risks=["Insufficient source data.", "Do not use placeholder output as investment research."],
            watch_items=["Connect data provider", "Refresh financials", "Review recent news", "Write variant view"],
            updated_date=today,
        ),
        valuation=ScenarioValuation(
            ticker=normalized,
            base_year_revenue=0,
            net_cash_debt=0,
            diluted_shares=0,
            bull=empty_case,
            base=empty_case,
            bear=empty_case,
            selected_case="base",
            notes="Valuation is unavailable until financial data is connected.",
            updated_date=today,
        ),
        peers=[],
        news=[
            NewsItem(
                title="No recent news source connected",
                source="Research intake",
                published_at=today,
                sentiment="Neutral",
                summary=(
                    "The app needs Bloomberg News, a licensed news API, RSS pipeline, or manually "
                    "approved source import before it can summarize current developments."
                ),
                impact_reason="Ticker intake is incomplete until a current-news source is connected.",
            )
        ],
        recommendation=Recommendation(
            ticker=normalized,
            rating="Under Review",
            confidence="Low",
            score=0,
            rationale="No recommendation can be generated until financials and recent news are available.",
            positives=[],
            negatives=["No connected financial feed", "No connected news feed"],
            source_status="Needs Bloomberg/news provider",
            updated_date=today,
        ),
    )
