from backend.app.providers.public_sources import PublicSourceEnricher


def test_alpha_vantage_overview_normalizes_analyst_snapshot():
    enricher = PublicSourceEnricher(alpha_vantage_key="demo")
    enricher._alpha_json = lambda _params: {
        "AnalystTargetPrice": "225.50",
        "AnalystRatingStrongBuy": "5",
        "AnalystRatingBuy": "10",
        "AnalystRatingHold": "3",
        "AnalystRatingSell": "1",
        "AnalystRatingStrongSell": "0",
    }

    snapshot = enricher.alpha_vantage_analyst_snapshot("NVDA")

    assert snapshot.source == "Alpha Vantage OVERVIEW; key configured"
    assert snapshot.target_price == 225.5
    assert snapshot.consensus == "Buy"
    assert snapshot.buy == 10


def test_alpha_vantage_information_message_is_preserved_and_redacted():
    enricher = PublicSourceEnricher(alpha_vantage_key="SECRET123")
    enricher._alpha_json = lambda _params: {
        "Information": "Key SECRET123 is not valid for this request. Please check your Alpha Vantage API key."
    }

    snapshot = enricher.alpha_vantage_analyst_snapshot("NVDA")

    assert snapshot.consensus == "Unavailable"
    assert snapshot.source.startswith("Alpha Vantage information:")
    assert "[redacted]" in snapshot.source
    assert "SECRET123" not in snapshot.source


def test_sec_submissions_normalizes_filing_events():
    enricher = PublicSourceEnricher()
    enricher._ticker_cik = {"NVDA": "0001045810"}
    enricher._sec_json = lambda _url: {
        "filings": {
            "recent": {
                "form": ["10-Q", "4", "8-K"],
                "filingDate": ["2026-05-28", "2026-05-29", "2026-06-10"],
                "accessionNumber": ["0001045810-26-000123", "ignore", "0001045810-26-000456"],
                "primaryDocument": ["nvda-20260528.htm", "ignore.htm", "nvda-20260610.htm"],
            }
        }
    }

    events = enricher.sec_filing_events("NVDA")

    assert [event.category for event in events] == ["Filing", "Filing"]
    assert events[0].title == "10-Q filed"
    assert "sec.gov/Archives" in (events[0].url or "")


def test_alpha_vantage_json_cache_reuses_payload_without_second_request():
    enricher = PublicSourceEnricher(alpha_vantage_key="demo")
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Symbol": "NVDA"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, _url, params):
            calls.append(params)
            return FakeResponse()

    import backend.app.providers.public_sources as public_sources

    original_client = public_sources.httpx.Client
    enricher.alpha_min_interval_seconds = 0
    public_sources.httpx.Client = FakeClient
    try:
        first = enricher._alpha_json({"function": "OVERVIEW", "symbol": "NVDA"})
        second = enricher._alpha_json({"symbol": "NVDA", "function": "OVERVIEW"})
    finally:
        public_sources.httpx.Client = original_client

    assert first == {"Symbol": "NVDA"}
    assert second == first
    assert len(calls) == 1
