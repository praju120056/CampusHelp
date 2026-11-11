"""App configuration, read from environment variables / .env (see .env.example)."""
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

# Private-network origins (laptop + phones on the same Wi-Fi).
LAN_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'educrew.db').as_posix()}"
    jwt_secret: str = ""
    jwt_expire_hours: int = 12
    bcrypt_rounds: int = 12

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.7-flash"
    gemini_timeout_seconds: float = 8.0

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    public_base_url: str = "http://localhost:3000"
    # Testing: when set, every email goes to this one address instead of the real recipient.
    demo_email_to: str = ""
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = LAN_ORIGIN_REGEX

    demo_mode: bool = False
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 10
    upload_dir: str = str(BACKEND_DIR / "uploads")
    max_upload_mb: int = 5

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def jwt_secret() -> str:
    """JWT signing key: from JWT_SECRET, else a random key kept in backend/.secret_key (gitignored)."""
    configured = get_settings().jwt_secret
    if configured and configured != "change-me":
        return configured
    path = BACKEND_DIR / ".secret_key"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    return key
