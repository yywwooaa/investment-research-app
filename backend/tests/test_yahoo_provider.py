from backend.app.providers.snapshot import SnapshotProvider
from backend.app.providers.yahoo import YahooFinanceProvider
from backend.app.settings import ROOT_DIR


def test_yahoo_market_cap_uses_fast_info_when_info_is_sparse():
    fallback = SnapshotProvider(ROOT_DIR / "data" / "fixtures" / "universe.json")
    provider = YahooFinanceProvider(fallback)
    base = fallback.get_company("MU")
    info = {
        "longName": "Micron Technology Inc.",
        "currency": "USD",
    }
    fast_info = {
        "last_price": 1020.76,
        "previous_close": 1087.99,
        "shares": 1_127_734_051,
    }

    profile = provider._build_profile("MU", info, fast_info, base)
    market = provider._build_market(info, fast_info, None, base)

    assert round(profile.market_cap) == 1151
    assert market.price == 1020.76
    assert round(market.daily_change_pct, 1) == -6.2
    assert profile.market_cap != base.profile.market_cap


def test_yahoo_recommendation_flags_extreme_historical_moves():
    fallback = SnapshotProvider(ROOT_DIR / "data" / "fixtures" / "universe.json")
    provider = YahooFinanceProvider(fallback)
    base = fallback.get_company("MU")
    market = base.market.model_copy(update={"relative_strength_pct": 4417.0, "ytd_change_pct": 623.6, "price": 1991.55})
    valuation = base.valuation.model_copy(
        update={"base": base.valuation.base.model_copy(update={"implied_return_pct": -12.1})}
    )

    recommendation = provider._build_recommendation("SNDK", market, valuation, [], base.thesis)

    assert recommendation.rating == "Sell"
    assert recommendation.confidence == "Low"
    assert recommendation.score < 50
    assert "data-quality warning" in recommendation.source_status
    assert "Extreme Yahoo historical move" in recommendation.negatives[0]
