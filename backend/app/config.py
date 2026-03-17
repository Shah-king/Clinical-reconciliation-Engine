"""Application configuration using environment variables."""

import logging
import os
from functools import lru_cache

# Load .env file before any os.getenv() call.
# dotenv is a no-op when variables are already set (e.g. in CI/production).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment

_INSECURE_DEFAULT_KEY = "dev-key-change-in-production"

logger = logging.getLogger(__name__)


class Settings:
    """Central configuration object. All values come from environment."""

    # API
    app_title: str = "Clinical Reconciliation Engine"
    app_version: str = "1.0.0"
    api_prefix: str = "/api"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Authentication
    api_key: str = os.getenv("API_KEY", _INSECURE_DEFAULT_KEY)

    # Gemini (Google AI Studio — free tier available at aistudio.google.com)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    llm_retry_attempts: int = int(os.getenv("LLM_RETRY_ATTEMPTS", "3"))
    llm_retry_delay: float = float(os.getenv("LLM_RETRY_DELAY", "1.0"))

    # Cache
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", str(24 * 3600)))

    # CORS — comma-separated list of allowed origins
    cors_origins: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Rate limiting (requests per minute per API key)
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    rate_limit_burst: int = int(os.getenv("RATE_LIMIT_BURST", "10"))


def _validate_settings(s: Settings) -> None:
    """Warn loudly about insecure defaults at startup."""
    if s.api_key == _INSECURE_DEFAULT_KEY:
        logger.warning(
            "SECURITY WARNING: API_KEY is set to the insecure default value. "
            "Set a strong random value in your .env file before deploying."
        )
    if not s.gemini_api_key:
        logger.warning(
            "GEMINI_API_KEY is not set — LLM reasoning will be unavailable. "
            "Get a free key at https://aistudio.google.com/apikey and set it in .env."
        )
    if s.debug:
        logger.warning("DEBUG mode is ON — disable in production (DEBUG=false).")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton settings instance."""
    s = Settings()
    _validate_settings(s)
    return s
