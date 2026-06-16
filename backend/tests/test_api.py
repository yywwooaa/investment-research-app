from fastapi.testclient import TestClient

from backend.app import main as main_module
from backend.app.providers.snapshot import SnapshotProvider
from backend.app.repository import ResearchRepository


def use_snapshot_provider(tmp_path):
    main_module.provider = SnapshotProvider(main_module.settings.fixture_path)
    main_module.repository = ResearchRepository(tmp_path / "workbench.sqlite3")


def test_universe_loads_snapshot(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)

    response = client.get("/api/universe")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 12
    assert payload[0]["ticker"] == "NVDA"
    assert {"price", "ev_sales_ntm", "recommendation", "confidence", "news_count"} <= payload[0].keys()


def test_company_record_shape(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)

    response = client.get("/api/company/NVDA")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["ticker"] == "NVDA"
    assert payload["financials"]["annual"]
    assert payload["valuation"]["base"]["implied_return_pct"] > 0
    assert payload["peers"]
    assert payload["recommendation"]["rating"] == "Buy"
    assert payload["news"]


def test_thesis_save_and_load(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    thesis = client.get("/api/theses/AMD").json()
    thesis["stance"] = "Buy"
    thesis["one_liner"] = "Updated analyst view."

    save_response = client.put("/api/theses/AMD", json=thesis)
    load_response = client.get("/api/theses/AMD")

    assert save_response.status_code == 200
    assert load_response.json()["one_liner"] == "Updated analyst view."
    assert load_response.json()["stance"] == "Buy"


def test_valuation_save_and_load(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    valuation = client.get("/api/valuation/MSFT").json()
    valuation["selected_case"] = "bull"
    valuation["bull"]["implied_return_pct"] = 28.5

    save_response = client.put("/api/valuation/MSFT", json=valuation)
    load_response = client.get("/api/valuation/MSFT")

    assert save_response.status_code == 200
    assert load_response.json()["selected_case"] == "bull"
    assert load_response.json()["bull"]["implied_return_pct"] == 28.5


def test_saved_idea_save_list_and_delete(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    idea = {
        "ticker": "NVDA",
        "note": "Own the AI infrastructure earnings revision cycle.",
        "priority": "High",
        "created_at": "2026-06-16",
        "updated_date": "2026-06-16",
    }

    save_response = client.put("/api/saved/NVDA", json=idea)
    list_response = client.get("/api/saved")
    delete_response = client.delete("/api/saved/NVDA")
    empty_response = client.get("/api/saved")

    assert save_response.status_code == 200
    assert save_response.json()["note"] == idea["note"]
    assert list_response.status_code == 200
    assert list_response.json()[0]["ticker"] == "NVDA"
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert empty_response.json() == []


def test_refresh_and_export(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)

    refresh_response = client.post("/api/data/refresh")
    export_response = client.post("/api/export/GOOGL/substack")

    assert refresh_response.status_code == 200
    assert refresh_response.json()["source"] == "snapshot"
    assert export_response.status_code == 200
    assert "# Alphabet" in export_response.json()["markdown"]
    assert "Disclosure:" in export_response.json()["markdown"]


def test_unknown_ticker_returns_research_intake(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)

    response = client.post("/api/research/CRM")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["ticker"] == "CRM"
    assert payload["recommendation"]["rating"] == "Under Review"
    assert payload["recommendation"]["source_status"] == "Needs Bloomberg/news provider"
