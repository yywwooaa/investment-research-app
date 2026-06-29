from datetime import date

import pandas as pd

from backend.app.models import NewsItem
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

    assert recommendation.rating == "Under Review"
    assert recommendation.confidence == "Low"
    assert recommendation.score < 50
    assert "data-quality warning" in recommendation.source_status
    assert "Extreme Yahoo historical move" in recommendation.negatives[0]


def test_yahoo_recommendation_goes_under_review_with_fixture_gap():
    fallback = SnapshotProvider(ROOT_DIR / "data" / "fixtures" / "universe.json")
    provider = YahooFinanceProvider(fallback)
    base = fallback.get_company("NVDA")
    info = {"regularMarketPrice": 206.52, "previousClose": 207.41}
    fast_info = {}
    news = base.news

    provenance = provider._build_provenance("NVDA", info, fast_info, None, base, news, base.market, base.valuation)
    recommendation = provider._build_recommendation("NVDA", base.market, base.valuation, news, base.thesis, provenance)

    assert provenance.market_cap == "Fixture fallback"
    assert recommendation.rating == "Under Review"
    assert recommendation.confidence == "Low"
    assert "core fields need validation" in recommendation.source_status


def test_yahoo_news_text_strips_html_markup():
    fallback = SnapshotProvider(ROOT_DIR / "data" / "fixtures" / "universe.json")
    provider = YahooFinanceProvider(fallback)

    cleaned = provider._clean_news_text(
        "<body><p>STORY: A down day on Wall Street.</p><p>Jitters over debt-funded AI spending&nbsp;hit semis.</p></body>"
    )

    assert "<" not in cleaned
    assert "&nbsp;" not in cleaned
    assert "STORY:" not in cleaned
    assert cleaned == "A down day on Wall Street. Jitters over debt-funded AI spending hit semis."


def test_yahoo_recommendation_rationale_summarizes_news_flow():
    fallback = SnapshotProvider(ROOT_DIR / "data" / "fixtures" / "universe.json")
    provider = YahooFinanceProvider(fallback)
    base = fallback.get_company("AMD")
    news = [
        NewsItem(
            title="AMD shares rise after analyst upgrade",
            source="Yahoo Finance",
            published_at=date(2026, 6, 23),
            sentiment="Positive",
            summary="Analysts raised their outlook after stronger demand signals for data center GPUs.",
            impact_reason="May explain sentiment or multiple movement, but validate against fundamentals.",
        ),
        NewsItem(
            title="Chip stocks face export-control risk",
            source="Yahoo Finance",
            published_at=date(2026, 6, 22),
            sentiment="Negative",
            summary="Investors are weighing whether tighter export rules could pressure revenue growth.",
            impact_reason="Could change regulatory, geopolitical, or legal risk in the thesis.",
        ),
    ]

    recommendation = provider._build_recommendation("AMD", base.market, base.valuation, news, base.thesis)

    assert "2 recent news item" not in recommendation.rationale
    assert "Recent news flow looks mixed" in recommendation.rationale
    assert "AMD shares rise after analyst upgrade" in recommendation.rationale
    assert "stronger demand signals" in recommendation.rationale


class FakeTicker:
    def __init__(self, info, income=None, cashflow=None, quarterly_income=None, quarterly_cashflow=None):
        self.info = info
        self.income_stmt = income
        self.cashflow = cashflow
        self.quarterly_income_stmt = quarterly_income
        self.quarterly_cashflow = quarterly_cashflow


def test_yahoo_financials_use_multi_year_statement_history_for_ad_hoc_tickers():
    fallback = SnapshotProvider(ROOT_DIR / "data" / "fixtures" / "universe.json")
    provider = YahooFinanceProvider(fallback)
    income = pd.DataFrame(
        {
            pd.Timestamp("2023-12-31"): {"Total Revenue": 10_000_000_000, "EBITDA": 1_000_000_000, "Diluted EPS": 1.1},
            pd.Timestamp("2024-12-31"): {"Total Revenue": 12_000_000_000, "EBITDA": 1_500_000_000, "Diluted EPS": 1.4},
            pd.Timestamp("2025-12-31"): {"Total Revenue": 15_000_000_000, "EBITDA": 2_100_000_000, "Diluted EPS": 1.9},
        }
    )
    cashflow = pd.DataFrame(
        {
            pd.Timestamp("2023-12-31"): {"Free Cash Flow": 800_000_000},
            pd.Timestamp("2024-12-31"): {"Free Cash Flow": 1_000_000_000},
            pd.Timestamp("2025-12-31"): {"Free Cash Flow": 1_300_000_000},
        }
    )
    ticker = FakeTicker(
        {"totalRevenue": 16_000_000_000, "ebitda": 2_400_000_000, "freeCashflow": 1_600_000_000, "trailingEps": 2.1},
        income=income,
        cashflow=cashflow,
    )

    financials = provider._build_financials(ticker, ticker.info, None)

    assert [point.period for point in financials.annual] == ["2023", "2024", "2025", "Yahoo TTM"]
    assert [point.revenue for point in financials.annual] == [10, 12, 15, 16]
    assert financials.annual[-1].ebitda_margin_pct == 15


class FakeYFinance:
    def __init__(self, tickers):
        self.tickers = tickers

    def Ticker(self, ticker):
        return self.tickers[ticker]


def test_yahoo_generates_peer_metrics_for_off_universe_tickers():
    fallback = SnapshotProvider(ROOT_DIR / "data" / "fixtures" / "universe.json")
    provider = YahooFinanceProvider(fallback)
    peer_tickers = {}
    for ticker, revenue in [("SBUX", 36_000_000_000), ("BROS", 1_500_000_000)]:
        income = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): {"Total Revenue": revenue * 0.8, "EBITDA": revenue * 0.12},
                pd.Timestamp("2025-12-31"): {"Total Revenue": revenue, "EBITDA": revenue * 0.15},
            }
        )
        peer_tickers[ticker] = FakeTicker(
            {
                "shortName": ticker,
                "totalRevenue": revenue,
                "enterpriseValue": revenue * 3,
                "ebitda": revenue * 0.15,
                "marketCap": revenue * 2,
                "freeCashflow": revenue * 0.08,
            },
            income=income,
        )

    profile = fallback.get_company("NVDA").profile.model_copy(
        update={"ticker": "LKNCY", "name": "Luckin Coffee Inc.", "sector": "Consumer Cyclical", "industry": "Restaurants"}
    )

    peers = provider._build_peers(FakeYFinance(peer_tickers), "LKNCY", profile, {}, None)

    assert [peer.ticker for peer in peers] == ["SBUX", "BROS"]
    assert peers[0].ev_sales_ntm == 3
    assert round(peers[0].revenue_growth_ntm_pct, 1) == 25.0
