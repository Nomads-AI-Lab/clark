from fastapi.testclient import TestClient

from clark.server import app


def test_healthz_is_public():
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stats_requires_bearer_token_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("CLARK_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("CLARK_DB_PATH", str(tmp_path / "server.db"))
    client = TestClient(app)

    missing = client.get("/v1/stats")
    authorized = client.get("/v1/stats", headers={"Authorization": "Bearer test-token"})

    assert missing.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["entities"] == 0

