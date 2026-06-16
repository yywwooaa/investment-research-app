from __future__ import annotations


def main() -> None:
    try:
        import yfinance as yf
    except ImportError:
        print("[MISSING] yfinance is not installed. Run: .venv/bin/python -m pip install yfinance")
        raise SystemExit(1)

    ticker = yf.Ticker("AAPL")
    try:
        history = ticker.history(period="5d")
        info = ticker.info
    except Exception as exc:
        print(f"[MISSING] Yahoo Finance request failed: {exc}")
        raise SystemExit(1)

    if history.empty:
        print("[MISSING] Yahoo Finance returned no price history for AAPL.")
        raise SystemExit(1)

    name = info.get("longName") or info.get("shortName") or "AAPL"
    price = history["Close"].iloc[-1]
    print(f"[OK] yfinance installed.")
    print(f"[OK] Yahoo Finance returned {name} latest close: {price:.2f}")
    print("Set VRW_DATA_SOURCE=yahoo in .env and restart the dev server.")


if __name__ == "__main__":
    main()
