from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class EnvSettings(BaseSettings):
    DATABASE_URL: str
    MAX_BOT_TOKEN: SecretStr = Field(validation_alias="MAX_TOKEN")
    POSTGRES_PASSWORD: SecretStr = SecretStr("")
    SECRET_KEY: SecretStr = SecretStr("")
    MAX_INIT_DATA_MAX_AGE: int = 86400
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    DEMO: bool = True
    MSP_FULL_REFRESH: bool = False
    LAW_PDF: bool = False
    PROJECT_NAME: str = "max-miniapp"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


ENV = EnvSettings()
