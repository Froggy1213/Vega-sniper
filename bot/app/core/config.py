import re
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# bot/app/core/config.py → project root is three levels up
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"

# Telegram bot tokens have the format: <bot_id>:<alphanumeric_hash>
_BOT_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")


def _validate_bot_token(value: str) -> str:
    if not isinstance(value, str) or not _BOT_TOKEN_RE.match(value.strip()):
        raise ValueError(
            "BOT_TOKEN must match the Telegram format: <bot_id>:<hash> "
            "(e.g. 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-0123456). "
            "Get one from @BotFather: https://t.me/BotFather"
        )
    return value.strip()


def _validate_admin_id(value: int) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(
            "ADMIN_ID must be a positive integer (your Telegram user ID). "
            "Get yours from @getmyid_bot: https://t.me/getmyid_bot"
        )
    return value


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

    @field_validator("bot_token")
    @classmethod
    def _validate_bot_token(cls, v: str) -> str:
        return _validate_bot_token(v)

    @field_validator("admin_id")
    @classmethod
    def _validate_admin_id(cls, v: int) -> int:
        return _validate_admin_id(v)


settings = Settings()
