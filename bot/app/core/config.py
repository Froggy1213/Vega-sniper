from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8")

    bot_token: str
    admin_id: int
    rabbitmq_url: str
    database_url: str
    db_echo: bool = False


settings = Settings()
