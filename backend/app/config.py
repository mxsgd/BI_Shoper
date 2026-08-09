from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:2402@localhost:5432/bi_shoper"
    sync_database_url: str = ""

    ga4_property_id: str = ""
    ga4_credentials_path: str = ""
    ga4_sync_window_days: int = 90

    tracker_remote_database_url: str = ""
    tracker_remote_ssl_insecure: bool = False

    # ------------------------------------------------------------------
    # Shoper App Store (Partner API) integration
    # ------------------------------------------------------------------
    # Master switch. When enabled, required settings below are validated
    # at application startup.
    shoper_appstore_enabled: bool = False
    # Application/client ID from the Shoper developer (Partner) panel.
    shoper_app_id: str = ""
    # App Store secret: HMAC key for lifecycle/iframe signatures AND the
    # OAuth client_secret for the /oauth/token Basic auth.
    shoper_app_secret: str = ""
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt tokens at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    shoper_token_cipher_key: str = ""
    # Secret for signing short-lived iframe app sessions. Falls back to
    # shoper_app_secret when empty.
    shoper_session_secret: str = ""
    # Where the iframe entry endpoint redirects after creating a session.
    shoper_panel_redirect_url: str = "/"
    # Max accepted age of the iframe `timestamp` parameter (seconds).
    shoper_iframe_max_age_seconds: int = 300
    # Lifetime of the app session issued after iframe verification (seconds).
    shoper_session_ttl_seconds: int = 1800
    # Allow plain http / default-port-80 shop URLs (development only).
    shoper_allow_insecure_shop_url: bool = False

    # DEPRECATED: legacy WebAPI login/password auth (POST /auth). Only used
    # when explicitly enabled and only for stores WITHOUT an App Store
    # installation. Will be removed once all stores are migrated.
    shoper_enable_legacy_webapi: bool = False

    @property
    def sync_db_url(self) -> str:
        """Sync URL for Alembic (replace asyncpg with psycopg2)."""
        if self.sync_database_url:
            return self.sync_database_url
        return self.database_url.replace("+asyncpg", "")

    @property
    def session_secret(self) -> str:
        return self.shoper_session_secret or self.shoper_app_secret

    def validate_shoper_appstore(self) -> list[str]:
        """Names (never values) of required-but-missing App Store settings."""
        if not self.shoper_appstore_enabled:
            return []
        missing: list[str] = []
        if not self.shoper_app_id.strip():
            missing.append("SHOPER_APP_ID")
        if not self.shoper_app_secret.strip():
            missing.append("SHOPER_APP_SECRET")
        if not self.shoper_token_cipher_key.strip():
            missing.append("SHOPER_TOKEN_CIPHER_KEY")
        return missing

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
