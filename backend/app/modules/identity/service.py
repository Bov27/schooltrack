"""Authentication: login, refresh-token rotation with reuse detection, logout."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.core.security import (
    InvalidTokenError,
    create_token,
    decode_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.modules.identity.models import (
    Device,
    DevicePlatform,
    DeviceStatus,
    PlatformAdmin,
    RefreshToken,
    User,
)

INVALID_CREDENTIALS = "Invalid email or password"
INVALID_REFRESH = "Invalid or expired refresh token"


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


class IdentityService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.session.scalar(select(User).where(User.email == normalize_email(email)))
        # verify_password runs even when the user is missing (uniform timing).
        valid = verify_password(password, user.password_hash if user else None)
        if user is None or not valid or not user.is_active:
            raise AuthenticationError(INVALID_CREDENTIALS)

        if user.password_hash and password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = datetime.now(UTC)
        pair = await self._issue_pair(user.id, family_id=uuid.uuid4())
        await self.session.commit()
        return pair

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            claims = decode_token(self.settings, refresh_token, "refresh")
        except InvalidTokenError as exc:
            raise AuthenticationError(INVALID_REFRESH) from exc

        stored = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.id == claims.token_id).with_for_update()
        )
        if stored is None or stored.user_id != claims.subject:
            raise AuthenticationError(INVALID_REFRESH)

        if stored.revoked_at is not None:
            # A rotated (or logged-out) token was presented again: it may have been stolen.
            # Revoke every token of this login so neither party can continue.
            await self._revoke_family(stored.family_id)
            await self.session.commit()
            raise AuthenticationError(INVALID_REFRESH)

        user = await self.session.get(User, stored.user_id)
        if user is None or not user.is_active or stored.expires_at <= datetime.now(UTC):
            raise AuthenticationError(INVALID_REFRESH)

        pair = await self._issue_pair(user.id, family_id=stored.family_id, replaces=stored)
        await self.session.commit()
        return pair

    async def logout(self, refresh_token: str) -> None:
        """Revoke the whole login (token family). Unknown or invalid tokens are ignored,
        so logout never reveals whether a token was valid."""
        try:
            claims = decode_token(self.settings, refresh_token, "refresh")
        except InvalidTokenError:
            return
        stored = await self.session.get(RefreshToken, claims.token_id)
        if stored is not None and stored.user_id == claims.subject:
            await self._revoke_family(stored.family_id)
            await self.session.commit()

    async def is_platform_admin(self, user_id: uuid.UUID) -> bool:
        return await self.session.get(PlatformAdmin, user_id) is not None

    async def find_user_id_by_email(self, email: str) -> uuid.UUID | None:
        user_id: uuid.UUID | None = await self.session.scalar(
            select(User.id).where(User.email == normalize_email(email), User.is_active.is_(True))
        )
        return user_id

    async def get_active_user(self, user_id: uuid.UUID) -> User | None:
        user = await self.session.get(User, user_id)
        return user if user is not None and user.is_active else None

    # ---- devices ------------------------------------------------------------------
    async def register_device(
        self,
        user_id: uuid.UUID,
        *,
        installation_id: str,
        platform: DevicePlatform,
        model: str | None,
        app_version: str | None,
    ) -> Device:
        """Idempotent per (user, installation): re-registering updates the metadata.
        A revoked device stays revoked; only an administrator could restore it."""
        now = datetime.now(UTC)
        await self.session.execute(
            pg_insert(Device)
            .values(
                user_id=user_id,
                installation_id=installation_id,
                platform=platform,
                model=model,
                app_version=app_version,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "installation_id"],
                set_={"model": model, "app_version": app_version, "last_seen_at": now},
            )
        )
        device = await self.session.scalar(
            select(Device).where(
                Device.user_id == user_id, Device.installation_id == installation_id
            )
        )
        await self.session.commit()
        if device is None:  # pragma: no cover - the upsert guarantees a row
            raise AuthenticationError("Device registration failed")
        return device

    async def list_devices(self, user_id: uuid.UUID) -> list[Device]:
        result = await self.session.scalars(
            select(Device).where(Device.user_id == user_id).order_by(Device.registered_at)
        )
        return list(result)

    async def active_device(self, user_id: uuid.UUID, device_id: uuid.UUID) -> Device | None:
        return await self.session.scalar(
            select(Device).where(
                Device.id == device_id,
                Device.user_id == user_id,
                Device.status == DeviceStatus.ACTIVE,
            )
        )

    async def _issue_pair(
        self, user_id: uuid.UUID, *, family_id: uuid.UUID, replaces: RefreshToken | None = None
    ) -> TokenPair:
        # token_type is the token kind, not a secret (S106 false positive).
        access, access_claims = create_token(
            self.settings, subject=user_id, token_type="access"  # noqa: S106
        )
        refresh, refresh_claims = create_token(
            self.settings,
            subject=user_id,
            token_type="refresh",  # noqa: S106
            family_id=family_id,
        )
        self.session.add(
            RefreshToken(
                id=refresh_claims.token_id,
                user_id=user_id,
                family_id=family_id,
                expires_at=refresh_claims.expires_at,
            )
        )
        if replaces is not None:
            await self.session.flush()  # the new row must exist before it is referenced
            replaces.revoked_at = datetime.now(UTC)
            replaces.replaced_by = refresh_claims.token_id
        expires_in = int((access_claims.expires_at - datetime.now(UTC)).total_seconds())
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=expires_in)

    async def _revoke_family(self, family_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
