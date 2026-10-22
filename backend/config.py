from __future__ import annotations

import os
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Settings(BaseModel):
    HOST: str = Field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    ENVIRONMENT: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if origin.strip()
        ]
    )

    # Strands Decider 2B Settings
    DECIDER_PROVIDER: str = Field(default_factory=lambda: os.getenv("DECIDER_PROVIDER", "mock"))
    STRANDS_DECIDER_URL: str = Field(
        default_factory=lambda: os.getenv("STRANDS_DECIDER_URL", "http://127.0.0.1:8000/v1/systemone")
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

    # Storage
    DATABASE_PATH: str = Field(default_factory=lambda: os.getenv("DATABASE_PATH", "backend/data/sentinel.db"))


settings = Settings()
