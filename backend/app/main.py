from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.exporter import build_substack_markdown
from backend.app.models import (
    CompanyRecord,
    MarkdownExport,
    RefreshResult,
    SavedIdea,
    ScenarioValuation,
    Thesis,
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


@app.get("/api/health")
def health() -> dict[str, str]:
    frontend_status = "served" if _frontend_dist_available() else "api-only"
    return {"status": "ok", "source": settings.data_source, "frontend": frontend_status}


@app.get("/api/universe", response_model=list[UniverseRow])
def get_universe() -> list[UniverseRow]:
    rows: list[UniverseRow] = []
    for company in provider.list_companies():
        record = _with_local_overrides(company)
        rows.append(
            UniverseRow(
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
        )
    return rows


@app.get("/api/company/{ticker}", response_model=CompanyRecord)
def get_company(ticker: str) -> CompanyRecord:
    try:
        return _with_local_overrides(provider.get_company(ticker))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/research/{ticker}", response_model=CompanyRecord)
def research_ticker(ticker: str) -> CompanyRecord:
    normalized = ticker.strip().upper()
    if not normalized or not normalized.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Ticker must be alphanumeric.")
    try:
        return _with_local_overrides(provider.get_company(normalized))
    except KeyError:
        return build_research_intake_record(normalized)


@app.post("/api/data/refresh", response_model=RefreshResult)
def refresh_data() -> RefreshResult:
    return provider.refresh()


@app.get("/api/theses/{ticker}", response_model=Thesis)
def get_thesis(ticker: str) -> Thesis:
    return get_company(ticker).thesis


@app.put("/api/theses/{ticker}", response_model=Thesis)
def put_thesis(ticker: str, thesis: Thesis) -> Thesis:
    if thesis.ticker.upper() != ticker.upper():
        raise HTTPException(status_code=400, detail="Ticker in path and body must match.")
    get_company(ticker)
    return repository.save_thesis(thesis)


@app.get("/api/valuation/{ticker}", response_model=ScenarioValuation)
def get_valuation(ticker: str) -> ScenarioValuation:
    return get_company(ticker).valuation


@app.put("/api/valuation/{ticker}", response_model=ScenarioValuation)
def put_valuation(ticker: str, valuation: ScenarioValuation) -> ScenarioValuation:
    if valuation.ticker.upper() != ticker.upper():
        raise HTTPException(status_code=400, detail="Ticker in path and body must match.")
    get_company(ticker)
    return repository.save_valuation(valuation)


@app.get("/api/saved", response_model=list[SavedIdea])
def list_saved_ideas() -> list[SavedIdea]:
    return repository.list_saved_ideas()


@app.put("/api/saved/{ticker}", response_model=SavedIdea)
def put_saved_idea(ticker: str, idea: SavedIdea) -> SavedIdea:
    if idea.ticker.upper() != ticker.upper():
        raise HTTPException(status_code=400, detail="Ticker in path and body must match.")
    return repository.save_saved_idea(idea)


@app.delete("/api/saved/{ticker}")
def delete_saved_idea(ticker: str) -> dict[str, bool]:
    repository.delete_saved_idea(ticker)
    return {"deleted": True}


@app.post("/api/export/{ticker}/substack", response_model=MarkdownExport)
def export_substack(ticker: str) -> MarkdownExport:
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
