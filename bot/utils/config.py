from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import os


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The dotenv source loads every key in .env, and pydantic-settings
        # defaults to extra="forbid" — so a retired variable left in .env
        # (e.g. STRAVA_CLIENT_ID after the Strava sync was removed) would
        # crash the bot at import. Ignore unknown keys instead.
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str
    telegram_allowed_chat_id: int
    # Ido 2026-10-20: "I am only on WhatsApp". False = no Telegram polling and no
    # Telegram copies of nudges/reports; the scheduler + WhatsApp keep running.
    # The token stays: PTB's Application still needs a valid one to start.
    telegram_enabled: bool = True

    # WhatsApp (via TARS's wa-gateway on the same box; bot/whatsapp/).
    # Off unless WA_TOKEN is set. The gateway routes the "CalTrack" group here.
    wa_token: str = ""
    wa_gateway_url: str = "http://127.0.0.1:8089"
    wa_listen_host: str = "127.0.0.1"
    wa_listen_port: int = 8093

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_vision_model: str = "openai/gpt-4o"
    openrouter_coach_model: str = "anthropic/claude-sonnet-4-5"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Supabase
    supabase_url: str
    supabase_key: str
    supabase_db_password: str = ""

    # App
    user_timezone: str = "Asia/Jerusalem"
    min_calories_male: int = 1500
    min_calories_female: int = 1200
    max_deficit_per_day: int = 1000

    @property
    def allowed_chat_ids(self) -> set[int]:
        return {self.telegram_allowed_chat_id}

    @property
    def wa_enabled(self) -> bool:
        return len(self.wa_token) >= 32


config = Config()
