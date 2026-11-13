import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    InvalidTokenError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from tests.conftest import TEST_JWT_SECRET, make_settings

SETTINGS = make_settings()


class TestPasswords:
    def test_hash_is_argon2id_and_salted(self) -> None:
        first, second = hash_password("s3cret-pass"), hash_password("s3cret-pass")
        assert first.startswith("$argon2id$")
        assert first != second

    def test_verify(self) -> None:
        hashed = hash_password("s3cret-pass")
        assert verify_password("s3cret-pass", hashed)
        assert not verify_password("wrong", hashed)

    def test_missing_or_corrupt_hash_never_verifies(self) -> None:
        assert not verify_password("anything", None)
        assert not verify_password("schooltrack-timing-equaliser", None)
        assert not verify_password("anything", "not-a-hash")


class TestTokens:
    def test_round_trip(self) -> None:
        user_id, family = uuid.uuid4(), uuid.uuid4()
        token, issued = create_token(
            SETTINGS, subject=user_id, token_type="refresh", family_id=family
        )
        claims = decode_token(SETTINGS, token, "refresh")
        assert claims.subject == user_id
        assert claims.family_id == family
        assert claims.token_id == issued.token_id

    def test_access_token_lifetime_comes_from_settings(self) -> None:
        settings = make_settings(access_token_ttl_minutes=5)
        _, claims = create_token(settings, subject=uuid.uuid4(), token_type="access")
        token, _ = create_token(settings, subject=uuid.uuid4(), token_type="access")
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["exp"] - payload["iat"] == 300
        assert claims.family_id is None

    @pytest.mark.parametrize(("issued", "expected"), [("access", "refresh"), ("refresh", "access")])
    def test_token_type_confusion_is_rejected(self, issued: str, expected: str) -> None:
        token, _ = create_token(SETTINGS, subject=uuid.uuid4(), token_type=issued)  # type: ignore
        with pytest.raises(InvalidTokenError):
            decode_token(SETTINGS, token, expected)  # type: ignore[arg-type]

    def test_expired_token_is_rejected(self) -> None:
        token, _ = create_token(
            SETTINGS, subject=uuid.uuid4(), token_type="access", ttl=timedelta(seconds=-1)
        )
        with pytest.raises(InvalidTokenError):
            decode_token(SETTINGS, token, "access")

    def test_token_signed_with_another_secret_is_rejected(self) -> None:
        other = make_settings(jwt_secret="another-secret-that-is-also-long-enough-000")
        token, _ = create_token(other, subject=uuid.uuid4(), token_type="access")
        with pytest.raises(InvalidTokenError):
            decode_token(SETTINGS, token, "access")

    def test_unsigned_alg_none_token_is_rejected(self) -> None:
        payload = {"sub": str(uuid.uuid4()), "typ": "access", "jti": str(uuid.uuid4()),
                   "iat": 1, "exp": 9_999_999_999, "iss": "schooltrack", "aud": "schooltrack-api"}
        token = jwt.encode(payload, key=None, algorithm="none")
        with pytest.raises(InvalidTokenError):
            decode_token(SETTINGS, token, "access")

    def test_wrong_audience_is_rejected(self) -> None:
        payload = {"sub": str(uuid.uuid4()), "typ": "access", "jti": str(uuid.uuid4()),
                   "iat": 1, "exp": 9_999_999_999, "iss": "schooltrack", "aud": "other-service"}
        token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_token(SETTINGS, token, "access")

    @pytest.mark.parametrize("garbage", ["", "abc", "a.b.c"])
    def test_garbage_is_rejected(self, garbage: str) -> None:
        with pytest.raises(InvalidTokenError):
            decode_token(SETTINGS, garbage, "access")
