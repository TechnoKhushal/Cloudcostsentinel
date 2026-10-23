from __future__ import annotations

import json
import logging
import os
from typing import List, Optional
from urllib.parse import urlsplit
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()
logger = logging.getLogger("cloudcost_sentinel.config")


def parse_cors_origins(raw: str) -> List[str]:
    """Safely parse CORS origins from JSON list or comma-separated string."""
    raw = raw.strip()
    if not raw:
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    # Fallback to comma-separated
    cleaned = raw.strip("[]'\"")
    return [item.strip().strip("'\"") for item in cleaned.split(",") if item.strip().strip("'\"")]


class Settings(BaseModel):
    HOST: str = Field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    ENVIRONMENT: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: parse_cors_origins(
            os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        )
    )

    # Authentication & Authorization Settings
    # In development mode, authentication is optional and defaults to simulated dev principal.
    # In production, AUTH_ENABLED defaults to True.
    AUTH_ENABLED: bool = Field(
        default_factory=lambda: os.getenv(
            "AUTH_ENABLED",
            "false" if os.getenv("ENVIRONMENT", "development") != "production" else "true",
        ).lower()
        in ("true", "1", "yes")
    )
    AUTH_ISSUER: Optional[str] = Field(default_factory=lambda: os.getenv("AUTH_ISSUER"))
    AUTH_AUDIENCE: Optional[str] = Field(default_factory=lambda: os.getenv("AUTH_AUDIENCE"))
    AUTH_JWKS_URL: Optional[str] = Field(default_factory=lambda: os.getenv("AUTH_JWKS_URL"))
    # Strands Decider 2B Settings
    DECIDER_PROVIDER: str = Field(default_factory=lambda: os.getenv("DECIDER_PROVIDER", "mock"))
    # Default to port 8080 (the external strands-decider serve instance) to avoid self-referential ambiguity
    STRANDS_DECIDER_URL: str = Field(
        default_factory=lambda: os.getenv("STRANDS_DECIDER_URL", "http://127.0.0.1:8080/v1/systemone")
    )
    DECIDER_MODEL_ID: str = Field(
        default_factory=lambda: os.getenv("DECIDER_MODEL_ID", "StrandsAgents/strands-decider-2B-hobson-v19")
    )
    DECIDER_MIN_CONFIDENCE: float = Field(
        default_factory=lambda: float(os.getenv("DECIDER_MIN_CONFIDENCE", "0.65"))
    )

    # Amazon Bedrock Settings
    BEDROCK_PROVIDER: str = Field(default_factory=lambda: os.getenv("BEDROCK_PROVIDER", "mock"))
    AWS_REGION: str = Field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    BEDROCK_MODEL_ID: str = Field(
        default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    )
    AWS_ACCESS_KEY_ID: str | None = Field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID"))
    AWS_SECRET_ACCESS_KEY: str | None = Field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY"))
    AWS_SESSION_TOKEN: str | None = Field(default_factory=lambda: os.getenv("AWS_SESSION_TOKEN"))

    # AWS Cost Explorer
    AWS_COST_EXPLORER_ENABLED: bool = Field(
        default_factory=lambda: os.getenv("AWS_COST_EXPLORER_ENABLED", "false").lower() in ("true", "1", "yes")
    )
    AWS_COST_EXPLORER_TIMEZONE: str = Field(
        default_factory=lambda: os.getenv("AWS_COST_EXPLORER_TIMEZONE", "UTC")
    )

    # Notification Provider Settings ("disabled" | "mock" | "sns" | "ses")
    NOTIFICATION_PROVIDER: str = Field(
        default_factory=lambda: os.getenv("NOTIFICATION_PROVIDER", "mock")
    )
    NOTIFICATION_SNS_TOPIC_ARN: Optional[str] = Field(
        default_factory=lambda: os.getenv("NOTIFICATION_SNS_TOPIC_ARN")
    )

    # Storage
    DATABASE_PATH: str = Field(default_factory=lambda: os.getenv("DATABASE_PATH", "backend/data/sentinel.db"))
    DATABASE_URL: Optional[str] = Field(default_factory=lambda: os.getenv("DATABASE_URL"))

    # Test fixture endpoint — disabled by default; never enable in production
    ENABLE_TEST_FIXTURE_ENDPOINT: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_TEST_FIXTURE_ENDPOINT", "false").lower() in ("true", "1", "yes")
    )

    def validate_startup(self) -> None:
        """Validate startup configuration to prevent unsafe states."""
        if self.ENVIRONMENT not in {"development", "demo", "production"}:
            raise ValueError("ENVIRONMENT must be development, demo, or production.")
        if self.ENVIRONMENT == "development" and os.getenv("RENDER"):
            raise ValueError("Render deployment must explicitly select ENVIRONMENT=demo or ENVIRONMENT=production.")
        if os.getenv("RENDER") and self.HOST != "0.0.0.0":
            raise ValueError("Render deployment requires HOST=0.0.0.0.")
        if not (0.0 < self.DECIDER_MIN_CONFIDENCE <= 1.0):
            raise ValueError(f"DECIDER_MIN_CONFIDENCE must be between 0.0 and 1.0; got {self.DECIDER_MIN_CONFIDENCE}")

        # 'inprocess' removed — it raises NotImplementedError and must not be allowed.
        allowed_deciders = {"mock", "http"}
        if self.DECIDER_PROVIDER not in allowed_deciders:
            raise ValueError(f"Invalid DECIDER_PROVIDER '{self.DECIDER_PROVIDER}'. Allowed: {sorted(allowed_deciders)}")

        allowed_bedrock = {"mock", "bedrock"}
        if self.BEDROCK_PROVIDER not in allowed_bedrock:
            raise ValueError(f"Invalid BEDROCK_PROVIDER '{self.BEDROCK_PROVIDER}'. Allowed: {allowed_bedrock}")

        if self.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL is not supported by the current SQLite repository. "
                "Remove it or implement PostgreSQL support before configuring it."
            )

        if self.ENVIRONMENT == "production":
            if self.ENABLE_TEST_FIXTURE_ENDPOINT:
                raise ValueError(
                    "Production startup refused: ENABLE_TEST_FIXTURE_ENDPOINT must be false in production. "
                    "The /v1/systemone test fixture must never be active in production."
                )
            self._validate_public_origins()

            # Production requires validated OIDC authentication. There is no bypass.
            if not self.AUTH_ENABLED:
                raise ValueError(
                    "Production startup refused: AUTH_ENABLED must be True in production. "
                    "Configure AUTH_JWKS_URL, AUTH_ISSUER, and AUTH_AUDIENCE."
                )

            if self.AUTH_ENABLED:
                # Validate full OIDC configuration when auth is enabled
                missing = []
                if not self.AUTH_JWKS_URL:
                    missing.append("AUTH_JWKS_URL")
                if not self.AUTH_ISSUER:
                    missing.append("AUTH_ISSUER")
                if not self.AUTH_AUDIENCE:
                    missing.append("AUTH_AUDIENCE")
                if missing:
                    raise ValueError(
                        f"AUTH_ENABLED=true requires these environment variables to be set: {missing}"
                    )
                issuer = urlsplit(self.AUTH_ISSUER or "")
                jwks = urlsplit(self.AUTH_JWKS_URL or "")
                if issuer.scheme != "https" or not issuer.netloc or jwks.scheme != "https" or not jwks.netloc:
                    raise ValueError("Production OIDC issuer and JWKS URL must be valid HTTPS URLs.")

            if self.DECIDER_PROVIDER == "mock" or self.BEDROCK_PROVIDER == "mock":
                raise ValueError(
                    "Production startup refused: mock providers are prohibited; use ENVIRONMENT=demo for simulated providers."
                )

            if self.DATABASE_PATH == "backend/data/sentinel.db" or not os.path.isabs(self.DATABASE_PATH):
                raise ValueError(
                    "Production startup requires DATABASE_PATH to be an explicit absolute path on a persistent disk."
                )

        if self.ENVIRONMENT == "demo":
            self._validate_public_origins()
            if self.AUTH_ENABLED:
                raise ValueError("ENVIRONMENT=demo is unauthenticated by design; set AUTH_ENABLED=false.")
            if self.DECIDER_PROVIDER != "mock" or self.BEDROCK_PROVIDER != "mock":
                raise ValueError("ENVIRONMENT=demo requires DECIDER_PROVIDER=mock and BEDROCK_PROVIDER=mock.")
            if self.AWS_COST_EXPLORER_ENABLED:
                raise ValueError("ENVIRONMENT=demo prohibits live AWS Cost Explorer access.")
            if self.NOTIFICATION_PROVIDER not in {"disabled", "mock"}:
                raise ValueError("ENVIRONMENT=demo allows only disabled or simulated notifications.")
            if self.ENABLE_TEST_FIXTURE_ENDPOINT:
                raise ValueError("ENVIRONMENT=demo must not enable the Decider test-fixture endpoint.")
            if os.getenv("RENDER") and (
                self.DATABASE_PATH == "backend/data/sentinel.db" or not os.path.isabs(self.DATABASE_PATH)
            ):
                raise ValueError("Render demo requires DATABASE_PATH on an explicitly mounted persistent disk.")

        if self.DECIDER_PROVIDER == "http":
            decider_url = urlsplit(self.STRANDS_DECIDER_URL)
            if (
                decider_url.scheme not in {"http", "https"}
                or not decider_url.netloc
                or decider_url.username
                or decider_url.password
            ):
                raise ValueError("STRANDS_DECIDER_URL must be a valid HTTP(S) URL without embedded credentials.")
            # Guard against pointing live HTTP decider to application's own port
            app_port_str = f":{self.PORT}"
            if "127.0.0.1" in self.STRANDS_DECIDER_URL and app_port_str in self.STRANDS_DECIDER_URL:
                raise ValueError(
                    f"STRANDS_DECIDER_URL ({self.STRANDS_DECIDER_URL}) points to the application's own HTTP port {self.PORT}. "
                    "In live HTTP mode, you must connect to an external strands-decider serve process (e.g. port 8080)."
                )

    def _validate_public_origins(self) -> None:
        if not self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS must contain the exact HTTPS frontend origin(s).")
        for origin in self.CORS_ORIGINS:
            parsed = urlsplit(origin)
            if origin == "*":
                raise ValueError("Wildcard '*' in public CORS_ORIGINS is prohibited.")
            is_local_demo_origin = (
                self.ENVIRONMENT == "demo"
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1"}
            )
            if (
                (parsed.scheme != "https" and not is_local_demo_origin)
                or not parsed.netloc
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Public CORS_ORIGINS must contain exact HTTPS origins without paths or credentials.")


settings = Settings()
