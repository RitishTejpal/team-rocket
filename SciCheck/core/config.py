from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    groq_api_key: str
    groq_model_name: str = "llama-3.1-8b-instant" 
    
@lru_cache
def get_settings() -> Settings:
    return Settings()