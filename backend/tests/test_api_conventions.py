from fastapi.testclient import TestClient


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
