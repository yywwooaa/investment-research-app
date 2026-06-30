from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
from typing import Any

import httpx

from backend.app.models import AnalystSnapshot, EventFlag, NewsItem


class PublicSourceEnricher:
    """Optional free/public enrichment sources for the research workbench."""

    def __init__(self, alpha_vantage_key: str = "", sec_user_agent: str = "Variant Research Workbench contact@example.com"):
        self.alpha_vantage_key = alpha_vantage_key.strip()
        self.sec_user_agent = sec_user_agent.strip() or "Variant Research Workbench contact@example.com"
        self._ticker_cik: dict[str, str] | None = None

    def sec_filing_events(self, ticker: str, limit: int = 8) -> list[EventFlag]:
        cik = self._cik_for_ticker(ticker)
        if not cik:
            return []
        data = self._sec_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        recent = data.get("filings", {}).get("recent", {}) if isinstance(data, dict) else {}
        forms = recent.get("form", []) or []
        dates = recent.get("filingDate", []) or []
        accession_numbers = recent.get("accessionNumber", []) or []
        documents = recent.get("primaryDocument", []) or []
        events: list[EventFlag] = []
        for form, filed, accession, document in zip(forms, dates, accession_numbers, documents):
            if form not in {"10-K", "10-Q", "8-K", "20-F", "6-K"}:
                continue
            filed_date = self._parse_date(filed)
            accession_clean = str(accession).replace("-", "")
            url = None
            if accession and document:
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{document}"
            events.append(
                EventFlag(
                    date=filed_date,
                    category="Filing",
                    title=f"{form} filed",
                    description=f"SEC filing posted on {filed_date.isoformat()}; review for estimate, risk, or disclosure changes.",
                    source="SEC EDGAR",
                    sentiment="Neutral",
                    url=url,
                )
            )
            if len(events) >= limit:
                break
        return events

    def alpha_vantage_analyst_snapshot(self, ticker: str) -> AnalystSnapshot:
        if not self.alpha_vantage_key:
            return AnalystSnapshot(source="Alpha Vantage key missing")
        data = self._alpha_json({"function": "OVERVIEW", "symbol": ticker})
        if not data or data.get("Note") or data.get("Information"):
            return AnalystSnapshot(source="Alpha Vantage key configured; no usable analyst payload")
        strong_buy = self._int(data.get("AnalystRatingStrongBuy"))
        buy = self._int(data.get("AnalystRatingBuy"))
        hold = self._int(data.get("AnalystRatingHold"))
        sell = self._int(data.get("AnalystRatingSell"))
        strong_sell = self._int(data.get("AnalystRatingStrongSell"))
        target = self._float(data.get("AnalystTargetPrice"))
        consensus = self._consensus(strong_buy, buy, hold, sell, strong_sell)
        return AnalystSnapshot(
            source="Alpha Vantage OVERVIEW; key configured",
            target_price=target,
            strong_buy=strong_buy,
            buy=buy,
            hold=hold,
            sell=sell,
            strong_sell=strong_sell,
            consensus=consensus,
        )

    def alpha_vantage_news(self, ticker: str, limit: int = 6) -> list[NewsItem]:
        if not self.alpha_vantage_key:
            return []
        data = self._alpha_json({"function": "NEWS_SENTIMENT", "tickers": ticker, "limit": str(limit)})
        feed = data.get("feed", []) if isinstance(data, dict) else []
        items: list[NewsItem] = []
        for item in feed[:limit]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            published = self._parse_alpha_time(item.get("time_published"))
            sentiment = self._sentiment_from_score(self._float(item.get("overall_sentiment_score")))
            summary = str(item.get("summary") or title).strip()
            items.append(
                NewsItem(
                    title=title,
                    source=f"Alpha Vantage / {item.get('source') or 'news'}",
                    published_at=published,
                    sentiment=sentiment,
                    summary=summary,
                    url=item.get("url"),
                    impact_reason="Alpha Vantage news/sentiment item; verify source relevance before using in a thesis.",
                )
            )
        return items

    def alpha_vantage_earnings_events(self, ticker: str, limit: int = 4) -> list[EventFlag]:
        if not self.alpha_vantage_key:
            return []
        csv_text = self._alpha_text({"function": "EARNINGS_CALENDAR", "symbol": ticker, "horizon": "3month"})
        if not csv_text or "symbol" not in csv_text[:80].lower():
            return []
        rows = csv.DictReader(StringIO(csv_text))
        events: list[EventFlag] = []
        for row in rows:
            report_date = self._parse_date(row.get("reportDate"))
            fiscal_end = row.get("fiscalDateEnding") or "upcoming quarter"
            estimate = row.get("estimate") or "n/a"
            events.append(
                EventFlag(
                    date=report_date,
                    category="Earnings",
                    title="Upcoming earnings",
                    description=f"Expected report for fiscal period ending {fiscal_end}; consensus EPS estimate {estimate}.",
                    source="Alpha Vantage earnings calendar",
                    sentiment="Neutral",
                )
            )
            if len(events) >= limit:
                break
        return events

    def _cik_for_ticker(self, ticker: str) -> str | None:
        if self._ticker_cik is None:
            data = self._sec_json("https://www.sec.gov/files/company_tickers.json")
            lookup: dict[str, str] = {}
            if isinstance(data, dict):
                for row in data.values():
                    if not isinstance(row, dict):
                        continue
                    symbol = str(row.get("ticker") or "").upper()
                    cik = self._int(row.get("cik_str"))
                    if symbol and cik:
                        lookup[symbol] = f"{cik:010d}"
            self._ticker_cik = lookup
        return self._ticker_cik.get(ticker.upper())

    def _sec_json(self, url: str) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=8, headers={"User-Agent": self.sec_user_agent}) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception:
            return {}

    def _alpha_json(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get("https://www.alphavantage.co/query", params={**params, "apikey": self.alpha_vantage_key})
                response.raise_for_status()
                return response.json()
        except Exception:
            return {}

    def _alpha_text(self, params: dict[str, str]) -> str:
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get("https://www.alphavantage.co/query", params={**params, "apikey": self.alpha_vantage_key})
                response.raise_for_status()
                return response.text
        except Exception:
            return ""

    @staticmethod
    def _consensus(strong_buy: int | None, buy: int | None, hold: int | None, sell: int | None, strong_sell: int | None) -> str:
        counts = {
            "Strong Buy": strong_buy or 0,
            "Buy": buy or 0,
            "Hold": hold or 0,
            "Sell": sell or 0,
            "Strong Sell": strong_sell or 0,
        }
        if not any(counts.values()):
            return "Unavailable"
        return max(counts, key=counts.get)

    @staticmethod
    def _sentiment_from_score(score: float | None) -> str:
        if score is None:
            return "Neutral"
        if score >= 0.15:
            return "Positive"
        if score <= -0.15:
            return "Negative"
        return "Neutral"

    @staticmethod
    def _parse_alpha_time(value: Any) -> date:
        text = str(value or "")
        try:
            return datetime.strptime(text[:8], "%Y%m%d").date()
        except ValueError:
            return date.today()

    @staticmethod
    def _parse_date(value: Any) -> date:
        try:
            return date.fromisoformat(str(value or "")[:10])
        except ValueError:
            return date.today()

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            if value in (None, "", "None"):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int(value: Any) -> int | None:
        try:
            if value in (None, "", "None"):
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None
