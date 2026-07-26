from fastapi.testclient import TestClient


def test_health_is_coc7_native(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Local COC7 KP Assistant",
        "version": "0.1.0",
        "ruleset": "coc7e",
    }


def test_readiness_checks_database(client: TestClient) -> None:
    response = client.get("/api/v1/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "database": "ready",
        "ruleset": "coc7e",
    }

