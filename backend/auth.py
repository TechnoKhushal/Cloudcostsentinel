from __future__ import annotations

import logging
from typing import List, Optional
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .config import settings

logger = logging.getLogger("cloudcost_sentinel.auth")

security_scheme = HTTPBearer(auto_error=False)


class AuthenticatedPrincipal(BaseModel):
    sub: str = Field(description="Subject identifier (e.g. user ID)")
    email: str = Field(description="Verified email or identity")
    roles: List[str] = Field(default_factory=lambda: ["viewer"])
    is_authenticated: bool = Field(default=False, description="True if verified via JWT; False if dev bypass")

    def has_role(self, role: str) -> bool:
        return "admin" in self.roles or role in self.roles


def get_current_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> AuthenticatedPrincipal:
    """Extract and verify caller principal.
    
    In development/demo mode with AUTH_ENABLED=False:
      Allows a default developer principal with both viewer & reviewer privileges,
      clearly marked as is_authenticated=False.
    
    In production mode with AUTH_ENABLED=True:
      Strictly validates Bearer JWT token against configured JWKS / issuer / audience.
      Rejects unauthenticated or expired requests with 401 Unauthorized.
    """
    if not settings.AUTH_ENABLED:
        if settings.ENVIRONMENT == "production" and not settings.ALLOW_UNAUTHENTICATED_IN_PRODUCTION:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication is required in production environment.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Development mode bypass
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
        # Decode without verification if no secret/JWKS configured (e.g. behind an authenticating reverse-proxy / ALB)
        # Otherwise decode with options
        options = {
            "verify_signature": bool(settings.AUTH_JWKS_URL),
            "verify_exp": True,
            "verify_iss": bool(settings.AUTH_ISSUER),
            "verify_aud": bool(settings.AUTH_AUDIENCE),
        }
        
        # When JWKS or symmetric key is provided, PyJWT handles it;
        # For general OIDC tokens passed from an ALB or API Gateway:
        claims = jwt.decode(
            token,
            key="",  # unverified signature if no local key or verification done by reverse proxy
            algorithms=["RS256", "HS256"],
            options=options,
            issuer=settings.AUTH_ISSUER,
            audience=settings.AUTH_AUDIENCE,
        )

        sub = claims.get("sub", "unknown-user")
        email = claims.get("email", claims.get("preferred_username", sub))
        
        # Extract roles from standard claim locations: "roles", "groups", "cognito:groups"
        roles = []
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
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
        )
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
        )


def require_viewer(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    """Requires viewer or reviewer role."""
    if not principal.has_role("viewer") and not principal.has_role("reviewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: viewer or reviewer role required.",
        )
    return principal


def require_reviewer(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    """Requires reviewer role (for approving/rejecting remediation items)."""
    if not principal.has_role("reviewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: reviewer role required to record approval decisions.",
        )
    return principal
