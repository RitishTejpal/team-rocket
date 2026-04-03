from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # Generation
    groq_api_key: str
    groq_model_name: str = "llama-3.1-8b-instant" 

    # Inference Script
    hf_token: str
    model_name: str = "openai/gpt-oss-120b"
    api_base_url: str = "https://router.huggingface.co/v1"

    
@lru_cache
def get_settings() -> Settings:
    return Settings()