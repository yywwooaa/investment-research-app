from __future__ import annotations

import json
import math
import re
import time
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

from backend.app.models import (
    CompanyProfile,
    CompanyRecord,
    DataProvenance,
    EventFlag,
    FinancialPoint,
    FinancialSeries,
    AnalystSnapshot,
    MarketSnapshot,
    NewsItem,
    PeerMetric,
    PricePoint,
    Recommendation,
    RefreshResult,
    ScenarioAssumption,
    ScenarioValuation,
    Sentiment,
    Thesis,
)
from backend.app.providers.base import DataProvider
from backend.app.providers.public_sources import PublicSourceEnricher
from backend.app.providers.snapshot import SnapshotProvider


class YahooFinanceProvider(DataProvider):
    """Free/public-data provider backed by yfinance.

    yfinance is useful for a personal research prototype, but it is not an
    official Yahoo product and should not be positioned as institutional-grade
    market data.
    """

    def __init__(
        self,
        fallback: SnapshotProvider,
        alpha_vantage_key: str = "",
        alpha_vantage_keys: str | list[str] = "",
        alpha_cache_path: Path | str | None = None,
        company_cache_dir: Path | str | None = None,
        company_cache_ttl_seconds: int = 60 * 15,
        lazy_universe_load: bool = True,
        sec_user_agent: str = "",
    ):
        self.fallback = fallback
        self.public_sources = PublicSourceEnricher(
            alpha_vantage_key=alpha_vantage_key,
            alpha_vantage_keys=alpha_vantage_keys,
            alpha_cache_path=alpha_cache_path,
            sec_user_agent=sec_user_agent,
        )
        self._records: dict[str, CompanyRecord] | None = None
        self._record_timestamps: dict[str, float] = {}
        self.company_cache_dir = Path(company_cache_dir) if company_cache_dir else None
        self.company_cache_ttl_seconds = company_cache_ttl_seconds
        self.lazy_universe_load = lazy_universe_load

    def list_companies(self) -> list[CompanyRecord]:
        if self._records is None:
            if self.lazy_universe_load:
                self._records = {company.profile.ticker: self._starter_record(company) for company in self.fallback.list_companies()}
            else:
                self.refresh()
        return list((self._records or {}).values())

    def get_company(self, ticker: str) -> CompanyRecord:
        key = ticker.upper().strip()
        cached = self._records.get(key) if self._records else None
        if cached is not None and self._record_is_fresh(key):
            return cached

        disk_cached = self._load_company_cache(key)
        if disk_cached is not None:
            if self._records is None:
                self._records = {}
            self._records[key] = disk_cached
            return disk_cached

        try:
            base = self.fallback.get_company(key)
        except KeyError:
            base = cached
        record = self._fetch_company(key, base, include_alpha=True)
        if self._records is None:
            self._records = {}
        self._records[key] = record
        self._record_timestamps[key] = time.time()
        self._store_company_cache(key, record)
        return record

    def _starter_record(self, record: CompanyRecord) -> CompanyRecord:
        warnings = [
            *record.provenance.warnings,
            "Starter tape loaded instantly; open a ticker or press Refresh for live Yahoo/Alpha enrichment.",
        ]
        provenance = record.provenance.model_copy(
            update={
                "quote": "Starter/cached tape",
                "market_cap": "Starter/cached tape",
                "financials": "Starter/cached tape",
                "news": "Starter/cached tape",
                "recommendation": "Starter/cached tape until ticker is opened",
                "warnings": warnings,
            }
        )
        recommendation = record.recommendation.model_copy(
            update={"source_status": "Starter tape; open ticker for live Yahoo/Alpha refresh"}
        )
        return record.model_copy(update={"provenance": provenance, "recommendation": recommendation})

    def _record_is_fresh(self, ticker: str) -> bool:
        stored_at = self._record_timestamps.get(ticker.upper())
        return stored_at is not None and time.time() - stored_at <= self.company_cache_ttl_seconds

    def _company_cache_path(self, ticker: str) -> Path | None:
        if not self.company_cache_dir:
            return None
        safe_ticker = re.sub(r"[^A-Z0-9._-]", "", ticker.upper())
        return self.company_cache_dir / f"{safe_ticker}.json"

    def _load_company_cache(self, ticker: str) -> CompanyRecord | None:
        path = self._company_cache_path(ticker)
        if not path or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
            stored_at = float(payload.get("stored_at") or 0)
            if time.time() - stored_at > self.company_cache_ttl_seconds:
                return None
            record = CompanyRecord.model_validate(payload.get("record"))
        except Exception:
            return None
        self._record_timestamps[ticker.upper()] = stored_at
        return record

    def _store_company_cache(self, ticker: str, record: CompanyRecord) -> None:
        path = self._company_cache_path(ticker)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_name(f"{path.name}.tmp")
            payload = {"stored_at": time.time(), "record": record.model_dump(mode="json")}
            temp_path.write_text(json.dumps(payload, separators=(",", ":")))
            temp_path.replace(path)
        except OSError:
            return

    def refresh(self) -> RefreshResult:
        records: dict[str, CompanyRecord] = {}
        errors: list[str] = []
        for base in self.fallback.list_companies():
            ticker = base.profile.ticker
            try:
                records[ticker] = self._fetch_company(ticker, base, include_alpha=False)
                self._record_timestamps[ticker] = time.time()
                self._store_company_cache(ticker, records[ticker])
            except Exception as exc:
                errors.append(f"{ticker}: {exc}")
                records[ticker] = self._unavailable_record(base, f"Yahoo Finance refresh failed: {exc}")
        self._records = records
        message = "Yahoo Finance refresh completed for tracked starter list."
        if errors:
            message += f" {len(errors)} ticker(s) marked unavailable instead of using demo data."
        return RefreshResult(
            source="yahoo",
            refreshed=not errors,
            message=message,
            tickers=list(records.keys()),
        )

    def _unavailable_record(self, base: CompanyRecord, reason: str) -> CompanyRecord:
        ticker = base.profile.ticker
        market = MarketSnapshot(
            price=0,
            daily_change_pct=0,
            ytd_change_pct=0,
            relative_strength_pct=0,
            ev_sales_ntm=0,
            ev_ebitda_ntm=None,
            pe_ntm=None,
            fcf_yield_pct=None,
        )
        financial_point = FinancialPoint(period="Unavailable", revenue=0)
        return base.model_copy(
            update={
                "profile": base.profile.model_copy(update={"market_cap": 0}),
                "market": market,
                "financials": FinancialSeries(annual=[financial_point], quarterly=[financial_point]),
                "thesis": Thesis(
                    ticker=ticker,
                    stance="Under Review",
                    one_liner="Live source data was unavailable for this refresh.",
                    variant_view="Do not publish or rate this ticker until source-backed data loads.",
                    evidence=[],
                    risks=[],
                    watch_items=["Retry Yahoo refresh", "Check Alpha Vantage status", "Validate against filings"],
                ),
                "valuation": self._empty_valuation(ticker, 0),
                "peers": [],
                "news": [],
                "price_history": [],
                "event_flags": [],
                "analyst_snapshot": AnalystSnapshot(source="Unavailable"),
                "recommendation": Recommendation(
                    ticker=ticker,
                    rating="Under Review",
                    confidence="Low",
                    score=0,
                    rationale=f"Under Review because {reason}. No demo data was used as a substitute.",
                    positives=[],
                    negatives=[reason],
                    source_status="Yahoo/yfinance unavailable; no fallback data used",
                    updated_date=date.today(),
                ),
                "provenance": DataProvenance(
                    quote="Unavailable",
                    market_cap="Unavailable",
                    financials="Unavailable",
                    valuation="Unavailable until user enters DCF assumptions",
                    news="Unavailable",
                    thesis="Blank/user-authored research workspace",
                    recommendation="Under Review because live source refresh failed",
                    warnings=[reason, "No demo fixture values were used as substitutes."],
                    refreshed_date=date.today(),
                ),
            }
        )

    def _fetch_company(self, ticker: str, base: CompanyRecord | None, *, include_alpha: bool = True) -> CompanyRecord:
        import yfinance as yf

        yf_ticker = yf.Ticker(ticker)
        info = self._safe_info(yf_ticker)
        fast_info = self._safe_fast_info(yf_ticker)
        history = self._safe_history(yf_ticker)

        if not info and not fast_info and history is None and base is None:
            raise KeyError(f"Yahoo Finance could not resolve ticker: {ticker}")

        profile = self._build_profile(ticker, info, fast_info, base)
        market = self._build_market(info, fast_info, history, base)
        financials = self._build_financials(yf_ticker, info, base)
        yahoo_news = self._build_news(yf_ticker, ticker, profile.name)
        alpha_news = self.public_sources.alpha_vantage_news(ticker) if include_alpha else []
        news = self._merge_news(yahoo_news, alpha_news)
        peers = self._build_peers(yf, ticker, profile, info, base)
        valuation = self._build_valuation(ticker, market, info, financials, base)
        thesis = self._build_thesis(ticker, profile, market, valuation, news, base)
        provenance = self._build_provenance(ticker, info, fast_info, history, base, news, market, valuation)
        price_history = self._build_price_history(history)
        analyst_snapshot = self._build_analyst_snapshot(ticker, info, include_alpha=include_alpha)
        event_flags = self._build_event_flags(ticker, history, news, analyst_snapshot, market, include_alpha=include_alpha)
        recommendation = self._build_recommendation(ticker, market, valuation, news, thesis, provenance, analyst_snapshot)

        return CompanyRecord(
            profile=profile,
            market=market,
            financials=financials,
            thesis=thesis.model_copy(update={"stance": recommendation.rating}),
            valuation=valuation,
            peers=peers,
            news=news,
            price_history=price_history,
            event_flags=event_flags,
            analyst_snapshot=analyst_snapshot,
            recommendation=recommendation,
            provenance=provenance,
        )

    def _build_analyst_snapshot(self, ticker: str, info: dict[str, Any], *, include_alpha: bool = True) -> AnalystSnapshot:
        alpha_snapshot = self.public_sources.alpha_vantage_analyst_snapshot(ticker) if include_alpha else AnalystSnapshot(source="Alpha Vantage deferred until ticker is opened")
        alpha_has_ratings = any(
            value
            for value in [
                alpha_snapshot.strong_buy,
                alpha_snapshot.buy,
                alpha_snapshot.hold,
                alpha_snapshot.sell,
                alpha_snapshot.strong_sell,
                alpha_snapshot.target_price,
            ]
        )
        if alpha_has_ratings:
            return alpha_snapshot

        target = self._num(info.get("targetMeanPrice"), None)
        recommendation_key = str(info.get("recommendationKey") or "").replace("_", " ").title()
        recommendation_mean = self._num(info.get("recommendationMean"), None)
        if not target and not recommendation_key and not recommendation_mean:
            return alpha_snapshot

        consensus = recommendation_key or self._consensus_from_recommendation_mean(recommendation_mean)
        return AnalystSnapshot(
            source=f"{alpha_snapshot.source}; Yahoo analyst summary fallback",
            target_price=target,
            consensus=consensus or "Yahoo Summary",
        )

    @staticmethod
    def _consensus_from_recommendation_mean(value: float | None) -> str:
        if value is None:
            return ""
        if value <= 1.8:
            return "Buy"
        if value <= 2.6:
            return "Hold"
        if value <= 3.5:
            return "Underperform"
        return "Sell"

    @staticmethod
    def _safe_info(yf_ticker: Any) -> dict[str, Any]:
        try:
            return dict(yf_ticker.info or {})
        except Exception:
            return {}

    @staticmethod
    def _safe_fast_info(yf_ticker: Any) -> dict[str, Any]:
        try:
            return dict(yf_ticker.fast_info or {})
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
    def _safe_statement(yf_ticker: Any, *attrs: str):
        for attr in attrs:
            try:
                statement = getattr(yf_ticker, attr)
                if callable(statement):
                    statement = statement()
                if statement is not None and not getattr(statement, "empty", True):
                    return statement
            except Exception:
                continue
        return None

    @staticmethod
    def _num(value: Any, fallback: float | None = None) -> float | None:
        try:
            if value is None:
                return fallback
            number = float(value)
            return number if math.isfinite(number) else fallback
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _reasonable(value: float | None, fallback: float | None, lower: float = 0, upper: float = 200) -> float | None:
        if value is None or value < lower or value > upper:
            return fallback
        return value

    def _first_num(self, *values: Any) -> float | None:
        for value in values:
            number = self._num(value, None)
            if number is not None:
                return number
        return None

    def _quote_value(self, info: dict[str, Any], fast_info: dict[str, Any]) -> float | None:
        return self._first_num(
            info.get("regularMarketPrice"),
            info.get("currentPrice"),
            info.get("lastPrice"),
            fast_info.get("last_price"),
            fast_info.get("lastPrice"),
        )

    def _previous_close_value(self, info: dict[str, Any], fast_info: dict[str, Any]) -> float | None:
        return self._first_num(
            info.get("regularMarketPreviousClose"),
            info.get("previousClose"),
            fast_info.get("previous_close"),
            fast_info.get("previousClose"),
        )

    def _market_cap(self, info: dict[str, Any], fast_info: dict[str, Any], price: float | None = None) -> float | None:
        market_cap = self._first_num(info.get("marketCap"), info.get("market_cap"), fast_info.get("market_cap"), fast_info.get("marketCap"))
        if market_cap:
            return market_cap

        shares = self._first_num(
            info.get("sharesOutstanding"),
            info.get("impliedSharesOutstanding"),
            fast_info.get("shares"),
            fast_info.get("shares_outstanding"),
            fast_info.get("sharesOutstanding"),
        )
        if shares and price:
            return shares * price
        return None

    def _build_profile(
        self,
        ticker: str,
        info: dict[str, Any],
        fast_info: dict[str, Any],
        base: CompanyRecord | None,
    ) -> CompanyProfile:
        price = self._quote_value(info, fast_info)
        market_cap = self._market_cap(info, fast_info, price)
        return CompanyProfile(
            ticker=ticker,
            name=info.get("longName") or info.get("shortName") or (base.profile.name if base else ticker),
            sector=info.get("sector") or (base.profile.sector if base else "Unknown"),
            industry=info.get("industry") or (base.profile.industry if base else "Unknown"),
            market_cap=(market_cap / 1_000_000_000) if market_cap else 0,
            currency=info.get("financialCurrency") or info.get("currency") or (base.profile.currency if base else "USD"),
            description=info.get("longBusinessSummary") or (base.profile.description if base else "Yahoo Finance profile loaded."),
        )

    def _build_market(
        self,
        info: dict[str, Any],
        fast_info: dict[str, Any],
        history: Any,
        base: CompanyRecord | None,
    ) -> MarketSnapshot:
        price = self._quote_value(info, fast_info)
        previous_close = self._previous_close_value(info, fast_info)
        if price is None and history is not None:
            price = self._num(history["Close"].iloc[-1], None)
        if previous_close is None and history is not None and len(history) > 1:
            previous_close = self._num(history["Close"].iloc[-2], None)
        if price is None:
            price = 0

        daily_change = ((price / previous_close - 1) * 100) if price and previous_close else 0
        ytd_change = 0
        relative_strength = 0
        if history is not None and not history.empty:
            year_start_rows = history[history.index >= f"{date.today().year}-01-01"]
            if not year_start_rows.empty:
                start = self._num(year_start_rows["Close"].iloc[0], None)
                ytd_change = ((price / start - 1) * 100) if price and start else ytd_change
            one_year_start = self._num(history["Close"].iloc[0], None)
            relative_strength = ((price / one_year_start - 1) * 100) if price and one_year_start else relative_strength

        market_cap = self._market_cap(info, fast_info, price)
        enterprise_value = self._num(info.get("enterpriseValue"), None)
        revenue = self._num(info.get("totalRevenue"), None)
        ebitda = self._num(info.get("ebitda"), None)
        ev_sales_raw = enterprise_value / revenue if enterprise_value and revenue else None
        ev_ebitda_raw = enterprise_value / ebitda if enterprise_value and ebitda else None
        ev_sales = self._reasonable(ev_sales_raw, 0, upper=80) or 0
        ev_ebitda = self._reasonable(ev_ebitda_raw, None, upper=150)
        pe = self._num(info.get("forwardPE"), None)
        fcf_yield = None
        free_cashflow = self._num(info.get("freeCashflow"), None)
        if free_cashflow and market_cap:
            fcf_yield = free_cashflow / market_cap * 100
        fcf_yield = self._reasonable(fcf_yield, None, lower=-25, upper=25)

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

    @staticmethod
    def _statement_value(statement: Any, column: Any, row_names: list[str]) -> float | None:
        if statement is None:
            return None
        for row_name in row_names:
            try:
                if row_name in statement.index:
                    value = statement.loc[row_name, column]
                    number = YahooFinanceProvider._num(value, None)
                    if number is not None:
                        return number
            except Exception:
                continue
        return None

    @staticmethod
    def _statement_period(column: Any) -> str:
        try:
            return str(column.year)
        except AttributeError:
            text = str(column)
            return text[:4] if len(text) >= 4 else text

    def _points_from_statements(self, income: Any, cashflow: Any, info: dict[str, Any], *, quarterly: bool = False) -> list[FinancialPoint]:
        if income is None:
            return []
        columns = sorted(list(income.columns))
        points: list[FinancialPoint] = []
        for column in columns:
            revenue = self._statement_value(income, column, ["Total Revenue", "Operating Revenue", "TotalRevenue"])
            if not revenue or revenue <= 0:
                continue
            ebitda = self._statement_value(income, column, ["EBITDA", "Normalized EBITDA", "Ebitda"])
            operating_cashflow = self._statement_value(
                cashflow,
                column,
                ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash Flow From Continuing Operating Activities"],
            )
            capex = self._statement_value(cashflow, column, ["Capital Expenditure", "Capital Expenditures"])
            fcf = self._statement_value(cashflow, column, ["Free Cash Flow", "FreeCashFlow"])
            if fcf is None and operating_cashflow is not None and capex is not None:
                fcf = operating_cashflow + capex
            eps = self._statement_value(income, column, ["Diluted EPS", "Basic EPS", "DilutedEPS", "BasicEPS"])
            suffix = "Q" if quarterly else ""
            points.append(
                FinancialPoint(
                    period=f"{self._statement_period(column)}{suffix}",
                    revenue=revenue / 1_000_000_000,
                    ebitda=(ebitda / 1_000_000_000) if ebitda is not None else None,
                    ebitda_margin_pct=(ebitda / revenue * 100) if ebitda is not None and revenue else None,
                    fcf=(fcf / 1_000_000_000) if fcf is not None else None,
                    eps=eps if eps is not None else self._num(info.get("trailingEps"), None),
                )
            )
        return points

    def _ttm_financial_point(self, info: dict[str, Any], fallback: FinancialPoint | None = None) -> FinancialPoint | None:
        revenue = self._num(info.get("totalRevenue"), None)
        if not revenue:
            return fallback
        ebitda = self._num(info.get("ebitda"), None)
        fcf = self._num(info.get("freeCashflow"), None)
        return FinancialPoint(
            period="Yahoo TTM",
            revenue=revenue / 1_000_000_000,
            ebitda=(ebitda / 1_000_000_000) if ebitda else None,
            ebitda_margin_pct=(ebitda / revenue * 100) if ebitda else None,
            fcf=(fcf / 1_000_000_000) if fcf else None,
            eps=self._num(info.get("trailingEps"), None),
        )

    def _build_financials(self, yf_ticker: Any, info: dict[str, Any], base: CompanyRecord | None) -> FinancialSeries:
        annual_income = self._safe_statement(yf_ticker, "income_stmt", "financials")
        annual_cashflow = self._safe_statement(yf_ticker, "cashflow")
        quarterly_income = self._safe_statement(yf_ticker, "quarterly_income_stmt", "quarterly_financials")
        quarterly_cashflow = self._safe_statement(yf_ticker, "quarterly_cashflow")

        annual = self._points_from_statements(annual_income, annual_cashflow, info)
        quarterly = self._points_from_statements(quarterly_income, quarterly_cashflow, info, quarterly=True)
        ttm = self._ttm_financial_point(info, annual[-1] if annual else None)

        if len(annual) >= 2:
            if ttm and (not annual or annual[-1].period != "Yahoo TTM"):
                annual = [*annual[-4:], ttm]
            return FinancialSeries(annual=annual, quarterly=quarterly or annual[-4:])

        point = ttm or FinancialPoint(period="Yahoo TTM", revenue=0, eps=self._num(info.get("trailingEps"), None))
        return FinancialSeries(annual=[point], quarterly=[point])

    @staticmethod
    def _revenue_growth_from_points(points: list[FinancialPoint]) -> float | None:
        usable = [point for point in points if point.revenue > 0 and not point.period.endswith("Q") and point.period != "Yahoo TTM"]
        if len(usable) < 2:
            return None
        start = usable[0].revenue
        end = usable[-1].revenue
        years = max(len(usable) - 1, 1)
        if start <= 0 or end <= 0:
            return None
        return ((end / start) ** (1 / years) - 1) * 100

    def _peer_candidates(self, profile: CompanyProfile, info: dict[str, Any]) -> list[str]:
        text = f"{profile.sector} {profile.industry} {profile.name} {info.get('longBusinessSummary', '')}".lower()
        if any(term in text for term in ["coffee", "restaurant", "beverage", "food service"]):
            return ["SBUX", "BROS", "YUMC", "MCD", "QSR"]
        if any(term in text for term in ["consumer electronics", "phone", "smartphone", "personal computer"]):
            return ["MSFT", "GOOGL", "META", "AMZN", "DELL", "HPQ"]
        if any(term in text for term in ["semiconductor", "chip", "foundry"]):
            return ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU"]
        if any(term in text for term in ["software", "cloud", "internet content"]):
            return ["MSFT", "GOOGL", "AMZN", "META", "ORCL", "CRM"]
        if any(term in text for term in ["bank", "financial"]):
            return ["JPM", "BAC", "WFC", "C", "GS", "MS"]
        if any(term in text for term in ["auto", "vehicle", "automaker"]):
            return ["TSLA", "GM", "F", "TM", "RIVN"]
        sector_matches = [
            record.profile.ticker
            for record in self.fallback.list_companies()
            if record.profile.sector.lower() == profile.sector.lower()
        ]
        return sector_matches or [record.profile.ticker for record in self.fallback.list_companies()[:5]]

    def _fetch_peer_metric(self, yf: Any, ticker: str) -> PeerMetric | None:
        try:
            yf_ticker = yf.Ticker(ticker)
            info = self._safe_info(yf_ticker)
            if not info:
                return None
            financials = self._build_financials(yf_ticker, info, None)
            latest = financials.annual[-1] if financials.annual else None
            revenue = self._num(info.get("totalRevenue"), None) or ((latest.revenue * 1_000_000_000) if latest else None)
            market_cap = self._num(info.get("marketCap"), None)
            enterprise_value = self._num(info.get("enterpriseValue"), None) or market_cap
            ebitda = self._num(info.get("ebitda"), None) or ((latest.ebitda * 1_000_000_000) if latest and latest.ebitda else None)
            free_cashflow = self._num(info.get("freeCashflow"), None) or ((latest.fcf * 1_000_000_000) if latest and latest.fcf else None)
            ev_sales = enterprise_value / revenue if enterprise_value and revenue else self._num(info.get("enterpriseToRevenue"), 0) or 0
            ev_ebitda = enterprise_value / ebitda if enterprise_value and ebitda else self._num(info.get("enterpriseToEbitda"), None)
            growth = self._revenue_growth_from_points(financials.annual)
            if growth is None:
                growth = (self._num(info.get("revenueGrowth"), 0) or 0) * 100
            fcf_yield = free_cashflow / market_cap * 100 if free_cashflow and market_cap else None
            return PeerMetric(
                ticker=ticker,
                name=info.get("shortName") or info.get("longName") or ticker,
                ev_sales_ntm=self._reasonable(ev_sales, 0, upper=100) or 0,
                ev_ebitda_ntm=self._reasonable(ev_ebitda, None, upper=200),
                revenue_growth_ntm_pct=growth,
                ebitda_margin_ntm_pct=(ebitda / revenue * 100) if ebitda and revenue else None,
                fcf_yield_pct=self._reasonable(fcf_yield, None, lower=-50, upper=50),
            )
        except Exception:
            return None

    def _build_peers(
        self,
        yf: Any,
        ticker: str,
        profile: CompanyProfile,
        info: dict[str, Any],
        base: CompanyRecord | None,
    ) -> list[PeerMetric]:
        if base and base.peers:
            return base.peers[:5]
        candidates = self._peer_candidates(profile, info)
        peers: list[PeerMetric] = []
        seen = {ticker.upper()}
        for candidate in candidates:
            normalized = candidate.upper().strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            metric = self._fetch_peer_metric(yf, normalized)
            if metric is not None:
                peers.append(metric)
            if len(peers) >= 5:
                break
        return peers

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
            title = self._clean_news_text(title)
            summary = self._clean_news_text(content.get("summary") or content.get("description") or title or f"Recent Yahoo Finance item for {ticker}.")
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
    def _merge_news(primary: list[NewsItem], secondary: list[NewsItem]) -> list[NewsItem]:
        placeholder = "No ticker-specific Yahoo Finance news returned"
        combined = [item for item in [*secondary, *primary] if not item.title.startswith(placeholder)]
        if not combined:
            return primary
        seen: set[str] = set()
        deduped: list[NewsItem] = []
        for item in sorted(combined, key=lambda news: news.published_at, reverse=True):
            key = re.sub(r"\W+", "", item.title.lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= 12:
                break
        return deduped

    @staticmethod
    def _build_price_history(history: Any) -> list[PricePoint]:
        if history is None:
            return []
        points: list[PricePoint] = []
        try:
            recent = history.tail(180)
            for index, row in recent.iterrows():
                close = YahooFinanceProvider._num(row.get("Close"), None)
                if close is None or close <= 0:
                    continue
                point_date = index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
                points.append(
                    PricePoint(
                        date=point_date,
                        close=round(close, 2),
                        volume=YahooFinanceProvider._num(row.get("Volume"), None),
                    )
                )
        except Exception:
            return []
        return points

    def _build_event_flags(
        self,
        ticker: str,
        history: Any,
        news: list[NewsItem],
        analyst_snapshot: Any,
        market: MarketSnapshot,
        *,
        include_alpha: bool = True,
    ) -> list[EventFlag]:
        events: list[EventFlag] = []
        events.extend(self._price_move_events(history))
        events.extend(self.public_sources.sec_filing_events(ticker))
        if include_alpha:
            events.extend(self.public_sources.alpha_vantage_earnings_events(ticker))
        if analyst_snapshot.target_price:
            implied = (analyst_snapshot.target_price / market.price - 1) * 100 if market.price else None
            events.append(
                EventFlag(
                    date=analyst_snapshot.as_of,
                    category="Analyst",
                    title=f"{analyst_snapshot.consensus} analyst consensus",
                    description=(
                        f"Aggregated analyst target is ${analyst_snapshot.target_price:.2f}"
                        + (f", implying {implied:.1f}% versus spot." if implied is not None else ".")
                    ),
                    source=analyst_snapshot.source,
                    sentiment="Positive" if implied and implied > 10 else "Negative" if implied and implied < -10 else "Neutral",
                    price_change_pct=implied,
                )
            )
        for item in news[:5]:
            if item.title.startswith("No ticker-specific Yahoo Finance news returned"):
                continue
            events.append(
                EventFlag(
                    date=item.published_at,
                    category="News",
                    title=item.title,
                    description=item.impact_reason,
                    source=item.source,
                    sentiment=item.sentiment,
                    url=item.url,
                )
            )
        return sorted(events, key=lambda event: event.date, reverse=True)[:18]

    @staticmethod
    def _price_move_events(history: Any) -> list[EventFlag]:
        if history is None:
            return []
        events: list[EventFlag] = []
        try:
            recent = history.tail(120).copy()
            closes = recent["Close"]
            pct_changes = closes.pct_change() * 100
            for index, change in pct_changes.dropna().items():
                if abs(float(change)) < 5:
                    continue
                point_date = index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
                direction = "rose" if change > 0 else "fell"
                events.append(
                    EventFlag(
                        date=point_date,
                        category="Price Move",
                        title=f"Stock {direction} {abs(float(change)):.1f}%",
                        description="Large one-day move; match against news, filings, earnings, or sector moves before attributing causality.",
                        source="Yahoo/yfinance price history",
                        sentiment="Positive" if change > 0 else "Negative",
                        price_change_pct=round(float(change), 1),
                    )
                )
        except Exception:
            return []
        return sorted(events, key=lambda event: abs(event.price_change_pct or 0), reverse=True)[:6]

    @staticmethod
    def _clean_news_text(value: Any) -> str:
        text = unescape(str(value or ""))
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        text = re.sub(r"(?i)</p\s*>", ". ", text)
        text = re.sub(r"(?i)<br\s*/?>", ". ", text)
        text = re.sub(r"(?i)</?(body|html|div|span|article|section|p)[^>]*>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"^\s*(story|update|brief)\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*::\s*", ": ", text)
        text = re.sub(r"\s+", " ", text).strip(" .")
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"([.!?]){2,}", r"\1", text)
        return f"{text}." if text and text[-1] not in ".!?" else text

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
            return "Potential read-through for sector demand, capex, or competitive positioning."
        if any(term in text for term in {"deal", "partnership", "customer", "contract", "order"}):
            return "Could affect revenue visibility, customer adoption, or backlog confidence."
        if any(term in text for term in {"regulation", "export", "china", "antitrust", "lawsuit", "probe"}):
            return "Could change regulatory, geopolitical, or legal risk in the thesis."
        if any(term in text for term in {"upgrade", "downgrade", "target", "analyst"}):
            return "May explain sentiment or multiple movement, but validate against fundamentals."
        return "Worth scanning for thesis impact; no obvious model-driver keyword detected."

    @staticmethod
    def _shorten_news_text(value: str, limit: int = 170) -> str:
        text = re.sub(r"\s+", " ", value).strip()
        if len(text) <= limit:
            return text
        sentence = re.split(r"(?<=[.!?])\s+", text)[0]
        if 40 <= len(sentence) <= limit:
            return sentence
        return f"{text[: limit - 3].rsplit(' ', 1)[0]}..."

    def _summarize_news_flow(self, news: list[NewsItem]) -> str:
        real_news = [
            item
            for item in news
            if not item.title.startswith("No ticker-specific Yahoo Finance news returned")
        ]
        if not real_news:
            return "No clearly ticker-specific recent Yahoo news was returned, so the news signal is not yet useful."

        positive_count = sum(1 for item in real_news if item.sentiment == "Positive")
        negative_count = sum(1 for item in real_news if item.sentiment == "Negative")
        if positive_count > negative_count:
            tone = "positive"
        elif negative_count > positive_count:
            tone = "negative"
        elif positive_count and negative_count:
            tone = "mixed"
        else:
            tone = "neutral"

        prioritized = sorted(
            real_news,
            key=lambda item: (
                item.sentiment == "Neutral",
                -item.published_at.toordinal(),
            ),
        )
        drivers = []
        for item in prioritized[:2]:
            summary = item.summary
            if summary.lower() == item.title.lower():
                summary = item.impact_reason
            drivers.append(f"{item.title}: {self._shorten_news_text(summary)}")
        return f"Recent news flow looks {tone}: {' | '.join(drivers)}"

    def _build_valuation(
        self,
        ticker: str,
        market: MarketSnapshot,
        info: dict[str, Any],
        financials: FinancialSeries,
        base: CompanyRecord | None,
    ) -> ScenarioValuation:
        base_revenue = financials.annual[-1].revenue if financials.annual else 0
        target_mean = self._num(info.get("targetMeanPrice"), None)
        if target_mean and market.price:
            return self._target_price_valuation(ticker, base_revenue, target_mean, market.price)
        return self._empty_valuation(ticker, base_revenue)

    @staticmethod
    def _scenario_from_price(price: float, current_price: float) -> ScenarioAssumption:
        implied_return = (price / current_price - 1) * 100 if current_price else 0
        return ScenarioAssumption(
            revenue_cagr_pct=0,
            terminal_margin_pct=0,
            exit_multiple=0,
            discount_rate_pct=0,
            implied_price=round(price, 2),
            implied_return_pct=implied_return,
        )

    def _target_price_valuation(self, ticker: str, base_revenue: float, target_price: float, current_price: float) -> ScenarioValuation:
        return ScenarioValuation(
            ticker=ticker,
            base_year_revenue=base_revenue,
            net_cash_debt=0,
            diluted_shares=0,
            bull=self._scenario_from_price(target_price * 1.15, current_price),
            base=self._scenario_from_price(target_price, current_price),
            bear=self._scenario_from_price(target_price * 0.8, current_price),
            notes=(
                "Yahoo Finance target mean price loaded. This is not a DCF; edit the valuation workspace "
                "with your own assumptions before publishing."
            ),
            updated_date=date.today(),
        )

    @staticmethod
    def _empty_valuation(ticker: str, base_revenue: float) -> ScenarioValuation:
        empty_case = ScenarioAssumption(
            revenue_cagr_pct=0,
            terminal_margin_pct=0,
            exit_multiple=0,
            discount_rate_pct=0,
            implied_price=0,
            implied_return_pct=0,
        )
        return ScenarioValuation(
            ticker=ticker,
            base_year_revenue=base_revenue,
            net_cash_debt=0,
            diluted_shares=0,
            bull=empty_case,
            base=empty_case,
            bear=empty_case,
            notes=(
                "No sourced valuation target is loaded. Enter DCF assumptions manually or connect a licensed/source-backed target."
            )
        )

    def _build_thesis(
        self,
        ticker: str,
        profile: CompanyProfile,
        market: MarketSnapshot,
        valuation: ScenarioValuation,
        news: list[NewsItem],
        base: CompanyRecord | None,
    ) -> Thesis:
        thesis = Thesis(
            ticker=ticker,
            stance="Under Review",
            one_liner=f"{profile.name} is loaded for source-backed research review.",
            variant_view="Build the differentiated view after reviewing source-backed financials, valuation, news, and filings.",
            evidence=[],
            risks=[],
            watch_items=["Review Yahoo Finance quote/news", "Check SEC filings", "Build peer set", "Refine valuation cases"],
        )
        evidence: list[str] = []
        if market.ytd_change_pct:
            evidence.append(f"YTD performance: {market.ytd_change_pct:.1f}%.")
        if market.ev_sales_ntm:
            evidence.append(f"EV/Sales: {market.ev_sales_ntm:.1f}x.")
        real_news_count = sum(1 for item in news if not item.title.startswith("No ticker-specific Yahoo Finance news returned"))
        if real_news_count:
            evidence.append(f"Recent source-backed news items loaded: {real_news_count}.")
        return thesis.model_copy(
            update={
                "ticker": ticker,
                "updated_date": date.today(),
                "evidence": evidence,
            }
        )

    def _build_provenance(
        self,
        ticker: str,
        info: dict[str, Any],
        fast_info: dict[str, Any],
        history: Any,
        base: CompanyRecord | None,
        news: list[NewsItem],
        market: MarketSnapshot,
        valuation: ScenarioValuation,
    ) -> DataProvenance:
        quote_source = "Unavailable"
        if self._first_num(info.get("regularMarketPrice"), info.get("currentPrice"), info.get("lastPrice")) is not None:
            quote_source = "Yahoo Finance quote field"
        elif self._first_num(fast_info.get("last_price"), fast_info.get("lastPrice")) is not None:
            quote_source = "Yahoo Finance fast quote"
        elif history is not None:
            quote_source = "Yahoo Finance latest historical close"

        market_cap_source = "Unavailable"
        if self._first_num(info.get("marketCap"), info.get("market_cap")) is not None:
            market_cap_source = "Yahoo Finance marketCap"
        elif self._first_num(fast_info.get("market_cap"), fast_info.get("marketCap")) is not None:
            market_cap_source = "Yahoo Finance fast market cap"
        elif self._first_num(
            info.get("sharesOutstanding"),
            info.get("impliedSharesOutstanding"),
            fast_info.get("shares"),
            fast_info.get("shares_outstanding"),
            fast_info.get("sharesOutstanding"),
        ) is not None and self._quote_value(info, fast_info) is not None:
            market_cap_source = "Yahoo shares outstanding x quote"

        financials_source = "Yahoo Finance TTM fundamentals" if self._num(info.get("totalRevenue"), None) else "Unavailable"

        if self._num(info.get("targetMeanPrice"), None):
            valuation_source = "Yahoo analyst target mean; not a DCF"
        else:
            valuation_source = "Unavailable until user enters DCF assumptions"

        has_real_news = bool(news) and not news[0].title.startswith("No ticker-specific Yahoo Finance news returned")
        news_source = "Yahoo Finance ticker news" if has_real_news else "No current Yahoo ticker news returned"
        thesis_source = "Blank/user-authored research workspace"

        warnings: list[str] = [
            "Yahoo/yfinance is a free unofficial source; validate figures against filings or a licensed feed before publishing."
        ]
        if market_cap_source == "Unavailable":
            warnings.append(f"{ticker} market cap was not returned by the live source.")
        if financials_source == "Unavailable":
            warnings.append(f"{ticker} financial series was not returned by the live source.")
        if "Unavailable" in valuation_source:
            warnings.append(f"{ticker} valuation/recommendation needs user-entered DCF assumptions or a sourced analyst target.")
        if not has_real_news:
            warnings.append("Yahoo did not return clearly ticker-specific recent news for this request.")
        if abs(market.relative_strength_pct) > 500 or abs(market.ytd_change_pct) > 500:
            warnings.append("Extreme historical move detected; validate splits, corporate actions, and quote source.")
        if valuation.base.implied_price == 0:
            warnings.append("No usable valuation target is loaded yet.")

        return DataProvenance(
            quote=quote_source,
            market_cap=market_cap_source,
            financials=financials_source,
            valuation=valuation_source,
            news=news_source,
            thesis=thesis_source,
            recommendation="Rule-based signal from available quote, momentum, news, and scenario fields",
            warnings=warnings,
            refreshed_date=date.today(),
        )

    def _build_recommendation(
        self,
        ticker: str,
        market: MarketSnapshot,
        valuation: ScenarioValuation,
        news: list[NewsItem],
        thesis: Thesis,
        provenance: DataProvenance | None = None,
        analyst_snapshot: AnalystSnapshot | None = None,
    ) -> Recommendation:
        implied_return = valuation.base.implied_return_pct
        analyst_return = (
            (analyst_snapshot.target_price / market.price - 1) * 100
            if analyst_snapshot and analyst_snapshot.target_price and market.price
            else None
        )
        has_rating_distribution = bool(
            analyst_snapshot
            and any(
                value
                for value in [
                    analyst_snapshot.strong_buy,
                    analyst_snapshot.buy,
                    analyst_snapshot.hold,
                    analyst_snapshot.sell,
                    analyst_snapshot.strong_sell,
                ]
            )
        )
        rating_total = 0
        hold_ratio = 0.0
        if has_rating_distribution and analyst_snapshot:
            rating_total = sum(
                value or 0
                for value in [
                    analyst_snapshot.strong_buy,
                    analyst_snapshot.buy,
                    analyst_snapshot.hold,
                    analyst_snapshot.sell,
                    analyst_snapshot.strong_sell,
                ]
            )
            hold_ratio = ((analyst_snapshot.hold or 0) / rating_total) if rating_total else 0.0
        analyst_consensus = analyst_snapshot.consensus if analyst_snapshot and analyst_snapshot.consensus != "Unavailable" else ""
        analyst_is_usable = analyst_return is not None or has_rating_distribution or bool(analyst_consensus)
        data_quality_warning = abs(market.relative_strength_pct) > 500 or abs(market.ytd_change_pct) > 500
        fallback_gap = False
        if provenance is not None:
            fallback_gap = any(
                marker in source.lower()
                for source in [provenance.quote, provenance.market_cap, provenance.financials, provenance.valuation]
                for marker in ["fixture", "unavailable", "scaffold"]
            )
        bounded_relative_strength = min(100, max(-100, market.relative_strength_pct))
        blended_return = implied_return
        if analyst_return is not None:
            blended_return = implied_return * 0.65 + analyst_return * 0.35
        score = min(100, max(0, 50 + blended_return * 1.1 + bounded_relative_strength * 0.05))
        consensus_key = analyst_consensus.lower()
        if blended_return >= 15 and consensus_key not in {"sell", "strong sell", "underperform"}:
            rating = "Buy"
        elif blended_return <= -10 or consensus_key in {"sell", "strong sell"}:
            rating = "Sell"
        else:
            rating = "Hold"
        if analyst_consensus.lower() in {"hold", "neutral"} and rating == "Buy" and blended_return < 20:
            rating = "Hold"
        if has_rating_distribution and hold_ratio >= 0.6 and rating == "Buy":
            rating = "Hold"
        confidence = "Medium" if abs(blended_return) >= 10 and market.price > 0 else "Low"
        if data_quality_warning:
            confidence = "Low"
        if fallback_gap or data_quality_warning:
            rating = "Under Review"
            confidence = "Low"
            score = min(score, 55)
        positives = thesis.evidence[:3] or []
        if analyst_return is not None and analyst_return > 0:
            positives = [f"Analyst target implies {analyst_return:.1f}% upside.", *positives]
        negatives = thesis.risks[:3] or ["Free data source; validate against filings and company materials before publishing."]
        if analyst_consensus.lower() in {"hold", "neutral"}:
            negatives = [f"Analyst consensus is {analyst_consensus}, which tempers the model signal.", *negatives]
        if has_rating_distribution and hold_ratio >= 0.6:
            negatives = [f"Most available analyst ratings are Hold ({analyst_snapshot.hold or 0} of {rating_total}).", *negatives]
        if analyst_return is not None and analyst_return < 0:
            negatives = [f"Analyst target implies {abs(analyst_return):.1f}% downside.", *negatives]
        if fallback_gap:
            negatives = [
                "Some core fields are unavailable; validate live market cap, financials, and valuation before assigning a rating.",
                *negatives,
            ]
        if data_quality_warning:
            negatives = [
                "Extreme Yahoo historical move detected; validate splits, corporate actions, and quote source before using momentum.",
                *negatives,
            ]
        source_status = "Yahoo/yfinance where available; unavailable fields keep the rating Under Review"
        if fallback_gap:
            source_status += "; data-quality warning: core fields unavailable"
        if data_quality_warning:
            source_status += "; data-quality warning: extreme historical move requires validation"
        news_summary = self._summarize_news_flow(news)
        analyst_phrase = ""
        if analyst_is_usable:
            parts = []
            if analyst_consensus:
                parts.append(f"analyst consensus of {analyst_consensus}")
            if analyst_return is not None:
                parts.append(f"analyst target implied return of {analyst_return:.1f}%")
            if has_rating_distribution:
                distribution = {
                    "strong buy": analyst_snapshot.strong_buy or 0,
                    "buy": analyst_snapshot.buy or 0,
                    "hold": analyst_snapshot.hold or 0,
                    "sell": analyst_snapshot.sell or 0,
                    "strong sell": analyst_snapshot.strong_sell or 0,
                }
                parts.append("rating distribution " + "/".join(f"{label} {value}" for label, value in distribution.items() if value))
            analyst_phrase = " Analyst input included " + ", ".join(parts) + "."
        if rating == "Under Review":
            rationale = (
                "Under Review because the app detected source gaps or data-quality warnings. "
                f"Current source view shows base-case implied return of {implied_return:.1f}%, "
                f"relative strength of {market.relative_strength_pct:.1f}%.{analyst_phrase} {news_summary}"
            )
        else:
            return_phrase = (
                f"blended model/analyst implied return of {blended_return:.1f}% (model {implied_return:.1f}%)"
                if analyst_return is not None
                else f"model implied return of {implied_return:.1f}%"
            )
            rationale = (
                f"{rating} based on Yahoo Finance market data, {return_phrase}, relative strength of {market.relative_strength_pct:.1f}%, "
                f"and the latest news context.{analyst_phrase} {news_summary}"
            )
        return Recommendation(
            ticker=ticker,
            rating=rating,
            confidence=confidence,
            score=round(score, 1),
            rationale=rationale,
            positives=positives,
            negatives=negatives,
            source_status=source_status,
            updated_date=date.today(),
        )
