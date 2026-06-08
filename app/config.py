from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FastAPI Booking"
    api_key: str = "change-me"
    database_url: str = (
        "mysql+aiomysql://booking_user:booking_password@127.0.0.1:3306/booking_db"
    )
    upload_dir: str = "uploads"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
