from fastapi.testclient import TestClient

from app.infrastructure.database import DatabaseProbe
from app.main import create_app
from tests.conftest import make_settings, use_fake_database

HEALTHY = DatabaseProbe(
    reachable=True, postgis_version="3.4.3", role="schooltrack_app", role_bypasses_rls=False
)


def test_live_does_not_need_the_database(client: TestClient) -> None:
    use_fake_database(client, DatabaseProbe(reachable=False, error="OperationalError"))
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_database_and_postgis_are_available(client: TestClient) -> None:
    use_fake_database(client, HEALTHY)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": {"reachable": True, "postgis_version": "3.4.3", "rls_enforced": True},
    }


def test_not_ready_when_database_unreachable(client: TestClient) -> None:
    use_fake_database(client, DatabaseProbe(reachable=False, error="OperationalError"))
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database"]["reachable"] is False
    assert "error" not in body["database"], "internal error details must not be exposed"


def test_not_ready_without_postgis(client: TestClient) -> None:
    use_fake_database(
        client,
        DatabaseProbe(reachable=True, postgis_version=None, role="x", role_bypasses_rls=False),
    )
    assert client.get("/api/v1/health/ready").status_code == 503


def test_role_that_bypasses_rls_is_tolerated_locally_but_reported(client: TestClient) -> None:
    use_fake_database(
        client,
        DatabaseProbe(
            reachable=True, postgis_version="3.4.3", role="postgres", role_bypasses_rls=True
        ),
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["database"]["rls_enforced"] is False


def test_role_that_bypasses_rls_fails_readiness_in_production() -> None:
    app = create_app(make_settings(environment="production"))
    with TestClient(app) as client:
        use_fake_database(
            client,
            DatabaseProbe(
                reachable=True, postgis_version="3.4.3", role="postgres", role_bypasses_rls=True
            ),
        )
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
