import uuid
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt import PyJWKClient

from app.core.config import Settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID  # the JWT 'sub' claim
    email: Optional[str]
    claims: dict


class TokenError(Exception):
    pass


class SupabaseJWTVerifier:
    """Verifies Supabase-issued access tokens. Prefers asymmetric ES256/RS256
    via the project's JWKS endpoint (Supabase's current default); falls back
    to the legacy HS256 shared secret when SUPABASE_JWT_SECRET is configured."""

    def __init__(self, settings: Settings) -> None:
        self._issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
        self._audience = settings.SUPABASE_JWT_AUDIENCE
        self._secret = settings.SUPABASE_JWT_SECRET
        self._jwks: Optional[PyJWKClient] = (
            None
            if self._secret
            else PyJWKClient(
                f"{self._issuer}/.well-known/jwks.json",
                cache_keys=True,
                lifespan=600,
                max_cached_keys=8,
            )
        )

    def warmup(self) -> None:
        """Called once from the FastAPI lifespan so the first real request
        doesn't pay for a synchronous JWKS fetch."""
        if self._jwks is not None:
            try:
                self._jwks.fetch_data()
            except Exception:
                pass  # non-fatal — verify() will retry per-request

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            if self._secret:
                claims = jwt.decode(
                    token,
                    self._secret,
                    algorithms=["HS256"],
                    audience=self._audience,
                    issuer=self._issuer,
                )
            else:
                assert self._jwks is not None
                signing_key = self._jwks.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256", "RS256"],
                    audience=self._audience,
                    issuer=self._issuer,
                )
        except jwt.PyJWTError as e:
            raise TokenError(str(e)) from e

        sub = claims.get("sub")
        try:
            user_id = uuid.UUID(str(sub))
        except (ValueError, TypeError) as e:
            raise TokenError(f"invalid or missing 'sub' claim: {sub!r}") from e

        return AuthenticatedUser(id=user_id, email=claims.get("email"), claims=claims)
