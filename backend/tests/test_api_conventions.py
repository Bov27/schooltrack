from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_unknown_route_uses_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_wrong_method_uses_standard_error_shape(client: TestClient) -> None:
    response = client.post("/api/v1/health/live")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert len(response.headers["X-Request-ID"]) == 32


def test_valid_client_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "mobile-abc-123"})
    assert response.headers["X-Request-ID"] == "mobile-abc-123"


def test_oversized_client_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "x" * 500})
    assert response.headers["X-Request-ID"] != "x" * 500


def test_openapi_is_served_under_api_prefix(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/health/ready" in response.json()["paths"]



def test_security_headers_on_every_response(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in response.headers  # local/test: no HTTPS


def test_oversized_request_is_refused_before_reading_it(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        content=b"x" * (1_048_576 + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_production_hides_docs_and_enables_hsts() -> None:
    with TestClient(create_app(make_settings(environment="production"))) as client:
        assert client.get("/api/v1/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 404
        live = client.get("/api/v1/health/live")
        assert live.headers["Strict-Transport-Security"].startswith("max-age=31536000")
