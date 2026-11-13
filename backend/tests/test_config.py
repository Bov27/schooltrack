import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_defaults_match_project_brief() -> None:
    settings = make_settings()
    assert settings.geofence_default_radius_m == 100
    assert settings.gps_max_accuracy_m == 30
    assert settings.location_max_age_s == 30
    assert settings.request_max_age_s == 15
    assert settings.api_v1_prefix == "/api/v1"


@pytest.mark.parametrize(
    "field",
    ["geofence_default_radius_m", "gps_max_accuracy_m", "location_max_age_s", "request_max_age_s"],
)
def test_geolocation_thresholds_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: 0})


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_non_postgres_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(database_url="mysql://user:pw@localhost/db")


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_cors_wildcard_rejected_when_deployed(environment: str) -> None:
    with pytest.raises(ValidationError, match="CORS wildcard"):
        make_settings(environment=environment, cors_origins=["*"])


def test_sql_echo_rejected_when_deployed() -> None:
    with pytest.raises(ValidationError, match="db_echo"):
        make_settings(environment="production", db_echo=True)


def test_cors_wildcard_allowed_locally() -> None:
    assert make_settings(environment="local", cors_origins=["*"]).cors_origins == ["*"]


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="jwt_secret"):
        make_settings(jwt_secret="too-short")


def test_jwt_secret_is_not_exposed_in_repr() -> None:
    settings = make_settings()
    assert settings.jwt_secret.get_secret_value() not in repr(settings)
