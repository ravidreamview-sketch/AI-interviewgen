import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    PROJECT_NAME: str = "Agentic AI-Powered Adaptive Learning & Career-Readiness Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment Configuration
    ENV: str = Field(default="development", description="Runtime environment: development | staging | production")
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    
    # Database
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="SQLAlchemy Database URL. If None in development, falls back to SQLite."
    )
    
    # Security & JWT
    ADMIN_JWT_SECRET: Optional[str] = Field(
        default=None,
        description="Cryptographic secret used to sign session tokens. Mandatory in production."
    )
    ADMIN_TOKEN_EXPIRE_MINUTES: int = Field(
        default=480,
        description="Token expiration duration in minutes (default 8 hours)"
    )
    
    # Bootstrap Super Admin credentials
    SUPER_ADMIN_EMAIL: str = "admin@example.com"
    SUPER_ADMIN_PASSWORD: Optional[str] = None
    
    # CORS Allowed Origins
    ADMIN_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000"
    
    # AI Provider API Keys
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    
    # Development auth bypass (Strictly disabled in production)
    DEV_AUTH_BYPASS: bool = False

    @field_validator("ADMIN_JWT_SECRET")
    @classmethod
    def validate_jwt_secret_in_production(cls, v: Optional[str], info) -> Optional[str]:
        env_val = os.environ.get("ENV", "development").lower().strip()
        if env_val in ("production", "prod"):
            if not v or len(v.strip()) < 32:
                raise ValueError(
                    "Production security violation: ADMIN_JWT_SECRET must be set and contain at least 32 random characters. "
                    "Insecure fallback secrets are strictly prohibited."
                )
        return v

    @property
    def is_production(self) -> bool:
        return self.ENV.lower().strip() in ("production", "prod")

    @property
    def cors_origins(self) -> List[str]:
        origins = [o.strip() for o in self.ADMIN_ALLOWED_ORIGINS.split(",") if o.strip()]
        if not origins:
            return ["http://localhost:8000", "http://127.0.0.1:8000"]
        return origins

    @property
    def resolved_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL.strip().strip("'").strip('"')
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+psycopg2://", 1)
            if url.startswith("postgresql://") and "+psycopg2" not in url:
                return url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url
        if self.is_production:
            raise RuntimeError("Production deployment requires a valid PostgreSQL DATABASE_URL. None was provided.")
        return "sqlite:///./interview.db"


settings = Settings()
