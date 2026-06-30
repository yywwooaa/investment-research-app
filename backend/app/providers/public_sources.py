from __future__ import annotations

import csv
import json
import time
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

from backend.app.models import AnalystSnapshot, EventFlag, NewsItem


class PublicSourceEnricher:
    """Optional free/public enrichment sources for the research workbench."""

    def __init__(
        self,
        alpha_vantage_key: str = "",
        sec_user_agent: str = "Variant Research Workbench contact@example.com",
        alpha_vantage_keys: str | list[str] = "",
        alpha_cache_path: Path | str | None = None,
    ):
        self.alpha_vantage_keys = self._normalize_alpha_keys(alpha_vantage_key, alpha_vantage_keys)
        self.alpha_vantage_key = self.alpha_vantage_keys[0] if self.alpha_vantage_keys else ""
        self.sec_user_agent = sec_user_agent.strip() or "Variant Research Workbench contact@example.com"
        self._ticker_cik: dict[str, str] | None = None
        self._alpha_json_cache: dict[tuple[tuple[str, str], ...], tuple[float, dict[str, Any]]] = {}
        self._alpha_text_cache: dict[tuple[tuple[str, str], ...], tuple[float, str]] = {}
        self._alpha_file_cache: dict[str, dict[str, Any]] = {}
        self._alpha_file_cache_loaded = False
        self._alpha_last_request_at = 0.0
        self.alpha_cache_ttl_seconds = 60 * 60 * 24
        self.alpha_min_interval_seconds = 1.15
        self.alpha_cache_path = Path(alpha_cache_path) if alpha_cache_path else None

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
        if not self.alpha_vantage_keys:
            return AnalystSnapshot(source="Alpha Vantage key missing")
        data = self._alpha_json({"function": "OVERVIEW", "symbol": ticker})
        if not data:
            return AnalystSnapshot(source="Alpha Vantage key configured; empty OVERVIEW response")
        if data.get("Note"):
            return AnalystSnapshot(source=f"Alpha Vantage note: {self._safe_alpha_message(data.get('Note'))}")
        if data.get("Information"):
            return AnalystSnapshot(source=f"Alpha Vantage information: {self._safe_alpha_message(data.get('Information'))}")
        if data.get("Error Message"):
            return AnalystSnapshot(source=f"Alpha Vantage error: {self._safe_alpha_message(data.get('Error Message'))}")
        strong_buy = self._int(data.get("AnalystRatingStrongBuy"))
        buy = self._int(data.get("AnalystRatingBuy"))
        hold = self._int(data.get("AnalystRatingHold"))
        sell = self._int(data.get("AnalystRatingSell"))
        strong_sell = self._int(data.get("AnalystRatingStrongSell"))
        target = self._float(data.get("AnalystTargetPrice"))
        has_analyst_payload = any([strong_buy, buy, hold, sell, strong_sell, target])
        if not has_analyst_payload:
            return AnalystSnapshot(source="Alpha Vantage OVERVIEW returned no analyst fields")
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
        if not self.alpha_vantage_keys:
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
        if not self.alpha_vantage_keys:
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

    @staticmethod
    def _normalize_alpha_keys(primary_key: str, extra_keys: str | list[str]) -> list[str]:
        values: list[str] = []
        if primary_key:
            values.extend(str(primary_key).split(","))
        if isinstance(extra_keys, str):
            values.extend(extra_keys.split(","))
        else:
            values.extend(str(key) for key in extra_keys if key)

        keys: list[str] = []
        for value in values:
            key = value.strip()
            if key and key not in keys:
                keys.append(key)
        return keys

    @staticmethod
    def _alpha_cache_key(params: dict[str, str]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((key, str(value)) for key, value in params.items()))

    @staticmethod
    def _alpha_file_token(kind: str, key: tuple[tuple[str, str], ...]) -> str:
        return json.dumps([kind, list(key)], separators=(",", ":"), sort_keys=True)

    def _fresh_alpha_json(self, key: tuple[tuple[str, str], ...]) -> dict[str, Any] | None:
        cached = self._alpha_json_cache.get(key)
        if cached:
            stored_at, payload = cached
            if time.time() - stored_at <= self.alpha_cache_ttl_seconds:
                return payload

        payload = self._fresh_alpha_file_payload("json", key)
        if isinstance(payload, dict):
            self._alpha_json_cache[key] = (time.time(), payload)
            return payload
        return None

    def _fresh_alpha_text(self, key: tuple[tuple[str, str], ...]) -> str | None:
        cached = self._alpha_text_cache.get(key)
        if cached:
            stored_at, payload = cached
            if time.time() - stored_at <= self.alpha_cache_ttl_seconds:
                return payload

        payload = self._fresh_alpha_file_payload("text", key)
        if isinstance(payload, str):
            self._alpha_text_cache[key] = (time.time(), payload)
            return payload
        return None

    def _fresh_alpha_file_payload(self, kind: str, key: tuple[tuple[str, str], ...]) -> Any | None:
        self._load_alpha_file_cache()
        token = self._alpha_file_token(kind, key)
        entry = self._alpha_file_cache.get(token)
        if not isinstance(entry, dict):
            return None
        stored_at = self._float(entry.get("stored_at"))
        if stored_at is None or time.time() - stored_at > self.alpha_cache_ttl_seconds:
            return None
        return entry.get("payload")

    def _load_alpha_file_cache(self) -> None:
        if self._alpha_file_cache_loaded:
            return
        self._alpha_file_cache_loaded = True
        if not self.alpha_cache_path or not self.alpha_cache_path.exists():
            return
        try:
            data = json.loads(self.alpha_cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self._alpha_file_cache = {str(key): value for key, value in data.items() if isinstance(value, dict)}

    def _store_alpha_json(self, key: tuple[tuple[str, str], ...], payload: dict[str, Any]) -> None:
        stored_at = time.time()
        self._alpha_json_cache[key] = (stored_at, payload)
        self._write_alpha_file_payload("json", key, payload, stored_at)

    def _store_alpha_text(self, key: tuple[tuple[str, str], ...], payload: str) -> None:
        stored_at = time.time()
        self._alpha_text_cache[key] = (stored_at, payload)
        self._write_alpha_file_payload("text", key, payload, stored_at)

    def _write_alpha_file_payload(self, kind: str, key: tuple[tuple[str, str], ...], payload: Any, stored_at: float) -> None:
        if not self.alpha_cache_path:
            return
        self._load_alpha_file_cache()
        token = self._alpha_file_token(kind, key)
        self._alpha_file_cache[token] = {"stored_at": stored_at, "payload": payload}
        self._prune_alpha_file_cache(stored_at)
        try:
            self.alpha_cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.alpha_cache_path.with_name(f"{self.alpha_cache_path.name}.tmp")
            temp_path.write_text(json.dumps(self._alpha_file_cache, indent=2, sort_keys=True))
            temp_path.replace(self.alpha_cache_path)
        except OSError:
            return

    def _prune_alpha_file_cache(self, now: float) -> None:
        self._alpha_file_cache = {
            token: entry
            for token, entry in self._alpha_file_cache.items()
            if now - (self._float(entry.get("stored_at")) or 0) <= self.alpha_cache_ttl_seconds
        }

    def _wait_for_alpha_slot(self) -> None:
        elapsed = time.monotonic() - self._alpha_last_request_at
        if elapsed < self.alpha_min_interval_seconds:
            time.sleep(self.alpha_min_interval_seconds - elapsed)
        self._alpha_last_request_at = time.monotonic()

    def _alpha_json(self, params: dict[str, str]) -> dict[str, Any]:
        key = self._alpha_cache_key(params)
        cached = self._fresh_alpha_json(key)
        if cached is not None:
            return cached
        if not self.alpha_vantage_keys:
            return {}

        last_payload: dict[str, Any] = {}
        for index, api_key in enumerate(self.alpha_vantage_keys):
            try:
                self._wait_for_alpha_slot()
                with httpx.Client(timeout=8) as client:
                    response = client.get("https://www.alphavantage.co/query", params={**params, "apikey": api_key})
                    response.raise_for_status()
                    payload = response.json()
            except Exception:
                continue

            if not isinstance(payload, dict):
                continue
            last_payload = payload
            if self._should_try_next_alpha_key(payload) and index < len(self.alpha_vantage_keys) - 1:
                continue
            self._store_alpha_json(key, payload)
            return payload

        if last_payload:
            self._store_alpha_json(key, last_payload)
        return last_payload

    def _alpha_text(self, params: dict[str, str]) -> str:
        key = self._alpha_cache_key(params)
        cached = self._fresh_alpha_text(key)
        if cached is not None:
            return cached
        if not self.alpha_vantage_keys:
            return ""

        last_payload = ""
        for index, api_key in enumerate(self.alpha_vantage_keys):
            try:
                self._wait_for_alpha_slot()
                with httpx.Client(timeout=8) as client:
                    response = client.get("https://www.alphavantage.co/query", params={**params, "apikey": api_key})
                    response.raise_for_status()
                    payload = response.text
            except Exception:
                continue

            last_payload = payload
            if self._alpha_text_suggests_key_limit(payload) and index < len(self.alpha_vantage_keys) - 1:
                continue
            self._store_alpha_text(key, payload)
            return payload

        if last_payload:
            self._store_alpha_text(key, last_payload)
        return last_payload

    @staticmethod
    def _should_try_next_alpha_key(payload: dict[str, Any]) -> bool:
        message = " ".join(str(payload.get(field) or "") for field in ("Note", "Information", "Error Message")).lower()
        return any(
            term in message
            for term in (
                "rate limit",
                "standard api rate limit",
                "requests per day",
                "frequency",
                "premium",
                "api key",
                "invalid",
            )
        )

    @staticmethod
    def _alpha_text_suggests_key_limit(payload: str) -> bool:
        message = payload.lower()
        return any(term in message for term in ("rate limit", "requests per day", "frequency", "premium", "api key", "invalid"))

    def _safe_alpha_message(self, value: Any) -> str:
        message = str(value or "")
        for key in self.alpha_vantage_keys:
            message = message.replace(key, "[redacted]")
        message = " ".join(message.split())
        return message[:220] if message else "No detail returned"

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
