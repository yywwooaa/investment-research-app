from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.models import CompanyRecord, DataProvenance, RefreshResult
from backend.app.providers.base import DataProvider
from backend.app.providers.snapshot import SnapshotProvider


DEFAULT_REFERENCE_FIELDS = [
    "PX_LAST",
    "CHG_PCT_1D",
    "YTD_RETURN",
    "CUR_MKT_CAP",
    "EV_TO_T12M_SALES",
    "EV_TO_T12M_EBITDA",
    "BEST_PE_RATIO",
    "FREE_CASH_FLOW_YIELD",
]


@dataclass
class BloombergConfig:
    host: str = "localhost"
    port: int = 8194
    local_snapshot_path: Path | None = None
    reference_fields: list[str] | None = None


class BloombergProvider(DataProvider):
    """Bloomberg Desktop API adapter.

    The implementation intentionally keeps the live fetch narrow for v1 and
    falls back to the public-safe snapshot provider when BLPAPI is unavailable.
    Field names are config-friendly because Bloomberg entitlements and field
    availability can differ by account.
    """

    def __init__(self, fallback: SnapshotProvider, config: BloombergConfig):
        self.fallback = fallback
        self.config = config
        self.fields = config.reference_fields or DEFAULT_REFERENCE_FIELDS
        self._live_records: dict[str, CompanyRecord] | None = None

    def _load_blpapi(self):
        try:
            import blpapi  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Python package 'blpapi' is not installed. Install Bloomberg's "
                "official BLPAPI package and make sure the Terminal API session is running."
            ) from exc
        return blpapi

    def list_companies(self) -> list[CompanyRecord]:
        if self._live_records is not None:
            return list(self._live_records.values())
        return self.fallback.list_companies()

    def get_company(self, ticker: str) -> CompanyRecord:
        key = ticker.upper()
        if self._live_records is not None and key in self._live_records:
            return self._live_records[key]
        return self.fallback.get_company(ticker)

    def refresh(self) -> RefreshResult:
        base_records = self.fallback.list_companies()
        tickers = [record.profile.ticker for record in base_records]
        try:
            blpapi = self._load_blpapi()
            options = blpapi.SessionOptions()
            options.setServerHost(self.config.host)
            options.setServerPort(self.config.port)
            session = blpapi.Session(options)
            if not session.start():
                raise RuntimeError("Unable to start Bloomberg API session.")
            if not session.openService("//blp/refdata"):
                raise RuntimeError("Unable to open Bloomberg reference data service.")
            field_data = self._fetch_reference_data(blpapi, session, tickers)
            session.stop()
        except Exception as exc:
            return RefreshResult(
                source="snapshot",
                refreshed=False,
                message=f"Bloomberg unavailable; using fixture snapshot. Detail: {exc}",
                tickers=tickers,
            )

        live_records = {
            record.profile.ticker: self._overlay_market_data(record, field_data.get(record.profile.ticker, {}))
            for record in base_records
        }
        self._live_records = live_records
        self._write_local_snapshot(field_data)

        return RefreshResult(
            source="bloomberg",
            refreshed=True,
            message=(
                "Bloomberg reference fields refreshed into memory. Local snapshots, if enabled, "
                "are written under data/local and ignored by git."
            ),
            tickers=tickers,
        )

    def _fetch_reference_data(self, blpapi: Any, session: Any, tickers: list[str]) -> dict[str, dict[str, float]]:
        service = session.getService("//blp/refdata")
        request = service.createRequest("ReferenceDataRequest")
        for ticker in tickers:
            request.append("securities", f"{ticker} US Equity")
        for field in self.fields:
            request.append("fields", field)

        session.sendRequest(request)
        results: dict[str, dict[str, float]] = {}

        while True:
            event = session.nextEvent(5000)
            for message in event:
                if not message.hasElement("securityData"):
                    continue
                securities = message.getElement("securityData")
                for index in range(securities.numValues()):
                    security = securities.getValueAsElement(index)
                    ticker = str(security.getElementAsString("security")).split(" ")[0].upper()
                    values: dict[str, float] = {}
                    if security.hasElement("fieldData"):
                        field_data = security.getElement("fieldData")
                        for field in self.fields:
                            if field_data.hasElement(field):
                                value = self._element_to_float(field_data.getElement(field))
                                if value is not None:
                                    values[field] = value
                    results[ticker] = values
            if event.eventType() == blpapi.Event.RESPONSE:
                break

        return results

    @staticmethod
    def _element_to_float(element: Any) -> float | None:
        try:
            value = element.getValue()
        except Exception:
            try:
                value = element.getValueAsFloat()
            except Exception:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _overlay_market_data(self, record: CompanyRecord, field_data: dict[str, float]) -> CompanyRecord:
        if not field_data:
            return record

        profile = record.profile
        market = record.market
        market_cap = field_data.get("CUR_MKT_CAP")
        updated_profile = profile.model_copy(
            update={
                "market_cap": market_cap / 1000 if market_cap and market_cap > 10000 else market_cap or profile.market_cap
            }
        )
        updated_market = market.model_copy(
            update={
                "price": field_data.get("PX_LAST", market.price),
                "daily_change_pct": field_data.get("CHG_PCT_1D", market.daily_change_pct),
                "ytd_change_pct": field_data.get("YTD_RETURN", market.ytd_change_pct),
                "ev_sales_ntm": field_data.get("EV_TO_T12M_SALES", market.ev_sales_ntm),
                "ev_ebitda_ntm": field_data.get("EV_TO_T12M_EBITDA", market.ev_ebitda_ntm),
                "pe_ntm": field_data.get("BEST_PE_RATIO", market.pe_ntm),
                "fcf_yield_pct": field_data.get("FREE_CASH_FLOW_YIELD", market.fcf_yield_pct),
            }
        )
        updated_provenance = DataProvenance(
            quote="Bloomberg Desktop API reference field PX_LAST" if "PX_LAST" in field_data else record.provenance.quote,
            market_cap="Bloomberg Desktop API reference field CUR_MKT_CAP" if "CUR_MKT_CAP" in field_data else record.provenance.market_cap,
            financials="Bloomberg reference fields where available; fixture financial series may still fill gaps",
            valuation="Fixture/user scenario scaffold; edit assumptions before publishing",
            news="No Bloomberg News ingestion in this app flow yet",
            thesis="Fixture or user-authored research",
            recommendation="Generated from available Bloomberg/reference and scenario fields",
            warnings=[
                "Bloomberg reference fields refreshed market data only; thesis, news, and valuation text may still be scaffolded.",
                *record.provenance.warnings,
            ],
        )
        return record.model_copy(update={"profile": updated_profile, "market": updated_market, "provenance": updated_provenance})

    def _write_local_snapshot(self, field_data: dict[str, dict[str, float]]) -> None:
        if self.config.local_snapshot_path is None:
            return
        self.config.local_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "bloomberg",
            "fields": self.fields,
            "data": field_data,
        }
        with self.config.local_snapshot_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
