"""One error shape for every failure: {"error": {"code", "message", "details"?, "request_id"?}}."""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AuthenticationError, DomainError, RateLimitedError


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    503: "service_unavailable",
}


def _response(
    request: Request,
    status_code: int,
    message: str,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=_STATUS_CODES.get(status_code, "error"),
            message=message,
            details=details,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return JSONResponse(
        status_code=status_code, content=body.model_dump(exclude_none=True), headers=headers
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - registration guarantees it
        raise exc
    return _response(request, exc.status_code, str(exc.detail), headers=exc.headers)


async def _domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):  # pragma: no cover
        raise exc
    headers: dict[str, str] | None = None
    if isinstance(exc, AuthenticationError):
        headers = {"WWW-Authenticate": "Bearer"}
    elif isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(exc.retry_after)}
    return _response(request, exc.status_code, exc.message, headers=headers)


async def _validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    details = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()
    ]
    return _response(request, 422, "Invalid request", details)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals; the request id links the response to server logs.
    return _response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI documentation for error answers, in the shape FastAPI expects."""
    responses: dict[int | str, dict[str, Any]] = {}
    for code in status_codes:
        responses[code] = {"model": ErrorResponse}
    return responses


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_exception_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
