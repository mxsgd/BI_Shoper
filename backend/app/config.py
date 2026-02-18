from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/bi_shoper"
    sync_database_url: str = ""

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
