from __future__ import annotations

import json
import logging
import os
from typing import List, Optional
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

    # Production safeguards
    ALLOW_MOCK_IN_PRODUCTION: bool = Field(
        default_factory=lambda: os.getenv("ALLOW_MOCK_IN_PRODUCTION", "false").lower() in ("true", "1", "yes")
    )

    # Test fixture endpoint — disabled by default; never enable in production
    ENABLE_TEST_FIXTURE_ENDPOINT: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_TEST_FIXTURE_ENDPOINT", "false").lower() in ("true", "1", "yes")
    )

    def validate_startup(self) -> None:
        """Validate startup configuration to prevent unsafe states."""
        if not (0.0 < self.DECIDER_MIN_CONFIDENCE <= 1.0):
            raise ValueError(f"DECIDER_MIN_CONFIDENCE must be between 0.0 and 1.0; got {self.DECIDER_MIN_CONFIDENCE}")

        # 'inprocess' removed — it raises NotImplementedError and must not be allowed.
        allowed_deciders = {"mock", "http"}
        if self.DECIDER_PROVIDER not in allowed_deciders:
            raise ValueError(f"Invalid DECIDER_PROVIDER '{self.DECIDER_PROVIDER}'. Allowed: {sorted(allowed_deciders)}")

        allowed_bedrock = {"mock", "bedrock"}
        if self.BEDROCK_PROVIDER not in allowed_bedrock:
            raise ValueError(f"Invalid BEDROCK_PROVIDER '{self.BEDROCK_PROVIDER}'. Allowed: {allowed_bedrock}")

        if self.ENVIRONMENT == "production":
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Wildcard '*' in CORS_ORIGINS is prohibited in production.")

            # Production requires AUTH_ENABLED=True — the ALLOW_UNAUTHENTICATED_IN_PRODUCTION
            # escape hatch has been removed. There is no override for production auth bypass.
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

            if (self.DECIDER_PROVIDER == "mock" or self.BEDROCK_PROVIDER == "mock") and not self.ALLOW_MOCK_IN_PRODUCTION:
                raise ValueError("Production startup refused: mock providers cannot be used in production without ALLOW_MOCK_IN_PRODUCTION=true.")

            if self.ENABLE_TEST_FIXTURE_ENDPOINT:
                raise ValueError(
                    "Production startup refused: ENABLE_TEST_FIXTURE_ENDPOINT must be false in production. "
                    "The /v1/systemone test fixture must never be active in production."
                )

        if self.DECIDER_PROVIDER == "http":
            # Guard against pointing live HTTP decider to application's own port
            app_port_str = f":{self.PORT}"
            if "127.0.0.1" in self.STRANDS_DECIDER_URL and app_port_str in self.STRANDS_DECIDER_URL:
                raise ValueError(
                    f"STRANDS_DECIDER_URL ({self.STRANDS_DECIDER_URL}) points to the application's own HTTP port {self.PORT}. "
                    "In live HTTP mode, you must connect to an external strands-decider serve process (e.g. port 8080)."
                )


settings = Settings()
