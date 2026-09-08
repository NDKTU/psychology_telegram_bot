import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env if present
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    """Application configuration settings."""

    CLIENT_BOT_TOKEN: str = os.getenv("CLIENT_BOT_TOKEN", "YOUR_CLIENT_BOT_TOKEN_HERE").strip()
    WORKER_BOT_TOKEN: str = os.getenv("WORKER_BOT_TOKEN", "YOUR_WORKER_BOT_TOKEN_HERE").strip()
    
    # Target chat ID for worker messages (can be a group ID e.g. -100xxx or worker user ID)
    WORKER_CHAT_ID: int = int(os.getenv("WORKER_CHAT_ID", "0"))

    # Passcode for workers to register via private chat (/start <secret>)
    WORKER_SECRET_KEY: str = os.getenv("WORKER_SECRET_KEY", "psychology_worker_secret_2026").strip()

    # SQLite Database location
    # PostgreSQL Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    # SQLite Database location (fallback when DATABASE_URL is not set)
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "bot.db")).strip()

    @property
    def is_postgres(self) -> bool:
        return bool(self.DATABASE_URL and (
            self.DATABASE_URL.startswith("postgresql://") or 
            self.DATABASE_URL.startswith("postgres://")
        ))

    @classmethod
    def is_client_token_configured(cls) -> bool:
        return bool(cls.CLIENT_BOT_TOKEN and "YOUR_CLIENT_BOT_TOKEN" not in cls.CLIENT_BOT_TOKEN)

    @classmethod
    def is_worker_token_configured(cls) -> bool:
        return bool(cls.WORKER_BOT_TOKEN and "YOUR_WORKER_BOT_TOKEN" not in cls.WORKER_BOT_TOKEN)


settings = Settings()

