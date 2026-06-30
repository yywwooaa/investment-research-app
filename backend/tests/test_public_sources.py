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
