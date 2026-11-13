"""Application factory."""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app import __version__
from app.api.errors import register_error_handlers
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.infrastructure.database import Database
from app.infrastructure.rate_limit import LoginRateLimiter

REQUEST_ID_HEADER = "X-Request-ID"


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings: Settings = app_settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The engine connects lazily; creating it here does not require the DB to be up.
        app.state.database = Database(settings)
        redis = Redis.from_url(settings.redis_url) if settings.redis_url else None
        app.state.login_limiter = LoginRateLimiter(
            redis, max_attempts=settings.login_max_attempts, window_s=settings.login_window_s
        )
        try:
            yield
        finally:
            await app.state.database.dispose()
            if redis is not None:
                await redis.aclose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Accept a client id only if it is short and printable, otherwise generate one.
        request_id = incoming if 0 < len(incoming) <= 64 and incoming.isprintable() else None
        request.state.request_id = request_id or uuid.uuid4().hex
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn --factory app.main:app_factory`."""
    return create_app()
