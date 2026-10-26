from __future__ import annotations

import logging
from typing import AsyncIterator, List, Optional
from contextvars import Token

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .config import settings
from .database.supabase import SupabaseStoreError, supabase_repository

logger = logging.getLogger("cloudcost_sentinel.auth")

security_scheme = HTTPBearer(auto_error=False)

# Module-level JWKS client — created once per process when AUTH_JWKS_URL is set.
# cache_keys=True uses PyJWT's in-process LRU cache, avoiding per-request JWKS fetches.
_jwks_client: Optional[PyJWKClient] = None


def _get_jwks_client() -> PyJWKClient:
    """Lazily create and cache the PyJWKClient singleton."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = settings.AUTH_JWKS_URL or (
            f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json" if settings.SUPABASE_URL else None
        )
        if not jwks_url:
            raise RuntimeError(
                "AUTH_JWKS_URL is required when AUTH_ENABLED=true. "
                "Set it to your OIDC provider's JWKS endpoint, e.g. "
                "https://cognito-idp.us-east-1.amazonaws.com/<pool_id>/.well-known/jwks.json"
            )
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


class AuthenticatedPrincipal(BaseModel):
    sub: str = Field(description="Subject identifier (e.g. user ID)")
    email: str = Field(description="Verified email or identity")
    roles: List[str] = Field(default_factory=lambda: ["viewer"])
    is_authenticated: bool = Field(default=False, description="True if verified via JWT; False if dev bypass")
    organization_id: Optional[str] = Field(default=None, exclude=True, repr=False)
    access_token: Optional[str] = Field(default=None, exclude=True, repr=False)

    def has_role(self, role: str) -> bool:
        if "admin" in self.roles or "owner" in self.roles:
            return True
        if role == "viewer":
            return bool(set(self.roles) & {"viewer", "reader", "member", "reviewer"})
        if role == "reviewer":
            return bool(set(self.roles) & {"reviewer"})
        return role in self.roles


def get_current_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> AuthenticatedPrincipal:
    """Extract and verify caller principal.

    In development/demo mode with AUTH_ENABLED=False:
      Allows a default developer principal with both viewer & reviewer privileges,
      clearly marked as is_authenticated=False.

      NOTE: This bypass is rejected when ENVIRONMENT=production — the service
      refuses to start in production with AUTH_ENABLED=False (see validate_startup).

    In production mode with AUTH_ENABLED=True:
      Strictly validates Bearer JWT token against configured JWKS / issuer / audience
      using PyJWKClient to fetch the actual RS256 signing key from the OIDC provider.
      Rejects unauthenticated, expired, wrong-issuer, wrong-audience, and forged requests
      with 401 Unauthorized.
    """
    if not settings.AUTH_ENABLED:
        # Development mode bypass. Production startup validation (config.py) ensures
        # AUTH_ENABLED=False is rejected before serving production traffic.
        logger.debug(
            "AUTH_ENABLED=false: issuing development bypass principal. "
            "This mode must never be used in production."
        )
        return AuthenticatedPrincipal(
            sub="dev-lead-engineer",
            email="lead-cloud-engineer@company.internal",
            roles=["viewer", "reviewer", "admin"],
            is_authenticated=False,
        )

    # Auth is enabled — require valid token
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        # Fetch the actual RS256 signing key from the OIDC provider's JWKS endpoint.
        # PyJWKClient uses the token's 'kid' header to select the correct key.
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Validate signature, expiry, issuer, and audience in a single call.
        issuer = settings.AUTH_ISSUER or f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
        audience = settings.AUTH_AUDIENCE or "authenticated"
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=issuer,
            audience=audience,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )

        sub = claims.get("sub", "unknown-user")
        email = claims.get("email", claims.get("preferred_username", sub))

        # Extract roles from standard claim locations: "roles", "groups", "cognito:groups"
        roles: List[str] = []
        if isinstance(claims.get("roles"), list):
            roles.extend(claims["roles"])
        if isinstance(claims.get("groups"), list):
            roles.extend(claims["groups"])
        if isinstance(claims.get("cognito:groups"), list):
            roles.extend(claims["cognito:groups"])
        if not roles:
            roles = ["viewer"]

        return AuthenticatedPrincipal(
            sub=sub,
            email=email,
            roles=roles,
            is_authenticated=True,
            access_token=token,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer.",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience.",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )
    except (jwt.InvalidSignatureError, jwt.DecodeError) as sig_err:
        logger.warning("JWT signature/decode failure (%s).", type(sig_err).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature verification failed.",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )
    except Exception as exc:
        logger.warning("Token verification failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )


async def _resolve_workspace(principal: AuthenticatedPrincipal) -> Optional[Token]:
    if not (principal.is_authenticated and settings.SUPABASE_URL):
        return None
    try:
        scope = await run_in_threadpool(supabase_repository.resolve_scope, principal.sub, principal.access_token or "")
    except SupabaseStoreError as exc:
        code = status.HTTP_403_FORBIDDEN if exc.status_code == 403 else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(code, "Workspace access could not be verified. Try again later.") from None
    principal.organization_id = scope.organization_id
    principal.roles = [scope.role]
    return supabase_repository.set_scope(scope)


async def require_viewer(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AsyncIterator[AuthenticatedPrincipal]:
    """Requires viewer or reviewer role."""
    scope_token = await _resolve_workspace(principal)
    try:
        if not principal.has_role("viewer"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: workspace membership required.")
        yield principal
    finally:
        if scope_token is not None:
            supabase_repository.reset_scope(scope_token)


async def require_reviewer(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AsyncIterator[AuthenticatedPrincipal]:
    """Requires reviewer role (for approving/rejecting remediation items)."""
    scope_token = await _resolve_workspace(principal)
    try:
        if not principal.has_role("reviewer"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: reviewer role required.")
        yield principal
    finally:
        if scope_token is not None:
            supabase_repository.reset_scope(scope_token)
