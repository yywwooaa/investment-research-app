from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings kept intentionally small for a local demo app."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_name: str = "Variant Research Workbench"
    data_source: str = Field(default="snapshot", alias="VRW_DATA_SOURCE")
    bloomberg_host: str = Field(default="localhost", alias="VRW_BLOOMBERG_HOST")
    bloomberg_port: int = Field(default=8194, alias="VRW_BLOOMBERG_PORT")
    fixture_path: Path = Field(
        default=ROOT_DIR / "data" / "fixtures" / "universe.json",
        alias="VRW_FIXTURE_PATH",
    )
    local_data_dir: Path = Field(
        default=ROOT_DIR / "data" / "local",
        alias="VRW_LOCAL_DATA_DIR",
    )
    sqlite_path: Path = Field(
        default=ROOT_DIR / "data" / "local" / "workbench.sqlite3",
        alias="VRW_SQLITE_PATH",
    )
    frontend_dist_dir: Path = Field(
        default=ROOT_DIR / "frontend" / "dist",
        alias="VRW_FRONTEND_DIST_DIR",
    )
    serve_frontend: bool = Field(default=True, alias="VRW_SERVE_FRONTEND")
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="VRW_ALLOWED_ORIGINS",
    )
    auth_require_invite: bool = Field(default=False, alias="VRW_REQUIRE_INVITE")
    invite_code: str = Field(default="", alias="VRW_INVITE_CODE")
    admin_key: str = Field(default="", alias="VRW_ADMIN_KEY")
    auth_session_days: int = Field(default=14, alias="VRW_AUTH_SESSION_DAYS")
    password_reset_minutes: int = Field(default=30, alias="VRW_PASSWORD_RESET_MINUTES")
    public_app_url: str = Field(default="http://127.0.0.1:5173", alias="VRW_PUBLIC_APP_URL")
    smtp_host: str = Field(default="", alias="VRW_SMTP_HOST")
    smtp_port: int = Field(default=465, alias="VRW_SMTP_PORT")
    smtp_username: str = Field(default="", alias="VRW_SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="VRW_SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="VRW_SMTP_FROM")
    smtp_tls: bool = Field(default=True, alias="VRW_SMTP_TLS")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHAVANTAGE_API_KEY")
    alpha_vantage_api_keys: str = Field(default="", alias="ALPHAVANTAGE_API_KEYS")
    alpha_vantage_cache_path: Path = Field(
        default=ROOT_DIR / "data" / "local" / "alpha_vantage_cache.json",
        alias="VRW_ALPHA_VANTAGE_CACHE_PATH",
    )
    company_cache_dir: Path = Field(
        default=ROOT_DIR / "data" / "local" / "company_cache",
        alias="VRW_COMPANY_CACHE_DIR",
    )
    company_cache_ttl_seconds: int = Field(default=60 * 15, alias="VRW_COMPANY_CACHE_TTL_SECONDS")
    lazy_universe_load: bool = Field(default=True, alias="VRW_LAZY_UNIVERSE_LOAD")
    sec_user_agent: str = Field(default="Variant Research Workbench contact@example.com", alias="VRW_SEC_USER_AGENT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
