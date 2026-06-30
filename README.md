# Variant Research Workbench

An interview-ready public equities research app for buyside-style stock research. The workbench combines ticker search, saved watchlists, company tear sheets, peer comps, scenario valuation, thesis notes, catalysts/risks, data provenance, and Substack-ready Markdown exports.

The repository is designed to be public-GitHub safe. Demo fixtures are synthetic/sanitized, while local Bloomberg outputs and SQLite research edits stay under ignored `data/local/`.

## What It Shows

- Starter research tape for large public equities, plus search for any ticker your configured provider can resolve.
- Company tear sheets with market snapshot, financial trajectory, peer comps, variant view, catalysts, risks, and watch items.
- Saved-watchlist dashboard with breadth, top movers, recommendation mix, and a personalized heatmap.
- Trending tape ranked by available news count, recent movement, and tracked/saved-name traction.
- Data provenance panel showing which fields are Yahoo/Bloomberg-backed, fixture-backed, scaffolded, or unavailable.
- Stock chart event flags for major price moves, SEC filings, earnings dates, analyst updates, and relevant news when available.
- Aggregated analyst sentiment panel with consensus, target price, and buy/hold/sell distribution when Alpha Vantage is configured.
- Bull/base/bear scenario valuation workspace with editable assumptions and implied return.
- Thesis editor for stance, horizon, one-liner, variant view, evidence, risks, and watch items.
- Saved idea board for bookmarking tickers, setting priority, and writing the reason you want to revisit the name.
- Signup/signin gate with invite-code protection and forgot-password reset flow.
- Owner admin panel for viewing registered users with a private Render-only admin key.
- Structured Substack Markdown export generated from your own thesis fields, not an LLM.
- Bloomberg Desktop API adapter that can refresh configured reference fields locally when `blpapi` and Terminal API are available.
- Buy/hold/sell/under-review recommendation cards with confidence, rationale, source status, positive drivers, negative drivers, and recent-news context.
- Ticker search that opens a tracked company, a provider-backed ticker, or a transparent research-intake state when no sanctioned data is connected.

## Stack

- Frontend: React, TypeScript, Vite, Recharts, Lucide icons
- Backend: FastAPI, Pydantic, SQLite
- Data providers: `SnapshotProvider` for public demo fixtures, `BloombergProvider` for local Bloomberg Desktop API refreshes
- Optional free/public provider: `YahooFinanceProvider` through `yfinance`, SEC EDGAR, and Alpha Vantage
- Optional local MCP server: `scripts/yfinance_mcp_server.py` exposes Yahoo/yfinance tools to MCP clients

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install
npm --prefix frontend install
cp .env.example .env
```

Run the local app:

```bash
npm run dev
```

The API runs on `http://127.0.0.1:8000` and the frontend runs on `http://127.0.0.1:5173`.

Check Yahoo Finance access:

```bash
npm run yahoo:check
```

Install optional MCP dependencies:

```bash
source .venv/bin/activate
pip install -r backend/requirements-mcp.txt
```

Run the yfinance MCP server locally:

```bash
npm run mcp:yfinance
```

Use Yahoo Finance mode:

```bash
VRW_DATA_SOURCE=yahoo
```

Optional free/public enrichment:

```bash
ALPHAVANTAGE_API_KEY=your-alpha-vantage-key
VRW_SEC_USER_AGENT="Variant Research Workbench your-email@example.com"
```

SEC EDGAR does not require an API key and is used for recent filing flags. Alpha Vantage is optional and powers aggregated analyst ratings, target price, earnings-calendar flags, and additional news/sentiment when the key is present.

Generate a local weekly research packet:

```bash
npm run weekly:update
```

The weekly packet is written under ignored `data/local/weekly_updates/`. In snapshot mode it summarizes demo fixtures. In Bloomberg mode it first refreshes the Bloomberg reference fields that your local entitlements allow.

## Bloomberg Mode

Snapshot mode is the default:

```bash
VRW_DATA_SOURCE=snapshot
```

To use Bloomberg locally:

```bash
VRW_DATA_SOURCE=bloomberg
VRW_BLOOMBERG_HOST=localhost
VRW_BLOOMBERG_PORT=8194
```

Install Bloomberg's official Python `blpapi` package and keep Bloomberg Terminal/API available on the machine. The provider requests a small configurable field set through the Desktop API and overlays refreshed market data in memory. If a local snapshot is written, it goes to `data/local/bloomberg_reference_snapshot.json`, which is ignored by git.

Bloomberg setup reference: [Bloomberg API Library](https://www.bloomberg.com/professional/support/api-library/).

## News And Recommendations

The app currently separates the research workflow from the data source:

- The starter tape can include synthetic/sanitized fixture values and demo news summaries.
- Yahoo mode uses `yfinance` for free/public market data and news where available. `yfinance` is unofficial, not affiliated with Yahoo, and should be treated as research/educational/personal-use data rather than institutional-grade data.
- SEC EDGAR is used for official filing-event flags where available.
- Alpha Vantage can add aggregated analyst ratings, target prices, earnings-calendar events, and news sentiment when `ALPHAVANTAGE_API_KEY` is configured.
- Bloomberg mode can refresh financial and market reference fields locally through BLPAPI.
- Current-news automation still needs a licensed source: Bloomberg News/Terminal entitlements, a market-data API with news, RSS feeds you are allowed to use, or manually approved imports.
- Data provenance is field-level: if Yahoo/Bloomberg does not supply a core field, the app flags fixture/scaffold fallback instead of presenting it as current market data.
- The recommendation card is a research signal for interview/demo workflows, not investment advice. It moves to `Under Review` when core source gaps or data-quality warnings are detected.

## API

- `POST /api/auth/signup`
- `POST /api/auth/signin`
- `GET /api/auth/me`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `GET /api/admin/users`
- `GET /api/search?q={query}`
- `GET /api/universe`
- `GET /api/watchlist`
- `GET /api/trending`
- `GET /api/company/{ticker}`
- `POST /api/data/refresh`
- `POST /api/research/{ticker}`
- `GET /api/theses/{ticker}`
- `PUT /api/theses/{ticker}`
- `GET /api/valuation/{ticker}`
- `PUT /api/valuation/{ticker}`
- `POST /api/export/{ticker}/substack`

## Local yfinance MCP Server

The app can also expose Yahoo/yfinance through a local stdio MCP server for MCP-aware clients. This is separate from the website: the website calls FastAPI, while MCP clients call the MCP server directly.

Example MCP client command:

```bash
cd "/Users/yoonchae/Documents/New project"
.venv/bin/python scripts/yfinance_mcp_server.py
```

Tools exposed:

- `get_quote(symbol)`
- `get_profile(symbol)`
- `get_history(symbol, period="1mo", interval="1d")`
- `get_news(symbol, limit=10)`
- `search_symbols(query, limit=8)`

The MCP server uses Yahoo Finance through `yfinance`, which is unofficial/free data. Validate numbers before publishing or using in investment work.

## Tests

```bash
source .venv/bin/activate
pytest backend/tests
npm --prefix frontend run build
```

## Sharing The App

`http://127.0.0.1:5173` only works on your machine. To send a real link to someone, deploy the app.

Recommended path: use Render as one Docker web service. The included `Dockerfile` builds the Vite frontend and serves it from FastAPI, while `render.yaml` configures a public demo with Yahoo mode and temporary local storage.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the exact steps.

## Public-Safety Rules

- Do not commit `.env`.
- Do not commit `data/local/`, SQLite databases, raw Bloomberg exports, or proprietary screenshots.
- Treat the bundled fixture values as synthetic demo data.
- Substack exports should use your own analysis plus data you are permitted to publish.
