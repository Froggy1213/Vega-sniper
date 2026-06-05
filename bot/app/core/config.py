from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# bot/app/core/config.py → project root is three levels up
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    admin_id: int
    rabbitmq_url: str
    database_url: str
    db_echo: bool = False
    premium_stars_price: int = 250
    premium_duration_days: int = 30


settings = Settings()
