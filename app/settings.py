from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv


# Ensure local .env always applies for this process (helpful during development).
# If you want env vars to win over .env, set them after process start or remove .env.
load_dotenv(override=True)


def _env(key: str, default: str | None = None) -> str | None:
    val = getenv(key)
    return val if val not in (None, "") else default


def _env_allow_empty(key: str, default: str | None = None) -> str | None:
    """
    Like _env, but preserves empty string if explicitly provided.
    Useful for things like auth prefix (can be intentionally empty).
    """
    val = getenv(key)
    return default if val is None else val


@dataclass(frozen=True)
class Settings:
    # App
    app_name: str = _env("APP_NAME", "Telegram Bot AI Integrator") or "Telegram Bot AI Integrator"
    host: str = _env("HOST", "0.0.0.0") or "0.0.0.0"
    port: int = int(_env("PORT", "8080") or "8080")

    # Security (UI)
    secret_key: str = _env("SECRET_KEY", "dev-secret-change-me") or "dev-secret-change-me"
    admin_username: str = _env("ADMIN_USERNAME", "admin") or "admin"
    admin_password: str = _env("ADMIN_PASSWORD", "admin") or "admin"

    # Database
    database_url: str = _env("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db") or "sqlite+aiosqlite:///./data/app.db"

    # LLM (OpenAI-compatible)
    llm_base_url: str = _env("LLM_BASE_URL", "https://api.openai.com") or "https://api.openai.com"
    llm_api_key: str | None = _env("LLM_API_KEY", None)
    llm_default_model: str = _env("LLM_DEFAULT_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    llm_auth_header: str = _env("LLM_AUTH_HEADER", "Authorization") or "Authorization"
    # Use "none"/"null" to disable prefix.
    llm_auth_prefix: str | None = (
        None
        if (_env_allow_empty("LLM_AUTH_PREFIX", "Bearer") or "Bearer").lower() in ("none", "null", "")
        else (_env_allow_empty("LLM_AUTH_PREFIX", "Bearer") or "Bearer")
    )

    # PDF rendering
    pdf_logo_path: str = _env("PDF_LOGO_PATH", "app/static/dailymind-hero.jpg") or "app/static/dailymind-hero.jpg"
    pdf_font_path: str = _env("PDF_FONT_PATH", "app/static/fonts/Inter-Regular.ttf") or "app/static/fonts/Inter-Regular.ttf"
    pdf_font_bold_path: str = (
        _env("PDF_FONT_BOLD_PATH", "app/static/fonts/Inter-SemiBold.ttf") or "app/static/fonts/Inter-SemiBold.ttf"
    )

    # Debug logging (incoming requests)
    log_incoming_puzzlebot: bool = (_env("LOG_INCOMING_PUZZLEBOT", "1") or "1") == "1"
    log_incoming_puzzlebot_body: bool = (_env("LOG_INCOMING_PUZZLEBOT_BODY", "1") or "1") == "1"


settings = Settings()
