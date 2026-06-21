from datetime import date
from typing import Any

try:
    import yfinance as yf
except ImportError as exc:  # pragma: no cover - startup guard
    raise SystemExit("yfinance is not installed. Run: .venv/bin/python -m pip install -r backend/requirements-mcp.txt") from exc

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - startup guard
    raise SystemExit("mcp is not installed. Run: .venv/bin/python -m pip install -r backend/requirements-mcp.txt") from exc


mcp = FastMCP("yfinance-research")


def _ticker(symbol: str):
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("Ticker symbol is required.")
    return normalized, yf.Ticker(normalized)


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def _quote_from(symbol: str, ticker: Any) -> dict[str, Any]:
    info = {}
    fast_info = {}
    try:
        info = dict(ticker.info or {})
    except Exception:
        info = {}
    try:
        fast_info = dict(ticker.fast_info or {})
    except Exception:
        fast_info = {}

    price = _num(info.get("regularMarketPrice")) or _num(info.get("currentPrice")) or _num(fast_info.get("last_price"))
    previous_close = (
        _num(info.get("regularMarketPreviousClose"))
        or _num(info.get("previousClose"))
        or _num(fast_info.get("previous_close"))
    )
    daily_change_pct = ((price / previous_close - 1) * 100) if price and previous_close else None
    market_cap = _num(info.get("marketCap")) or _num(fast_info.get("market_cap"))

    return {
        "ticker": symbol,
        "name": info.get("longName") or info.get("shortName") or symbol,
        "price": price,
        "previous_close": previous_close,
        "daily_change_pct": daily_change_pct,
        "market_cap": market_cap,
        "currency": info.get("currency") or info.get("financialCurrency") or "",
        "exchange": info.get("exchange") or info.get("fullExchangeName") or "",
        "source": "Yahoo Finance via yfinance; unofficial/free data, validate before publishing",
        "as_of": date.today().isoformat(),
    }


@mcp.tool()
def get_quote(symbol: str) -> dict[str, Any]:
    """Return a current quote snapshot for a stock ticker from yfinance."""

    normalized, ticker = _ticker(symbol)
    return _quote_from(normalized, ticker)


@mcp.tool()
def get_profile(symbol: str) -> dict[str, Any]:
    """Return company profile and basic valuation fields from yfinance."""

    normalized, ticker = _ticker(symbol)
    info = dict(ticker.info or {})
    return {
        "ticker": normalized,
        "name": info.get("longName") or info.get("shortName") or normalized,
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "market_cap": _num(info.get("marketCap")),
        "enterprise_value": _num(info.get("enterpriseValue")),
        "trailing_pe": _num(info.get("trailingPE")),
        "forward_pe": _num(info.get("forwardPE")),
        "price_to_sales_trailing_12m": _num(info.get("priceToSalesTrailing12Months")),
        "ebitda": _num(info.get("ebitda")),
        "total_revenue": _num(info.get("totalRevenue")),
        "free_cashflow": _num(info.get("freeCashflow")),
        "summary": info.get("longBusinessSummary") or "",
        "source": "Yahoo Finance via yfinance; unofficial/free data, validate before publishing",
    }


@mcp.tool()
def get_history(symbol: str, period: str = "1mo", interval: str = "1d") -> dict[str, Any]:
    """Return recent historical OHLCV rows from yfinance.

    Common periods: 5d, 1mo, 6mo, ytd, 1y, 5y.
    Common intervals: 1d, 1wk, 1mo.
    """

    normalized, ticker = _ticker(symbol)
    history = ticker.history(period=period, interval=interval, auto_adjust=False)
    rows = []
    if history is not None and not history.empty:
        for index, row in history.tail(120).iterrows():
            rows.append(
                {
                    "date": index.date().isoformat() if hasattr(index, "date") else str(index),
                    "open": _num(row.get("Open")),
                    "high": _num(row.get("High")),
                    "low": _num(row.get("Low")),
                    "close": _num(row.get("Close")),
                    "volume": int(row.get("Volume") or 0),
                }
            )
    return {
        "ticker": normalized,
        "period": period,
        "interval": interval,
        "rows": rows,
        "source": "Yahoo Finance via yfinance; unofficial/free data, validate before publishing",
    }


@mcp.tool()
def get_news(symbol: str, limit: int = 10) -> dict[str, Any]:
    """Return recent ticker news from yfinance when Yahoo returns it."""

    normalized, ticker = _ticker(symbol)
    items = []
    for item in list(getattr(ticker, "news", []) or [])[: max(1, min(limit, 20))]:
        content = item.get("content", item) if isinstance(item, dict) else {}
        provider = content.get("provider", {}) if isinstance(content.get("provider"), dict) else {}
        title = content.get("title") or item.get("title")
        if not title:
            continue
        items.append(
            {
                "title": title,
                "publisher": provider.get("displayName") or item.get("publisher") or "Yahoo Finance",
                "published": content.get("pubDate") or item.get("providerPublishTime"),
                "summary": content.get("summary") or content.get("description") or "",
                "url": content.get("clickThroughUrl", {}).get("url")
                if isinstance(content.get("clickThroughUrl"), dict)
                else item.get("link"),
            }
        )
    return {
        "ticker": normalized,
        "items": items,
        "source": "Yahoo Finance via yfinance; unofficial/free data, validate before publishing",
    }


@mcp.tool()
def search_symbols(query: str, limit: int = 8) -> dict[str, Any]:
    """Search Yahoo Finance symbols by company name or ticker."""

    cleaned = query.strip()
    if not cleaned:
        return {"query": query, "results": []}
    search = yf.Search(
        cleaned,
        max_results=max(1, min(limit, 12)),
        news_count=0,
        lists_count=0,
        include_research=False,
        include_cultural_assets=False,
        timeout=5,
        raise_errors=False,
    )
    results = []
    for quote in getattr(search, "quotes", []) or []:
        symbol = str(quote.get("symbol") or "").upper().strip()
        quote_type = str(quote.get("quoteType") or quote.get("typeDisp") or "")
        if not symbol or "=" in symbol or quote_type.upper() not in {"EQUITY", "ETF"}:
            continue
        results.append(
            {
                "ticker": symbol,
                "name": quote.get("longname") or quote.get("shortname") or symbol,
                "exchange": quote.get("exchDisp") or quote.get("exchange") or "",
                "quote_type": quote_type.title() if quote_type else "Equity",
            }
        )
    return {"query": cleaned, "results": results}


if __name__ == "__main__":
    mcp.run()
