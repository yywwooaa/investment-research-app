from __future__ import annotations

import json
from pathlib import Path

from backend.app.models import (
    Catalyst,
    CompanyProfile,
    CompanyRecord,
    FinancialPoint,
    FinancialSeries,
    MarketSnapshot,
    NewsItem,
    PeerMetric,
    Recommendation,
    RefreshResult,
    ScenarioAssumption,
    ScenarioValuation,
    Thesis,
)
from backend.app.providers.base import DataProvider


class SnapshotProvider(DataProvider):
    """Loads public-safe demo records from fixture JSON."""

    def __init__(self, fixture_path: Path):
        self.fixture_path = fixture_path
        self._records: dict[str, CompanyRecord] | None = None

    def _load(self) -> dict[str, CompanyRecord]:
        if self._records is None:
            with self.fixture_path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            records = [self._build_record(item, raw["companies"]) for item in raw["companies"]]
            self._records = {record.profile.ticker.upper(): record for record in records}
        return self._records

    def _build_record(self, item: dict, all_items: list[dict]) -> CompanyRecord:
        if "profile" in item:
            return CompanyRecord.model_validate(item)

        ticker = item["ticker"].upper()
        market_cap = float(item["market_cap"])
        price = float(item["price"])
        revenue = [float(value) for value in item["annual_revenue"]]
        margins = [float(value) for value in item["annual_margin_pct"]]
        years = item.get("annual_years", ["2023A", "2024A", "2025E", "2026E"])
        annual = [
            FinancialPoint(
                period=year,
                revenue=rev,
                ebitda=rev * margin / 100,
                ebitda_margin_pct=margin,
                fcf=rev * (margin - 4) / 100,
                eps=item["eps"] * (0.78 + index * 0.08),
            )
            for index, (year, rev, margin) in enumerate(zip(years, revenue, margins))
        ]
        quarterly = [
            FinancialPoint(
                period=f"Q{index + 1} 2026E",
                revenue=revenue[-1] / 4 * (0.94 + index * 0.04),
                ebitda=revenue[-1] / 4 * margins[-1] / 100 * (0.94 + index * 0.04),
                ebitda_margin_pct=margins[-1],
                fcf=revenue[-1] / 4 * max(margins[-1] - 5, 4) / 100,
                eps=item["eps"] / 4 * (0.92 + index * 0.05),
            )
            for index in range(4)
        ]

        base_revenue = revenue[-1]
        selected = float(item["price_target"])
        valuation = ScenarioValuation(
            ticker=ticker,
            base_year_revenue=base_revenue,
            net_cash_debt=float(item.get("net_cash_debt", 0)),
            diluted_shares=max(market_cap / price, 0.1),
            bull=ScenarioAssumption(
                revenue_cagr_pct=item["growth_ntm_pct"] + 8,
                terminal_margin_pct=margins[-1] + 4,
                exit_multiple=item["ev_sales_ntm"] + 3,
                discount_rate_pct=9.5,
                implied_price=selected * 1.22,
                implied_return_pct=(selected * 1.22 / price - 1) * 100,
            ),
            base=ScenarioAssumption(
                revenue_cagr_pct=item["growth_ntm_pct"] + 2,
                terminal_margin_pct=margins[-1],
                exit_multiple=item["ev_sales_ntm"],
                discount_rate_pct=10.5,
                implied_price=selected,
                implied_return_pct=(selected / price - 1) * 100,
            ),
            bear=ScenarioAssumption(
                revenue_cagr_pct=max(item["growth_ntm_pct"] - 7, -4),
                terminal_margin_pct=max(margins[-1] - 6, 5),
                exit_multiple=max(item["ev_sales_ntm"] - 3, 1),
                discount_rate_pct=11.5,
                implied_price=selected * 0.72,
                implied_return_pct=(selected * 0.72 / price - 1) * 100,
            ),
            notes=item["valuation_notes"],
            updated_date=item["updated_date"],
        )

        peer_lookup = {peer["ticker"].upper(): peer for peer in all_items}
        peers = [
            PeerMetric(
                ticker=peer_ticker,
                name=peer_lookup[peer_ticker]["name"],
                ev_sales_ntm=peer_lookup[peer_ticker]["ev_sales_ntm"],
                ev_ebitda_ntm=peer_lookup[peer_ticker].get("ev_ebitda_ntm"),
                revenue_growth_ntm_pct=peer_lookup[peer_ticker]["growth_ntm_pct"],
                ebitda_margin_ntm_pct=peer_lookup[peer_ticker]["annual_margin_pct"][-1],
                fcf_yield_pct=peer_lookup[peer_ticker].get("fcf_yield_pct"),
            )
            for peer_ticker in item["peers"]
            if peer_ticker in peer_lookup
        ]
        recommendation = self._build_recommendation(item, valuation.base.implied_return_pct)
        news = self._build_news_items(item)

        return CompanyRecord(
            profile=CompanyProfile(
                ticker=ticker,
                name=item["name"],
                sector=item["sector"],
                industry=item["industry"],
                market_cap=market_cap,
                currency=item.get("currency", "USD"),
                description=item["description"],
            ),
            market=MarketSnapshot(
                price=price,
                daily_change_pct=item["daily_change_pct"],
                ytd_change_pct=item["ytd_change_pct"],
                relative_strength_pct=item["relative_strength_pct"],
                ev_sales_ntm=item["ev_sales_ntm"],
                ev_ebitda_ntm=item.get("ev_ebitda_ntm"),
                pe_ntm=item.get("pe_ntm"),
                fcf_yield_pct=item.get("fcf_yield_pct"),
            ),
            financials=FinancialSeries(annual=annual, quarterly=quarterly),
            thesis=Thesis(
                ticker=ticker,
                stance=item["stance"],
                horizon=item.get("horizon", "6-24 months"),
                one_liner=item["one_liner"],
                variant_view=item["variant_view"],
                evidence=item["evidence"],
                catalysts=[Catalyst.model_validate(catalyst) for catalyst in item["catalysts"]],
                risks=item["risks"],
                watch_items=item["watch_items"],
                updated_date=item["updated_date"],
            ),
            valuation=valuation,
            peers=peers,
            news=news,
            recommendation=recommendation,
        )

    def _build_recommendation(self, item: dict, implied_return_pct: float) -> Recommendation:
        rating = item.get("recommendation", item["stance"])
        if rating == "Watch":
            rating = "Hold"
        if rating == "Avoid":
            rating = "Sell"
        confidence = item.get("confidence")
        if confidence is None:
            confidence = "High" if abs(implied_return_pct) >= 20 else "Medium" if abs(implied_return_pct) >= 10 else "Low"
        score = item.get("score")
        if score is None:
            score = min(100, max(0, 50 + implied_return_pct * 1.2 + item["relative_strength_pct"] * 0.35))
        return Recommendation(
            ticker=item["ticker"].upper(),
            rating=rating,
            confidence=confidence,
            score=round(score, 1),
            rationale=item.get(
                "recommendation_rationale",
                f"{rating} based on scenario upside, relative strength, margin trajectory, and the current catalyst/risk balance.",
            ),
            positives=item.get("positives", item["evidence"][:3]),
            negatives=item.get("negatives", item["risks"][:3]),
            source_status=item.get("source_status", "Snapshot demo: synthetic financials and sample news, not Bloomberg"),
            updated_date=item["updated_date"],
        )

    def _build_news_items(self, item: dict) -> list[NewsItem]:
        raw_news = item.get("news")
        if raw_news:
            return [NewsItem.model_validate(news_item) for news_item in raw_news]

        return [
            NewsItem(
                title=f"{item['ticker']} AI infrastructure demand monitor",
                source="Demo research note",
                published_at=item["updated_date"],
                sentiment="Positive" if item["stance"] == "Buy" else "Neutral",
                summary=item["one_liner"],
            ),
            NewsItem(
                title=f"{item['ticker']} valuation and risk review",
                source="Demo research note",
                published_at=item["updated_date"],
                sentiment="Neutral",
                summary=item["valuation_notes"],
            ),
        ]

    def list_companies(self) -> list[CompanyRecord]:
        return list(self._load().values())

    def get_company(self, ticker: str) -> CompanyRecord:
        key = ticker.upper()
        try:
            return self._load()[key]
        except KeyError as exc:
            raise KeyError(f"Unknown ticker: {ticker}") from exc

    def refresh(self) -> RefreshResult:
        self._records = None
        tickers = [record.profile.ticker for record in self.list_companies()]
        return RefreshResult(
            source="snapshot",
            refreshed=True,
            message="Loaded public-safe fixture data. No Bloomberg session was used.",
            tickers=tickers,
        )
