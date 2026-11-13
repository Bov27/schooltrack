"""Liveness and readiness endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.core.config import Settings
from app.infrastructure.database import Database

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class DatabaseCheck(BaseModel):
    reachable: bool
    postgis_version: str | None = None
    rls_enforced: bool | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: DatabaseCheck


def get_database(request: Request) -> Database:
    db: Database = request.app.state.database
    return db


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """The process is up. Does not touch dependencies."""
    return LiveResponse()


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse}},
)
async def ready(
    response: Response,
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_app_settings),
) -> ReadyResponse:
    """Database reachable, PostGIS installed, and, in deployed environments,
    the API connected with a role that cannot bypass Row-Level Security."""
    probe = await database.probe()
    rls_enforced = None if probe.role_bypasses_rls is None else not probe.role_bypasses_rls

    is_ready = probe.reachable and probe.postgis_version is not None
    if settings.is_deployed and rls_enforced is not True:
        is_ready = False

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        database=DatabaseCheck(
            reachable=probe.reachable,
            postgis_version=probe.postgis_version,
            rls_enforced=rls_enforced,
        ),
    )
