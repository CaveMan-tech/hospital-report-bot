from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    extract_mode: str = "mock"
    openai_model: str = "openai:gpt-5-mini"
    store: str = "memory"
    supabase_url: str = ""
    supabase_service_key: str = ""
    pack: str = "ng-lagos"
    ref_code_secret: str = "dev-only-secret"
    analyst_password: str = "change-me"
    allow_unverified: bool = False
    demo_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
