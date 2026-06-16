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


@lru_cache
def get_settings() -> Settings:
    return Settings()
