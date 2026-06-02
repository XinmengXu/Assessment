from fastapi.testclient import TestClient

from app.main import app


def test_export_attempts_endpoint_returns_csv():
    client = TestClient(app)
    response = client.get("/api/exports/attempts")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
