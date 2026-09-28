from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

class EnvSettings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://max:max@postgres:5432/maxapp"
    MAX_BOT_TOKEN: SecretStr = Field(validation_alias="MAX_TOKEN")
    # ключ подписи JWT мини-приложения — только из .env (openssl rand -hex 32); API без него не стартует
    SECRET_KEY: SecretStr = SecretStr("")
    MAX_INIT_DATA_MAX_AGE: int = 86400
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    PROJECT_NAME: str = "max-miniapp"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


ENV = EnvSettings()
