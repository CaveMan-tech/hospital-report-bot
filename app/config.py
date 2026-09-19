from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    extract_mode: Literal["mock", "llm"] = "mock"   # "llm" = real language model, letters not digits
    openai_model: str = "openai:gpt-5-mini"
    openai_api_key: str = ""
    # gpt-5-mini "thinks" before answering. Minimal keeps a reply near 4s instead of 15 to 20s,
    # with no loss on the evaluation set. A distressed person should not wait on a spinner.
    # Voice notes: off unless switched on. Audio is transcribed and discarded, never stored.
    voice_enabled: bool = False
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    extract_timeout_seconds: float = 15.0   # typical reply is ~4s; past this we degrade, not hang
    openai_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "minimal"
    store: Literal["memory", "postgres"] = "memory"
    database_url: str = ""
    pack: str = "ng-lagos"                 # default pack
    packs: str = "ng-lagos,ke-nairobi"     # every pack this deployment serves
    ref_code_secret: str = "dev-only-secret"
    analyst_password: str = "change-me"
    allow_unverified: bool = False
    demo_mode: bool = True


    # Set automatically by Railway. Used only to decide whether the safety checks below apply.
    railway_environment: str = ""

    def production_problems(self) -> list[str]:
        """Things that must never reach a public deployment. Empty list means good to go."""
        problems = []
        if self.ref_code_secret in ("dev-only-secret", "change-me-to-a-long-random-string") \
                or len(self.ref_code_secret) < 24:
            problems.append("REF_CODE_SECRET must be a long random string (24+ characters)")
        if self.analyst_password in ("change-me", "demo", "") or len(self.analyst_password) < 10:
            problems.append("ANALYST_PASSWORD must be set to something non-default (10+ characters)")
        if self.allow_unverified:
            problems.append("ALLOW_UNVERIFIED must be false: unverified legal text must not reach real people")
        if self.extract_mode == "mock":
            problems.append("EXTRACT_MODE=mock is a keyword stub; set EXTRACT_MODE=llm and OPENAI_API_KEY")
        if self.store == "memory":
            problems.append("STORE=memory loses every report on restart; set STORE=postgres and DATABASE_URL")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
