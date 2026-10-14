from fastapi.testclient import TestClient


def test_live_retorna_ok(client: TestClient) -> None:
    resp = client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_confirma_banco_disponivel(client: TestClient) -> None:
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["database"] == "up"
