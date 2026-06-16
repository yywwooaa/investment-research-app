from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from backend.app.models import (
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
    Sentiment,
    Thesis,
)
from backend.app.providers.base import DataProvider
from backend.app.providers.snapshot import SnapshotProvider


class YahooFinanceProvider(DataProvider):
    """Free/public-data provider backed by yfinance.

    yfinance is useful for a personal research prototype, but it is not an
    official Yahoo product and should not be positioned as institutional-grade
    market data.
    """

    def __init__(self, fallback: SnapshotProvider):
        self.fallback = fallback
        self._records: dict[str, CompanyRecord] | None = None

    def list_companies(self) -> list[CompanyRecord]:
        if self._records is None:
            self.refresh()
        return list((self._records or {}).values())

    def get_company(self, ticker: str) -> CompanyRecord:
        key = ticker.upper().strip()
        if self._records and key in self._records:
            return self._records[key]
        try:
            base = self.fallback.get_company(key)
        except KeyError:
            base = None
        return self._fetch_company(key, base)

    def refresh(self) -> RefreshResult:
        records: dict[str, CompanyRecord] = {}
        errors: list[str] = []
        for base in self.fallback.list_companies():
            ticker = base.profile.ticker
            try:
                records[ticker] = self._fetch_company(ticker, base)
            except Exception as exc:
                errors.append(f"{ticker}: {exc}")
                records[ticker] = base.model_copy(
                    update={
                        "recommendation": base.recommendation.model_copy(
                            update={"source_status": "Snapshot fallback: Yahoo Finance refresh failed"}
                        )
                    }
                )
        self._records = records
        message = "Yahoo Finance refresh completed for seeded universe."
        if errors:
            message += f" Snapshot fallback used for {len(errors)} ticker(s)."
        return RefreshResult(
            source="yahoo",
            refreshed=not errors,
            message=message,
            tickers=list(records.keys()),
        )

    def _fetch_company(self, ticker: str, base: CompanyRecord | None) -> CompanyRecord:
        import yfinance as yf

        yf_ticker = yf.Ticker(ticker)
        info = self._safe_info(yf_ticker)
        history = self._safe_history(yf_ticker)

        if not info and history is None and base is None:
            raise KeyError(f"Yahoo Finance could not resolve ticker: {ticker}")

        profile = self._build_profile(ticker, info, base)
        market = self._build_market(info, history, base)
        financials = self._build_financials(info, base)
        news = self._build_news(yf_ticker, ticker, profile.name)
        peers = base.peers if base else []
        valuation = self._build_valuation(ticker, market, info, financials, base)
        thesis = self._build_thesis(ticker, profile, market, valuation, news, base)
        recommendation = self._build_recommendation(ticker, market, valuation, news, thesis)

        return CompanyRecord(
            profile=profile,
            market=market,
            financials=financials,
            thesis=thesis.model_copy(update={"stance": recommendation.rating}),
            valuation=valuation,
            peers=peers,
            news=news,
            recommendation=recommendation,
        )

    @staticmethod
    def _safe_info(yf_ticker: Any) -> dict[str, Any]:
        try:
            return dict(yf_ticker.info or {})
        except Exception:
            return {}

    @staticmethod
    def _safe_history(yf_ticker: Any):
        try:
            history = yf_ticker.history(period="1y", interval="1d", auto_adjust=False)
            return history if history is not None and not history.empty else None
        except Exception:
            return None

    @staticmethod
    def _num(value: Any, fallback: float | None = None) -> float | None:
        try:
            if value is None:
                return fallback
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _reasonable(value: float | None, fallback: float | None, lower: float = 0, upper: float = 200) -> float | None:
        if value is None or value < lower or value > upper:
            return fallback
        return value

    def _build_profile(self, ticker: str, info: dict[str, Any], base: CompanyRecord | None) -> CompanyProfile:
        market_cap = self._num(info.get("marketCap"))
        return CompanyProfile(
            ticker=ticker,
            name=info.get("longName") or info.get("shortName") or (base.profile.name if base else ticker),
            sector=info.get("sector") or (base.profile.sector if base else "Unknown"),
            industry=info.get("industry") or (base.profile.industry if base else "Unknown"),
            market_cap=(market_cap / 1_000_000_000) if market_cap else (base.profile.market_cap if base else 0),
            currency=info.get("financialCurrency") or info.get("currency") or (base.profile.currency if base else "USD"),
            description=info.get("longBusinessSummary") or (base.profile.description if base else "Yahoo Finance profile loaded."),
        )

    def _build_market(self, info: dict[str, Any], history: Any, base: CompanyRecord | None) -> MarketSnapshot:
        price = self._num(info.get("regularMarketPrice"), None)
        previous_close = self._num(info.get("regularMarketPreviousClose"), None)
        if price is None and history is not None:
            price = self._num(history["Close"].iloc[-1], None)
        if previous_close is None and history is not None and len(history) > 1:
            previous_close = self._num(history["Close"].iloc[-2], None)
        if price is None:
            price = base.market.price if base else 0

        daily_change = ((price / previous_close - 1) * 100) if price and previous_close else 0
        ytd_change = base.market.ytd_change_pct if base else 0
        relative_strength = base.market.relative_strength_pct if base else 0
        if history is not None and not history.empty:
            year_start_rows = history[history.index >= f"{date.today().year}-01-01"]
            if not year_start_rows.empty:
                start = self._num(year_start_rows["Close"].iloc[0], None)
                ytd_change = ((price / start - 1) * 100) if price and start else ytd_change
            one_year_start = self._num(history["Close"].iloc[0], None)
            relative_strength = ((price / one_year_start - 1) * 100) if price and one_year_start else relative_strength

        market_cap = self._num(info.get("marketCap"), None)
        enterprise_value = self._num(info.get("enterpriseValue"), None)
        revenue = self._num(info.get("totalRevenue"), None)
        ebitda = self._num(info.get("ebitda"), None)
        ev_sales_raw = enterprise_value / revenue if enterprise_value and revenue else None
        ev_ebitda_raw = enterprise_value / ebitda if enterprise_value and ebitda else None
        ev_sales = self._reasonable(ev_sales_raw, base.market.ev_sales_ntm if base else 0, upper=80)
        ev_ebitda = self._reasonable(ev_ebitda_raw, base.market.ev_ebitda_ntm if base else None, upper=150)
        pe = self._num(info.get("forwardPE"), base.market.pe_ntm if base else None)
        fcf_yield = None
        free_cashflow = self._num(info.get("freeCashflow"), None)
        if free_cashflow and market_cap:
            fcf_yield = free_cashflow / market_cap * 100
        elif base:
            fcf_yield = base.market.fcf_yield_pct
        fcf_yield = self._reasonable(fcf_yield, base.market.fcf_yield_pct if base else None, lower=-25, upper=25)

        return MarketSnapshot(
            price=price,
            daily_change_pct=daily_change,
            ytd_change_pct=ytd_change,
            relative_strength_pct=relative_strength,
            ev_sales_ntm=ev_sales,
            ev_ebitda_ntm=ev_ebitda,
            pe_ntm=pe,
            fcf_yield_pct=fcf_yield,
        )

    def _build_financials(self, info: dict[str, Any], base: CompanyRecord | None) -> FinancialSeries:
        if base:
            latest_revenue = self._num(info.get("totalRevenue"), None)
            latest_ebitda = self._num(info.get("ebitda"), None)
            latest_fcf = self._num(info.get("freeCashflow"), None)
            if latest_revenue:
                annual = list(base.financials.annual)
                annual[-1] = FinancialPoint(
                    period="Yahoo TTM",
                    revenue=latest_revenue / 1_000_000_000,
                    ebitda=(latest_ebitda / 1_000_000_000) if latest_ebitda else annual[-1].ebitda,
                    ebitda_margin_pct=(latest_ebitda / latest_revenue * 100) if latest_ebitda else annual[-1].ebitda_margin_pct,
                    fcf=(latest_fcf / 1_000_000_000) if latest_fcf else annual[-1].fcf,
                    eps=self._num(info.get("trailingEps"), annual[-1].eps),
                )
                return FinancialSeries(annual=annual, quarterly=base.financials.quarterly)
            return base.financials

        revenue = self._num(info.get("totalRevenue"), 0) or 0
        ebitda = self._num(info.get("ebitda"), None)
        fcf = self._num(info.get("freeCashflow"), None)
        margin = (ebitda / revenue * 100) if ebitda and revenue else None
        point = FinancialPoint(
            period="Yahoo TTM",
            revenue=revenue / 1_000_000_000,
            ebitda=(ebitda / 1_000_000_000) if ebitda else None,
            ebitda_margin_pct=margin,
            fcf=(fcf / 1_000_000_000) if fcf else None,
            eps=self._num(info.get("trailingEps"), None),
        )
        return FinancialSeries(annual=[point], quarterly=[point])

    def _build_news(self, yf_ticker: Any, ticker: str, company_name: str) -> list[NewsItem]:
        try:
            raw_news = list(getattr(yf_ticker, "news", []) or [])
        except Exception:
            raw_news = []
        news_items: list[NewsItem] = []
        for item in raw_news[:10]:
            content = item.get("content", item) if isinstance(item, dict) else {}
            title = content.get("title") or item.get("title") if isinstance(item, dict) else None
            provider = content.get("provider", {}) if isinstance(content.get("provider"), dict) else {}
            source = provider.get("displayName") or item.get("publisher", "Yahoo Finance") if isinstance(item, dict) else "Yahoo Finance"
            summary = content.get("summary") or content.get("description") or title or f"Recent Yahoo Finance item for {ticker}."
            if not self._is_relevant_news(ticker, company_name, title or "", summary or ""):
                continue
            published_raw = content.get("pubDate") or item.get("providerPublishTime") if isinstance(item, dict) else None
            published = self._parse_news_date(published_raw)
            if title:
                news_items.append(
                    NewsItem(
                        title=title,
                        source=source,
                        published_at=published,
                        sentiment=self._infer_news_sentiment(title, summary),
                        summary=summary,
                        url=content.get("clickThroughUrl", {}).get("url") if isinstance(content.get("clickThroughUrl"), dict) else item.get("link"),
                        impact_reason=self._news_impact_reason(title, summary),
                    )
                )
        if news_items:
            return news_items
        return [
            NewsItem(
                title=f"No ticker-specific Yahoo Finance news returned for {ticker}",
                source="Yahoo Finance",
                published_at=date.today(),
                sentiment="Neutral",
                summary="Market data loaded, but Yahoo Finance did not return clearly ticker-specific recent news for this request.",
                impact_reason="Treat this as a data-coverage warning, not a company-specific signal.",
            )
        ]

    @staticmethod
    def _is_relevant_news(ticker: str, company_name: str, title: str, summary: str) -> bool:
        text = f"{title} {summary}".lower()
        company_tokens = [
            token.strip(".,&()").lower()
            for token in company_name.split()
            if len(token.strip(".,&()")) >= 4
        ]
        company_tokens = [token for token in company_tokens if token not in {"inc", "corp", "corporation", "company", "limited", "holdings"}]
        return ticker.lower() in text or any(token in text for token in company_tokens[:3])

    @staticmethod
    def _parse_news_date(value: Any) -> date:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).date()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                return date.today()
        return date.today()

    @staticmethod
    def _infer_news_sentiment(title: str, summary: str) -> Sentiment:
        text = f"{title} {summary}".lower()
        positive_terms = {"beat", "beats", "raises", "raised", "upgrade", "upgraded", "surge", "growth", "record", "wins"}
        negative_terms = {"miss", "misses", "cuts", "cut", "downgrade", "downgraded", "probe", "lawsuit", "slump", "falls"}
        if any(term in text for term in positive_terms):
            return "Positive"
        if any(term in text for term in negative_terms):
            return "Negative"
        return "Neutral"

    @staticmethod
    def _news_impact_reason(title: str, summary: str) -> str:
        text = f"{title} {summary}".lower()
        if any(term in text for term in {"earnings", "revenue", "margin", "guidance", "forecast"}):
            return "Likely relevant to near-term estimates, revisions, or margin assumptions."
        if any(term in text for term in {"ai", "chip", "datacenter", "data center", "cloud", "semiconductor"}):
            return "Potential read-through for AI infrastructure demand and competitive positioning."
        if any(term in text for term in {"deal", "partnership", "customer", "contract", "order"}):
            return "Could affect revenue visibility, customer adoption, or backlog confidence."
        if any(term in text for term in {"regulation", "export", "china", "antitrust", "lawsuit", "probe"}):
            return "Could change regulatory, geopolitical, or legal risk in the thesis."
        if any(term in text for term in {"upgrade", "downgrade", "target", "analyst"}):
            return "May explain sentiment or multiple movement, but validate against fundamentals."
        return "Worth scanning for thesis impact; no obvious model-driver keyword detected."

    def _build_valuation(
        self,
        ticker: str,
        market: MarketSnapshot,
        info: dict[str, Any],
        financials: FinancialSeries,
        base: CompanyRecord | None,
    ) -> ScenarioValuation:
        if base:
            base_case = base.valuation
        else:
            base_case = ScenarioValuation(
                ticker=ticker,
                base_year_revenue=financials.annual[-1].revenue,
                net_cash_debt=0,
                diluted_shares=0,
                bull=ScenarioAssumption(
                    revenue_cagr_pct=12,
                    terminal_margin_pct=20,
                    exit_multiple=max(market.ev_sales_ntm + 2, 1),
                    discount_rate_pct=10,
                    implied_price=market.price * 1.25,
                    implied_return_pct=25,
                ),
                base=ScenarioAssumption(
                    revenue_cagr_pct=6,
                    terminal_margin_pct=16,
                    exit_multiple=max(market.ev_sales_ntm, 1),
                    discount_rate_pct=10.5,
                    implied_price=market.price,
                    implied_return_pct=0,
                ),
                bear=ScenarioAssumption(
                    revenue_cagr_pct=0,
                    terminal_margin_pct=10,
                    exit_multiple=max(market.ev_sales_ntm - 2, 1),
                    discount_rate_pct=11.5,
                    implied_price=market.price * 0.8,
                    implied_return_pct=-20,
                ),
                notes="Yahoo Finance live-data scaffold. Refine assumptions manually before publishing.",
            )
        target_mean = self._num(info.get("targetMeanPrice"), None)
        if target_mean and market.price:
            base_return = (target_mean / market.price - 1) * 100
            return base_case.model_copy(
                update={
                    "base": base_case.base.model_copy(update={"implied_price": target_mean, "implied_return_pct": base_return}),
                    "bull": base_case.bull.model_copy(update={"implied_price": target_mean * 1.15, "implied_return_pct": (target_mean * 1.15 / market.price - 1) * 100}),
                    "bear": base_case.bear.model_copy(update={"implied_price": target_mean * 0.8, "implied_return_pct": (target_mean * 0.8 / market.price - 1) * 100}),
                    "notes": "Yahoo Finance source: target mean price and live market/fundamental fields where available.",
                    "updated_date": date.today(),
                }
            )
        return base_case.model_copy(update={"ticker": ticker, "updated_date": date.today()})

    def _build_thesis(
        self,
        ticker: str,
        profile: CompanyProfile,
        market: MarketSnapshot,
        valuation: ScenarioValuation,
        news: list[NewsItem],
        base: CompanyRecord | None,
    ) -> Thesis:
        if base:
            thesis = base.thesis
        else:
            thesis = Thesis(
                ticker=ticker,
                stance="Under Review",
                one_liner=f"{profile.name} is loaded from Yahoo Finance for initial research review.",
                variant_view="Build the differentiated view after reviewing financials, valuation, news, and filings.",
                evidence=[],
                risks=[],
                watch_items=["Review Yahoo Finance news", "Check SEC filings", "Build peer set", "Refine valuation cases"],
            )
        return thesis.model_copy(
            update={
                "ticker": ticker,
                "updated_date": date.today(),
                "evidence": thesis.evidence
                or [
                    f"YTD performance: {market.ytd_change_pct:.1f}%.",
                    f"EV/Sales: {market.ev_sales_ntm:.1f}x.",
                    f"Recent news items loaded: {len(news)}.",
                ],
            }
        )

    def _build_recommendation(
        self,
        ticker: str,
        market: MarketSnapshot,
        valuation: ScenarioValuation,
        news: list[NewsItem],
        thesis: Thesis,
    ) -> Recommendation:
        implied_return = valuation.base.implied_return_pct
        score = min(100, max(0, 50 + implied_return * 1.1 + market.relative_strength_pct * 0.2))
        if implied_return >= 15:
            rating = "Buy"
        elif implied_return <= -10:
            rating = "Sell"
        else:
            rating = "Hold"
        confidence = "Medium" if abs(implied_return) >= 10 and market.price > 0 else "Low"
        positives = thesis.evidence[:3] or [f"Base-case implied return is {implied_return:.1f}%."]
        negatives = thesis.risks[:3] or ["Free data source; validate against filings and company materials before publishing."]
        return Recommendation(
            ticker=ticker,
            rating=rating,
            confidence=confidence,
            score=round(score, 1),
            rationale=(
                f"{rating} based on Yahoo Finance market data, base-case implied return of "
                f"{implied_return:.1f}%, relative strength of {market.relative_strength_pct:.1f}%, "
                f"and {len(news)} recent news item(s)."
            ),
            positives=positives,
            negatives=negatives,
            source_status="Yahoo Finance via yfinance: free/public, unofficial, research-use data",
            updated_date=date.today(),
        )
