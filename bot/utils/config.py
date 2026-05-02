from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import os


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    telegram_bot_token: str
    telegram_allowed_chat_id: int

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_vision_model: str = "openai/gpt-4o"
    openrouter_coach_model: str = "anthropic/claude-sonnet-4-5"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Supabase
    supabase_url: str
    supabase_key: str
    supabase_db_password: str = ""

    # Strava (Stage 2)
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_refresh_token: str = ""

    # App
    user_timezone: str = "Asia/Jerusalem"
    min_calories_male: int = 1500
    min_calories_female: int = 1200
    max_deficit_per_day: int = 1000

    @property
    def allowed_chat_ids(self) -> set[int]:
        return {self.telegram_allowed_chat_id}


config = Config()
