"""Password hashing (Argon2id) and JWT access/refresh tokens."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

TokenType = Literal["access", "refresh"]
_ALGORITHM = "HS256"

# argon2-cffi defaults follow the RFC 9106 low-memory Argon2id profile.
_hasher = PasswordHasher()
# Verifying against this when the user does not exist keeps login timing uniform,
# so response time does not reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("schooltrack-timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        matches = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return matches and password_hash is not None


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


class InvalidTokenError(Exception):
    """The token is malformed, expired, has a bad signature or is of the wrong type."""


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: uuid.UUID
    token_type: TokenType
    token_id: uuid.UUID
    expires_at: datetime
    family_id: uuid.UUID | None = None


def create_token(
    settings: Settings,
    *,
    subject: uuid.UUID,
    token_type: TokenType,
    family_id: uuid.UUID | None = None,
    now: datetime | None = None,
    ttl: timedelta | None = None,
) -> tuple[str, TokenClaims]:
    issued_at = now or datetime.now(UTC)
    if ttl is None:
        ttl = (
            timedelta(minutes=settings.access_token_ttl_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_ttl_days)
        )
    claims = TokenClaims(
        subject=subject,
        token_type=token_type,
        token_id=uuid.uuid4(),
        expires_at=issued_at + ttl,
        family_id=family_id,
    )
    payload: dict[str, object] = {
        "sub": str(subject),
        "typ": token_type,
        "jti": str(claims.token_id),
        "iat": int(issued_at.timestamp()),
        "exp": int(claims.expires_at.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    if family_id is not None:
        payload["fam"] = str(family_id)
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)
    return token, claims


def decode_token(settings: Settings, token: str, expected_type: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[_ALGORITHM],  # never trust the token's own "alg" header
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "typ", "jti", "exp", "iat", "iss", "aud"]},
        )
        if payload["typ"] != expected_type:
            raise InvalidTokenError(f"expected a {expected_type} token")
        family = payload.get("fam")
        return TokenClaims(
            subject=uuid.UUID(payload["sub"]),
            token_type=expected_type,
            token_id=uuid.UUID(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            family_id=uuid.UUID(family) if family else None,
        )
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise InvalidTokenError(str(exc)) from exc
