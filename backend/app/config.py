from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:2402@localhost:5432/bi_shoper"
    sync_database_url: str = ""

    ga4_property_id: str = ""
    ga4_credentials_path: str = ""
    ga4_sync_window_days: int = 90

    tracker_remote_database_url: str = ""
    tracker_remote_ssl_insecure: bool = False

    @property
    def sync_db_url(self) -> str:
        """Sync URL for Alembic (replace asyncpg with psycopg2)."""
        if self.sync_database_url:
            return self.sync_database_url
        return self.database_url.replace("+asyncpg", "")

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
