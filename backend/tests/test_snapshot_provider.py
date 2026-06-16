from pathlib import Path

from backend.app.providers.snapshot import SnapshotProvider


def test_snapshot_provider_expands_compact_fixture():
    provider = SnapshotProvider(Path("data/fixtures/universe.json"))

    company = provider.get_company("VRT")

    assert company.profile.name == "Vertiv"
    assert company.market.ev_sales_ntm > 0
    assert len(company.financials.annual) == 4
    assert company.valuation.base.implied_price > company.market.price
    assert company.peers
