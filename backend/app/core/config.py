"""Application settings loaded from environment variables or .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    # Allow overriding the base URL for compatible providers (e.g. Azure, local)
    llm_base_url: str = "https://api.openai.com/v1"
    # Maximum tokens the planner may request in a single LLM call
    llm_max_tokens: int = 512

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
