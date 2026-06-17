from fastapi.testclient import TestClient

from backend.app import main as main_module
from backend.app.providers.snapshot import SnapshotProvider
from backend.app.repository import ResearchRepository


def use_snapshot_provider(tmp_path):
    main_module.provider = SnapshotProvider(main_module.settings.fixture_path)
    main_module.repository = ResearchRepository(tmp_path / "workbench.sqlite3")


def auth_headers(client: TestClient, email: str = "analyst@example.com") -> dict[str, str]:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "Password123!", "invite_code": None},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_universe_loads_snapshot(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    headers = auth_headers(client)

    response = client.get("/api/universe", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 12
    assert payload[0]["ticker"] == "NVDA"
    assert {"price", "ev_sales_ntm", "recommendation", "confidence", "news_count"} <= payload[0].keys()


def test_company_record_shape(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    headers = auth_headers(client)

    response = client.get("/api/company/NVDA", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["ticker"] == "NVDA"
    assert payload["financials"]["annual"]
    assert payload["valuation"]["base"]["implied_return_pct"] > 0
    assert payload["peers"]
    assert payload["recommendation"]["rating"] == "Buy"
    assert payload["news"]


def test_search_suggestions_resolve_names_and_partials(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    headers = auth_headers(client)

    apple_response = client.get("/api/search?q=apple", headers=headers)
    sandisk_response = client.get("/api/search?q=sand", headers=headers)
    coverage_response = client.get("/api/search?q=nvidia", headers=headers)

    assert apple_response.status_code == 200
    assert any(item["ticker"] == "AAPL" for item in apple_response.json())
    assert any(item["ticker"] == "SNDK" for item in sandisk_response.json())
    assert coverage_response.json()[0]["ticker"] == "NVDA"


def test_thesis_save_and_load(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    headers = auth_headers(client)
    thesis = client.get("/api/theses/AMD", headers=headers).json()
    thesis["stance"] = "Buy"
    thesis["one_liner"] = "Updated analyst view."

    save_response = client.put("/api/theses/AMD", json=thesis, headers=headers)
    load_response = client.get("/api/theses/AMD", headers=headers)

    assert save_response.status_code == 200
    assert load_response.json()["one_liner"] == "Updated analyst view."
    assert load_response.json()["stance"] == "Buy"


def test_valuation_save_and_load(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    headers = auth_headers(client)
    valuation = client.get("/api/valuation/MSFT", headers=headers).json()
    valuation["selected_case"] = "bull"
    valuation["bull"]["implied_return_pct"] = 28.5

    save_response = client.put("/api/valuation/MSFT", json=valuation, headers=headers)
    load_response = client.get("/api/valuation/MSFT", headers=headers)

    assert save_response.status_code == 200
    assert load_response.json()["selected_case"] == "bull"
    assert load_response.json()["bull"]["implied_return_pct"] == 28.5


def test_saved_idea_save_list_and_delete(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    headers = auth_headers(client)
    idea = {
        "ticker": "NVDA",
        "note": "Own the AI infrastructure earnings revision cycle.",
        "priority": "High",
        "created_at": "2026-06-16",
        "updated_date": "2026-06-16",
    }

    save_response = client.put("/api/saved/NVDA", json=idea, headers=headers)
    list_response = client.get("/api/saved", headers=headers)
    delete_response = client.delete("/api/saved/NVDA", headers=headers)
    empty_response = client.get("/api/saved", headers=headers)

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
    headers = auth_headers(client)

    refresh_response = client.post("/api/data/refresh", headers=headers)
    export_response = client.post("/api/export/GOOGL/substack", headers=headers)

    assert refresh_response.status_code == 200
    assert refresh_response.json()["source"] == "snapshot"
    assert export_response.status_code == 200
    assert "# Alphabet" in export_response.json()["markdown"]
    assert "Disclosure:" in export_response.json()["markdown"]


def test_unknown_ticker_returns_research_intake(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    headers = auth_headers(client)

    response = client.post("/api/research/CRM", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["ticker"] == "CRM"
    assert payload["recommendation"]["rating"] == "Under Review"
    assert payload["recommendation"]["source_status"] == "Needs Bloomberg/news provider"


def test_research_routes_require_auth(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)

    response = client.get("/api/universe")
    search_response = client.get("/api/search?q=apple")

    assert response.status_code == 401
    assert search_response.status_code == 401


def test_auth_signin_and_password_reset(tmp_path):
    use_snapshot_provider(tmp_path)
    client = TestClient(main_module.app)
    signup = client.post(
        "/api/auth/signup",
        json={"email": "reset@example.com", "password": "Password123!", "invite_code": None},
    )
    token = signup.json()["token"]

    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    signin_response = client.post("/api/auth/signin", json={"email": "reset@example.com", "password": "Password123!"})
    forgot_response = client.post("/api/auth/forgot-password", json={"email": "reset@example.com"})

    reset_token = main_module.new_token()
    main_module.repository.create_password_reset(
        "reset@example.com",
        main_module.hash_token(reset_token),
        main_module.utc_now() + main_module.timedelta(minutes=10),
    )
    reset_response = client.post("/api/auth/reset-password", json={"token": reset_token, "password": "NewPassword123!"})
    old_signin = client.post("/api/auth/signin", json={"email": "reset@example.com", "password": "Password123!"})
    new_signin = client.post("/api/auth/signin", json={"email": "reset@example.com", "password": "NewPassword123!"})

    assert signup.status_code == 200
    assert me_response.json()["email"] == "reset@example.com"
    assert signin_response.status_code == 200
    assert forgot_response.status_code == 200
    assert reset_response.status_code == 200
    assert old_signin.status_code == 401
    assert new_signin.status_code == 200
