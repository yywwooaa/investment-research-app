from __future__ import annotations

import hmac
import sqlite3
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.auth import hash_password, hash_token, new_token, normalize_email, send_reset_email, utc_now, verify_password
from backend.app.exporter import build_substack_markdown
from backend.app.models import (
    AdminUser,
    AuthResponse,
    AuthUser,
    CompanyRecord,
    ForgotPasswordRequest,
    MarkdownExport,
    MessageResponse,
    RefreshResult,
    ResetPasswordRequest,
    SavedIdea,
    SearchSuggestion,
    ScenarioValuation,
    SigninRequest,
    SignupRequest,
    Thesis,
    TrendingRow,
    UniverseRow,
)
from backend.app.providers.bloomberg import BloombergConfig, BloombergProvider
from backend.app.providers.snapshot import SnapshotProvider
from backend.app.providers.yahoo import YahooFinanceProvider
from backend.app.research_engine import build_research_intake_record
from backend.app.repository import ResearchRepository
from backend.app.settings import get_settings

settings = get_settings()
snapshot_provider = SnapshotProvider(settings.fixture_path)
if settings.data_source.lower() == "bloomberg":
    provider = BloombergProvider(
        fallback=snapshot_provider,
        config=BloombergConfig(
            host=settings.bloomberg_host,
            port=settings.bloomberg_port,
            local_snapshot_path=settings.local_data_dir / "bloomberg_reference_snapshot.json",
        ),
    )
elif settings.data_source.lower() == "yahoo":
    provider = YahooFinanceProvider(fallback=snapshot_provider)
else:
    provider = snapshot_provider
repository = ResearchRepository(settings.sqlite_path)

COMMON_SEARCH_SUGGESTIONS = [
    SearchSuggestion(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", sector="Technology", industry="Consumer Electronics", source="Common US equity"),
    SearchSuggestion(ticker="SNDK", name="Sandisk Corporation", exchange="NASDAQ", sector="Technology", industry="Computer Hardware", source="Common US equity"),
    SearchSuggestion(ticker="TSLA", name="Tesla, Inc.", exchange="NASDAQ", sector="Consumer Cyclical", industry="Auto Manufacturers", source="Common US equity"),
    SearchSuggestion(ticker="JPM", name="JPMorgan Chase & Co.", exchange="NYSE", sector="Financial Services", industry="Banks", source="Common US equity"),
    SearchSuggestion(ticker="BAC", name="Bank of America Corporation", exchange="NYSE", sector="Financial Services", industry="Banks", source="Common US equity"),
    SearchSuggestion(ticker="NFLX", name="Netflix, Inc.", exchange="NASDAQ", sector="Communication Services", industry="Entertainment", source="Common US equity"),
    SearchSuggestion(ticker="CRM", name="Salesforce, Inc.", exchange="NYSE", sector="Technology", industry="Software", source="Common US equity"),
    SearchSuggestion(ticker="ORCL", name="Oracle Corporation", exchange="NYSE", sector="Technology", industry="Software", source="Common US equity"),
    SearchSuggestion(ticker="SHOP", name="Shopify Inc.", exchange="NYSE", sector="Technology", industry="Software", source="Common US equity"),
    SearchSuggestion(ticker="SQ", name="Block, Inc.", exchange="NYSE", sector="Technology", industry="Financial Technology", source="Common US equity"),
]

app = FastAPI(title=settings.app_name)
allowed_origins = [origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _with_local_overrides(record: CompanyRecord) -> CompanyRecord:
    thesis = repository.get_thesis(record.profile.ticker) or record.thesis
    valuation = repository.get_valuation(record.profile.ticker) or record.valuation
    return record.model_copy(update={"thesis": thesis, "valuation": valuation})


def _create_auth_response(user: AuthUser) -> AuthResponse:
    token = new_token()
    expires_at = utc_now() + timedelta(days=settings.auth_session_days)
    repository.create_session(user.email, hash_token(token), expires_at)
    return AuthResponse(token=token, user=user)


def require_user(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    user = repository.get_user_by_session(hash_token(token))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Sign in again.")
    return user


def require_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    if not settings.admin_key:
        raise HTTPException(status_code=503, detail="Admin key is not configured.")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key.")


def _reset_link(request: Request, token: str) -> str:
    base_url = settings.public_app_url.strip().rstrip("/")
    if not base_url:
        base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/?{urlencode({'reset_token': token})}"


def _send_or_log_reset_email(email: str, link: str) -> None:
    if settings.smtp_host and settings.smtp_from:
        send_reset_email(
            to_email=email,
            reset_link=link,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            smtp_from=settings.smtp_from,
            use_tls=settings.smtp_tls,
        )
        return
    print(f"Password reset requested for {email}. Configure SMTP to email this link: {link}")


def _search_rank(query: str, suggestion: SearchSuggestion) -> tuple[int, str]:
    needle = query.lower()
    ticker = suggestion.ticker.lower()
    name = suggestion.name.lower()
    words = [word.strip(".,()&-").lower() for word in suggestion.name.split()]
    if ticker == needle:
        rank = 0
    elif ticker.startswith(needle):
        rank = 1
    elif words and words[0].startswith(needle):
        rank = 2
    elif any(word.startswith(needle) for word in words):
        rank = 3
    elif needle in name or needle in ticker:
        rank = 4
    else:
        rank = 9
    return rank, suggestion.ticker


def _matches_search(query: str, suggestion: SearchSuggestion) -> bool:
    haystack = " ".join(
        [
            suggestion.ticker,
            suggestion.name,
            suggestion.exchange,
            suggestion.sector,
            suggestion.industry,
        ]
    ).lower()
    return query.lower() in haystack


def _coverage_suggestions(query: str) -> list[SearchSuggestion]:
    suggestions = [
        SearchSuggestion(
            ticker=record.profile.ticker,
            name=record.profile.name,
            exchange="Coverage",
            sector=record.profile.sector,
            industry=record.profile.industry,
            source="Coverage universe",
        )
        for record in snapshot_provider.list_companies()
    ]
    return sorted(
        [suggestion for suggestion in suggestions if _matches_search(query, suggestion)],
        key=lambda suggestion: _search_rank(query, suggestion),
    )


def _common_suggestions(query: str) -> list[SearchSuggestion]:
    return sorted(
        [suggestion for suggestion in COMMON_SEARCH_SUGGESTIONS if _matches_search(query, suggestion)],
        key=lambda suggestion: _search_rank(query, suggestion),
    )


def _yahoo_suggestions(query: str, limit: int) -> list[SearchSuggestion]:
    if settings.data_source.lower() != "yahoo":
        return []
    try:
        import yfinance as yf

        search = yf.Search(
            query,
            max_results=limit,
            news_count=0,
            lists_count=0,
            include_research=False,
            include_cultural_assets=False,
            timeout=5,
            raise_errors=False,
        )
    except Exception:
        return []

    suggestions: list[SearchSuggestion] = []
    for quote in getattr(search, "quotes", []) or []:
        symbol = str(quote.get("symbol") or "").upper().strip()
        quote_type = str(quote.get("quoteType") or quote.get("typeDisp") or "")
        if not symbol or "=" in symbol or quote_type.upper() not in {"EQUITY", "ETF"}:
            continue
        name = quote.get("longname") or quote.get("shortname") or symbol
        suggestions.append(
            SearchSuggestion(
                ticker=symbol,
                name=str(name),
                exchange=str(quote.get("exchDisp") or quote.get("exchange") or ""),
                quote_type=quote_type.title() if quote_type else "Equity",
                sector=str(quote.get("sector") or ""),
                industry=str(quote.get("industry") or ""),
                source="Yahoo Finance",
            )
        )
    return suggestions


def _dedupe_suggestions(suggestions: list[SearchSuggestion], limit: int) -> list[SearchSuggestion]:
    seen: set[str] = set()
    deduped: list[SearchSuggestion] = []
    for suggestion in suggestions:
        if suggestion.ticker in seen:
            continue
        seen.add(suggestion.ticker)
        deduped.append(suggestion)
        if len(deduped) >= limit:
            break
    return deduped


def _record_for_research_view(ticker: str) -> CompanyRecord:
    normalized = ticker.strip().upper()
    try:
        return _with_local_overrides(provider.get_company(normalized))
    except KeyError:
        return build_research_intake_record(normalized)


def _to_universe_row(record: CompanyRecord) -> UniverseRow:
    return UniverseRow(
        ticker=record.profile.ticker,
        name=record.profile.name,
        sector=record.profile.sector,
        industry=record.profile.industry,
        price=record.market.price,
        daily_change_pct=record.market.daily_change_pct,
        ytd_change_pct=record.market.ytd_change_pct,
        relative_strength_pct=record.market.relative_strength_pct,
        ev_sales_ntm=record.market.ev_sales_ntm,
        ev_ebitda_ntm=record.market.ev_ebitda_ntm,
        pe_ntm=record.market.pe_ntm,
        fcf_yield_pct=record.market.fcf_yield_pct,
        stance=record.thesis.stance,
        recommendation=record.recommendation.rating,
        confidence=record.recommendation.confidence,
        source_status=record.recommendation.source_status,
        horizon=record.thesis.horizon,
        catalyst_count=len(record.thesis.catalysts),
        news_count=len(record.news),
        thesis_updated=record.thesis.updated_date,
    )


def _to_trending_row(record: CompanyRecord, source_label: str) -> TrendingRow:
    news_count = len(record.news)
    move_score = abs(record.market.daily_change_pct) * 4
    news_score = news_count * 8
    momentum_score = min(abs(record.market.relative_strength_pct), 100) * 0.2
    score = round(move_score + news_score + momentum_score, 1)
    reason_parts: list[str] = []
    if news_count:
        reason_parts.append(f"{news_count} recent news item(s)")
    if record.market.daily_change_pct:
        reason_parts.append(f"{record.market.daily_change_pct:+.1f}% today")
    if record.market.relative_strength_pct:
        reason_parts.append(f"{record.market.relative_strength_pct:+.1f}% one-year move")
    reason = " / ".join(reason_parts) if reason_parts else "Research intake awaiting source data"
    return TrendingRow(
        ticker=record.profile.ticker,
        name=record.profile.name,
        price=record.market.price,
        daily_change_pct=record.market.daily_change_pct,
        news_count=news_count,
        traction_score=score,
        reason=f"{source_label}: {reason}",
        source_status=record.recommendation.source_status,
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    frontend_status = "served" if _frontend_dist_available() else "api-only"
    return {"status": "ok", "source": settings.data_source, "frontend": frontend_status}


@app.post("/api/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest) -> AuthResponse:
    email = normalize_email(payload.email)
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if settings.auth_require_invite:
        if not settings.invite_code:
            raise HTTPException(status_code=503, detail="Signup is disabled until an invite code is configured.")
        if (payload.invite_code or "").strip() != settings.invite_code:
            raise HTTPException(status_code=403, detail="Invite code is required.")
    try:
        user = repository.create_user(email, hash_password(payload.password))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account already exists for this email.") from exc
    return _create_auth_response(user)


@app.post("/api/auth/signin", response_model=AuthResponse)
def signin(payload: SigninRequest) -> AuthResponse:
    email = normalize_email(payload.email)
    stored_hash = repository.get_password_hash(email)
    if stored_hash is None or not verify_password(payload.password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    user = repository.get_user(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _create_auth_response(user)


@app.get("/api/auth/me", response_model=AuthUser)
def me(user: AuthUser = Depends(require_user)) -> AuthUser:
    return user


@app.get("/api/admin/users", response_model=list[AdminUser])
def admin_users(
    _user: AuthUser = Depends(require_user),
    _admin: None = Depends(require_admin_key),
) -> list[AdminUser]:
    return repository.list_admin_users()


@app.post("/api/auth/signout", response_model=MessageResponse)
def signout(authorization: str | None = Header(default=None)) -> MessageResponse:
    if authorization and authorization.startswith("Bearer "):
        repository.delete_session(hash_token(authorization.removeprefix("Bearer ").strip()))
    return MessageResponse(message="Signed out.")


@app.post("/api/auth/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, request: Request) -> MessageResponse:
    email = normalize_email(payload.email)
    if repository.get_user(email):
        token = new_token()
        expires_at = utc_now() + timedelta(minutes=settings.password_reset_minutes)
        repository.create_password_reset(email, hash_token(token), expires_at)
        _send_or_log_reset_email(email, _reset_link(request, token))
    return MessageResponse(message="If that account exists, a reset link has been sent.")


@app.post("/api/auth/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
    email = repository.consume_password_reset(hash_token(payload.token.strip()))
    if email is None:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired.")
    repository.update_password(email, hash_password(payload.password))
    return MessageResponse(message="Password reset. You can sign in now.")


@app.get("/api/universe", response_model=list[UniverseRow])
def get_universe(_user: AuthUser = Depends(require_user)) -> list[UniverseRow]:
    return [_to_universe_row(_with_local_overrides(company)) for company in provider.list_companies()]


@app.get("/api/watchlist", response_model=list[UniverseRow])
def get_watchlist(_user: AuthUser = Depends(require_user)) -> list[UniverseRow]:
    return [_to_universe_row(_record_for_research_view(idea.ticker)) for idea in repository.list_saved_ideas()]


@app.get("/api/trending", response_model=list[TrendingRow])
def get_trending(
    limit: int = Query(default=12, ge=1, le=24),
    _user: AuthUser = Depends(require_user),
) -> list[TrendingRow]:
    records: dict[str, tuple[CompanyRecord, str]] = {}
    for company in provider.list_companies():
        record = _with_local_overrides(company)
        records[record.profile.ticker] = (record, "Tracked market tape")
    for idea in repository.list_saved_ideas():
        record = _record_for_research_view(idea.ticker)
        records[record.profile.ticker] = (record, "Saved idea")
    rows = [_to_trending_row(record, source_label) for record, source_label in records.values()]
    return sorted(rows, key=lambda row: (-row.traction_score, row.ticker))[:limit]


@app.get("/api/search", response_model=list[SearchSuggestion])
def search_symbols(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=8, ge=1, le=12),
    _user: AuthUser = Depends(require_user),
) -> list[SearchSuggestion]:
    query = q.strip()
    if not query:
        return []
    suggestions = [
        *_coverage_suggestions(query),
        *_common_suggestions(query),
        *_yahoo_suggestions(query, limit),
    ]
    return _dedupe_suggestions(suggestions, limit)


@app.get("/api/company/{ticker}", response_model=CompanyRecord)
def get_company(ticker: str, _user: AuthUser = Depends(require_user)) -> CompanyRecord:
    try:
        return _with_local_overrides(provider.get_company(ticker))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/research/{ticker}", response_model=CompanyRecord)
def research_ticker(ticker: str, _user: AuthUser = Depends(require_user)) -> CompanyRecord:
    normalized = ticker.strip().upper()
    if not normalized or not normalized.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Ticker must be alphanumeric.")
    return _record_for_research_view(normalized)


@app.post("/api/data/refresh", response_model=RefreshResult)
def refresh_data(_user: AuthUser = Depends(require_user)) -> RefreshResult:
    return provider.refresh()


@app.get("/api/theses/{ticker}", response_model=Thesis)
def get_thesis(ticker: str, _user: AuthUser = Depends(require_user)) -> Thesis:
    return get_company(ticker).thesis


@app.put("/api/theses/{ticker}", response_model=Thesis)
def put_thesis(ticker: str, thesis: Thesis, _user: AuthUser = Depends(require_user)) -> Thesis:
    if thesis.ticker.upper() != ticker.upper():
        raise HTTPException(status_code=400, detail="Ticker in path and body must match.")
    get_company(ticker)
    return repository.save_thesis(thesis)


@app.get("/api/valuation/{ticker}", response_model=ScenarioValuation)
def get_valuation(ticker: str, _user: AuthUser = Depends(require_user)) -> ScenarioValuation:
    return get_company(ticker).valuation


@app.put("/api/valuation/{ticker}", response_model=ScenarioValuation)
def put_valuation(ticker: str, valuation: ScenarioValuation, _user: AuthUser = Depends(require_user)) -> ScenarioValuation:
    if valuation.ticker.upper() != ticker.upper():
        raise HTTPException(status_code=400, detail="Ticker in path and body must match.")
    get_company(ticker)
    return repository.save_valuation(valuation)


@app.get("/api/saved", response_model=list[SavedIdea])
def list_saved_ideas(_user: AuthUser = Depends(require_user)) -> list[SavedIdea]:
    return repository.list_saved_ideas()


@app.put("/api/saved/{ticker}", response_model=SavedIdea)
def put_saved_idea(ticker: str, idea: SavedIdea, _user: AuthUser = Depends(require_user)) -> SavedIdea:
    if idea.ticker.upper() != ticker.upper():
        raise HTTPException(status_code=400, detail="Ticker in path and body must match.")
    return repository.save_saved_idea(idea)


@app.delete("/api/saved/{ticker}")
def delete_saved_idea(ticker: str, _user: AuthUser = Depends(require_user)) -> dict[str, bool]:
    repository.delete_saved_idea(ticker)
    return {"deleted": True}


@app.post("/api/export/{ticker}/substack", response_model=MarkdownExport)
def export_substack(ticker: str, _user: AuthUser = Depends(require_user)) -> MarkdownExport:
    return build_substack_markdown(get_company(ticker))


def _frontend_dist_available() -> bool:
    return settings.serve_frontend and (settings.frontend_dist_dir / "index.html").is_file()


if _frontend_dist_available():
    assets_dir = settings.frontend_dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        requested_path = settings.frontend_dist_dir / full_path
        if full_path and requested_path.is_file():
            return FileResponse(requested_path)
        return FileResponse(settings.frontend_dist_dir / "index.html")
