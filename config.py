import os
from pathlib import Path
from typing import List, Optional, Union

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import field_validator
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


def _parse_int_list(v: Union[List[int], str, None]) -> List[int]:
    if not v:
        return []
    if isinstance(v, str):
        clean = v.strip("[]() ")
        if not clean:
            return []
        return [int(x.strip()) for x in clean.split(",") if x.strip().lstrip("-").isdigit()]
    if isinstance(v, (list, tuple)):
        return [int(x) for x in v]
    return []


def _parse_str_list(v: Union[List[str], str, None], default: List[str]) -> List[str]:
    if not v:
        return default
    if isinstance(v, str):
        clean = v.strip("[]() ")
        if not clean:
            return default
        return [x.strip().strip("'\"") for x in clean.split(",") if x.strip()]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v]
    return default


DEFAULT_REPO_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path(os.getenv("VAULT_DATA_DIR", str(DEFAULT_REPO_DIR / "data")))


if HAS_PYDANTIC:
    class Settings(BaseSettings):
        # 1. Telegram Bot & Userbot
        TELEGRAM_BOT_TOKEN: str = "9006529162:AAGOXEb8Jq_ERM739fsTaHOckEIdTnzFyPc"
        ALLOWED_TELEGRAM_USER_IDS: Union[List[int], str] = []
        TELEGRAM_PROXY: Optional[str] = None
        TELEGRAM_API_ID: Optional[int] = None
        TELEGRAM_API_HASH: Optional[str] = None
        TELEGRAM_FREELANCE_CHANNELS: Union[List[str], str] = [
            "freelancer_ir",
            "python_jobs_ir"
        ]

        # 2. 9Router Gateway
        NINEROUTER_URL: str = "http://localhost:20128"
        NINEROUTER_KEY: Optional[str] = None

        # 3. Configurable Default Models & Agent Controls
        SYSTEM_ONE_MODEL: str = "oc/jev-1.13-free"
        AGENT_MODEL: str = "anthropic/claude-3-7-sonnet"
        AGENT_MAX_TURNS: int = 200
        AGENT_TOOL_REPEAT_LIMIT: int = 3
        STT_MODEL: str = "groq/whisper-large-v3-turbo"
        IMAGE_MODEL: str = "black-forest-labs/flux-1-schnell"
        EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

        # 4. Freelance Radar (Phase 3)
        RADAR_POLL_INTERVAL_SECONDS: int = 600
        RADAR_SYSTEM_ONE_BATCH_SIZE: int = 20
        RADAR_SYSTEM_ONE_THRESHOLD: float = 0.55
        RADAR_MIN_BUDGET_TOMAN: float = 1_000_000.0
        RADAR_CONCURRENT_EVALS: int = 4
        RADAR_ENABLE_GLOBAL_SOURCES: bool = True
        RADAR_GLOBAL_RSS_FEEDS: Union[List[str], str] = [
            "https://remoteok.com/remote-python-jobs.rss",
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss"
        ]
        TELEGRAM_API_ID: Optional[int] = None
        TELEGRAM_API_HASH: Optional[str] = None
        TELEGRAM_SESSION_NAME: str = "arush_radar_session"
        RADAR_CATEGORIES: Union[List[str], str] = [
            "python", "react", "bot", "ai", "web scraping", "telegram", "fastapi", "django", "automation"
        ]
        RADAR_MATCH_THRESHOLD: int = 80
        PORTFOLIO_SUMMARY: str = (
            "Senior Python & Full-Stack AI Engineer specializing in Telegram bots (aiogram/Telethon), "
            "LLM agents, RAG & vector databases, web scraping (Playwright/aiohttp), FastAPI/Django backends, "
            "React dashboards, and Windows automation."
        )

        # 5. Browser & GitHub Automation (Phase 4)
        CHROME_USER_DATA_DIR: Optional[str] = None
        CHROME_PROFILE_NAME: str = "Default"
        BROWSER_HEADLESS: bool = False
        GITHUB_TOKEN: Optional[str] = None
        GITHUB_DEFAULT_REPO: str = "arush221617/arush-tg"

        # 6. Local Integrations & Storage (Phase 5 & 2)
        COMFYUI_URL: str = "http://127.0.0.1:8188"
        VAULT_DATA_DIR: Path = DEFAULT_DATA_DIR

        # 7. Daily Routines & Self-Healing Daemon (Phase 6 & 7)
        TIMEZONE_OFFSET_HOURS: float = 3.5  # Iran Standard Time (IRST UTC+3:30)
        MORNING_BRIEFING_TIME: str = "08:30"
        NIGHTLY_REVIEW_TIME: str = "22:30"
        BACKUP_TIME: str = "03:00"
        BACKUP_RETENTION_DAYS: int = 14
        HEALTHCHECK_PORT: int = 8089
        HEARTBEAT_INTERVAL_SECONDS: int = 60

        model_config = SettingsConfigDict(
            env_file=str(DEFAULT_REPO_DIR / ".env"),
            env_file_encoding="utf-8",
            extra="ignore"
        )

        @field_validator("ALLOWED_TELEGRAM_USER_IDS", mode="before")
        @classmethod
        def parse_allowed_ids(cls, v):
            return _parse_int_list(v)

        @field_validator("RADAR_CATEGORIES", mode="before")
        @classmethod
        def parse_radar_categories(cls, v):
            return _parse_str_list(
                v,
                ["python", "react", "bot", "ai", "web scraping", "telegram", "fastapi", "django", "automation"]
            )

        @field_validator("TELEGRAM_FREELANCE_CHANNELS", mode="before")
        @classmethod
        def parse_freelance_channels(cls, v):
            res = _parse_str_list(v, ["freelancer_ir", "python_jobs_ir"])
            return [c for c in res if c.lstrip("@").lower() not in ("karlancer", "ponisha_ir", "ponisha")]
else:
    class Settings:
        def __init__(self):
            self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9006529162:AAGOXEb8Jq_ERM739fsTaHOckEIdTnzFyPc")
            self.ALLOWED_TELEGRAM_USER_IDS = _parse_int_list(os.getenv("ALLOWED_TELEGRAM_USER_IDS", ""))
            self.TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY") or None
            self.TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID")) if os.getenv("TELEGRAM_API_ID") else None
            self.TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH") or None
            raw_channels = _parse_str_list(
                os.getenv("TELEGRAM_FREELANCE_CHANNELS"),
                ["freelancer_ir", "python_jobs_ir"]
            )
            self.TELEGRAM_FREELANCE_CHANNELS = [
                c for c in raw_channels if c.lstrip("@").lower() not in ("karlancer", "ponisha_ir", "ponisha")
            ]
            self.NINEROUTER_URL = os.getenv("NINEROUTER_URL", "http://localhost:20128")
            self.NINEROUTER_KEY = os.getenv("NINEROUTER_KEY") or None
            self.SYSTEM_ONE_MODEL = os.getenv("SYSTEM_ONE_MODEL", "oc/jev-1.13-free")
            self.AGENT_MODEL = os.getenv("AGENT_MODEL", "anthropic/claude-3-7-sonnet")
            self.AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "200"))
            self.AGENT_TOOL_REPEAT_LIMIT = int(os.getenv("AGENT_TOOL_REPEAT_LIMIT", "3"))
            self.STT_MODEL = os.getenv("STT_MODEL", "groq/whisper-large-v3-turbo")
            self.IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-1-schnell")
            self.EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
            self.RADAR_POLL_INTERVAL_SECONDS = int(os.getenv("RADAR_POLL_INTERVAL_SECONDS", "600"))
            self.RADAR_SYSTEM_ONE_BATCH_SIZE = int(os.getenv("RADAR_SYSTEM_ONE_BATCH_SIZE", "20"))
            self.RADAR_SYSTEM_ONE_THRESHOLD = float(os.getenv("RADAR_SYSTEM_ONE_THRESHOLD", "0.55"))
            self.RADAR_MIN_BUDGET_TOMAN = float(os.getenv("RADAR_MIN_BUDGET_TOMAN", "1000000"))
            self.RADAR_CONCURRENT_EVALS = int(os.getenv("RADAR_CONCURRENT_EVALS", "4"))
            self.RADAR_ENABLE_GLOBAL_SOURCES = os.getenv("RADAR_ENABLE_GLOBAL_SOURCES", "true").lower() == "true"
            self.RADAR_GLOBAL_RSS_FEEDS = _parse_str_list(
                os.getenv("RADAR_GLOBAL_RSS_FEEDS"),
                [
                    "https://remoteok.com/remote-python-jobs.rss",
                    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss"
                ]
            )
            self.TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID")) if os.getenv("TELEGRAM_API_ID") else None
            self.TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH") or None
            self.TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "arush_radar_session")
            self.RADAR_CATEGORIES = _parse_str_list(
                os.getenv("RADAR_CATEGORIES"),
                ["python", "react", "bot", "ai", "web scraping", "telegram", "fastapi", "django", "automation"]
            )
            self.RADAR_MATCH_THRESHOLD = int(os.getenv("RADAR_MATCH_THRESHOLD", "80"))
            self.PORTFOLIO_SUMMARY = os.getenv(
                "PORTFOLIO_SUMMARY",
                "Senior Python & Full-Stack AI Engineer specializing in Telegram bots (aiogram/Telethon), "
                "LLM agents, RAG & vector databases, web scraping (Playwright/aiohttp), FastAPI/Django backends, "
                "React dashboards, and Windows automation."
            )
            self.CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR") or None
            self.CHROME_PROFILE_NAME = os.getenv("CHROME_PROFILE_NAME", "Default")
            self.BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
            self.GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or None
            self.GITHUB_DEFAULT_REPO = os.getenv("GITHUB_DEFAULT_REPO", "arush221617/arush-tg")
            self.COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
            self.VAULT_DATA_DIR = Path(os.getenv("VAULT_DATA_DIR", str(DEFAULT_DATA_DIR)))
            self.TIMEZONE_OFFSET_HOURS = float(os.getenv("TIMEZONE_OFFSET_HOURS", "3.5"))
            self.MORNING_BRIEFING_TIME = os.getenv("MORNING_BRIEFING_TIME", "08:30")
            self.NIGHTLY_REVIEW_TIME = os.getenv("NIGHTLY_REVIEW_TIME", "22:30")
            self.BACKUP_TIME = os.getenv("BACKUP_TIME", "03:00")
            self.BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "14"))
            self.HEALTHCHECK_PORT = int(os.getenv("HEALTHCHECK_PORT", "8089"))
            self.HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60"))


settings = Settings()


def ensure_data_directories(base_dir: Optional[Path] = None) -> None:
    target = base_dir or settings.VAULT_DATA_DIR
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fallback if a Windows path like d:\arush\arush-tg\data is used on Linux/Docker
        fallback = DEFAULT_REPO_DIR / "data"
        settings.VAULT_DATA_DIR = fallback
        target = fallback
        target.mkdir(parents=True, exist_ok=True)

    for sub in ("projects", "media", "receipts", "db", "backups", "downloads", "labs", "skills"):
        (target / sub).mkdir(parents=True, exist_ok=True)


ensure_data_directories()
