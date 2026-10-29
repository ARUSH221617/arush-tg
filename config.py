import os
from pathlib import Path
from typing import List, Optional, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    # Telegram
    TELEGRAM_BOT_TOKEN: str = "9006529162:AAGOXEb8Jq_ERM739fsTaHOckEIdTnzFyPc"
    ALLOWED_TELEGRAM_USER_IDS: Union[List[int], str] = []
    TELEGRAM_PROXY: Optional[str] = None

    # 9Router Server
    NINEROUTER_URL: str = "http://localhost:20128"
    NINEROUTER_KEY: Optional[str] = None

    # Configurable Default Models (Changeable in .env)
    AGENT_MODEL: str = "anthropic/claude-3-7-sonnet"
    STT_MODEL: str = "groq/whisper-large-v3-turbo"
    IMAGE_MODEL: str = "black-forest-labs/flux-1-schnell"
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

    # Local paths & integrations
    COMFYUI_URL: str = "http://127.0.0.1:8188"
    VAULT_DATA_DIR: Path = Path(r"d:\arush\arush-tg\data")

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("ALLOWED_TELEGRAM_USER_IDS", mode="before")
    @classmethod
    def parse_allowed_ids(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            clean = v.strip("[]() ")
            if not clean:
                return []
            return [int(x.strip()) for x in clean.split(",") if x.strip()]
        if isinstance(v, (list, tuple)):
            return [int(x) for x in v]
        return []

settings = Settings()

# Ensure data folders exist
settings.VAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
(settings.VAULT_DATA_DIR / "projects").mkdir(parents=True, exist_ok=True)
(settings.VAULT_DATA_DIR / "media").mkdir(parents=True, exist_ok=True)
(settings.VAULT_DATA_DIR / "receipts").mkdir(parents=True, exist_ok=True)
(settings.VAULT_DATA_DIR / "db").mkdir(parents=True, exist_ok=True)
