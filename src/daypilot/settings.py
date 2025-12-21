from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str
    opencage_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings()
