import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv opsiyonel
    pass


def _ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


@dataclass(frozen=True)
class Config:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    allowed_user_ids: set[int] = field(default_factory=lambda: _ids(os.getenv("ALLOWED_USER_IDS", "")))
    check_interval_min: int = int(os.getenv("CHECK_INTERVAL_MIN", "60"))
    max_pages: int = int(os.getenv("MAX_PAGES", "2"))
    request_delay: float = float(os.getenv("REQUEST_DELAY", "4"))
    fetcher: str = os.getenv("FETCHER", "httpx")
    min_drop_ratio: float = float(os.getenv("MIN_DROP_RATIO", "0.01"))
    deal_ratio: float = float(os.getenv("DEAL_RATIO", "0.90"))
    db_path: str = os.getenv("DB_PATH", "asistanbot.db")


config = Config()
