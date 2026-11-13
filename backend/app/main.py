"""Application factory."""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
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

    docs = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json" if docs else None,
        docs_url=f"{settings.api_v1_prefix}/docs" if docs else None,
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

    docs_prefix = f"{settings.api_v1_prefix}/docs"
    static_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        # Responses carry personal data: never store them in shared or browser caches.
        "Cache-Control": "no-store",
    }
    if settings.is_deployed:
        static_headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    @app.middleware("http")
    async def security_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        declared = request.headers.get("content-length")
        too_large = declared is not None and (
            not declared.isdigit() or int(declared) > settings.max_request_bytes
        )
        if too_large:
            response: Response = JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "payload_too_large",
                        "message": f"Request body exceeds {settings.max_request_bytes} bytes",
                    }
                },
            )
        else:
            response = await call_next(request)
        response.headers.update(static_headers)
        if not request.url.path.startswith(docs_prefix):
            # JSON API: nothing may be loaded or framed (the Swagger UI needs its CDN assets).
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        return response

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
