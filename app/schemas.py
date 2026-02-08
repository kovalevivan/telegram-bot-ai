from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PromptBase(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, description="prompt_id для вызова из Puzzlebot")
    name: str = Field(..., min_length=1, max_length=256)
    system_template: str | None = None
    user_template: str = Field(..., min_length=1)
    provider: str = Field(default="openai")
    model: str = Field(..., min_length=1, max_length=128)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=0, le=8192, description="0 = не задавать лимит в запросе к LLM")


class PromptCreate(PromptBase):
    pass


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    system_template: str | None = None
    user_template: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=0, le=8192, description="0 = не задавать лимит в запросе к LLM")


class PromptOut(PromptBase):
    id: int

    class Config:
        from_attributes = True


class PuzzlebotAIRequest(BaseModel):
    # Mode A (preferred): provide a ready prompt text directly (less params)
    prompt: str | None = Field(default=None, description="Готовый текст промта (если задан — prompt_id/params не нужны)")
    system: str | None = Field(default=None, description="Опциональный system prompt (только для режима prompt)")

    # Mode B (legacy): use stored prompt + params
    prompt_id: str | None = Field(default=None, description="slug промта (если задан — будет использоваться шаблон из БД)")
    params: dict[str, Any] = Field(default_factory=dict)

    # Telegram
    bot_api_key: str = Field(..., description="Telegram bot token")
    chat_id: int
    user_id: int | None = Field(default=None, description="Опционально (для логов/совместимости)")
    # parse_mode intentionally unused: we always send plain text to avoid formatting-related Telegram errors
    parse_mode: str | None = Field(default=None, description="(не используется) всегда отправляем plain text")
    send_pdf: bool = Field(
        default=False,
        description="Если true — отправим PDF-файл с брендингом DailyMind вместо plain text",
    )

    # Optional overrides for mode A (keep API small by default)
    model: str | None = Field(default=None, description="Опционально: переопределить модель")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=0, le=8192, description="0 = не задавать лимит в запросе к LLM")

    @model_validator(mode="before")
    @classmethod
    def _parse_json_string_body(cls, data: Any):
        """
        Puzzlebot (and some low-code tools) sometimes send the body as a JSON *string*
        instead of an object. Accept both:
          - { ... }   (dict)
          - "{...}"   (string with JSON inside)
        """
        if isinstance(data, (bytes, bytearray)):
            try:
                data = data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return data
        if isinstance(data, str):
            s = data.strip()
            # Try parse JSON string -> dict
            try:
                parsed = json.loads(s)
            except Exception:  # noqa: BLE001
                return data
            return parsed
        return data


class AcceptedResponse(BaseModel):
    status: str = "accepted"
    request_id: str
    error: str | None = None


class ProcessedResponse(BaseModel):
    status: str = "ok"
    request_id: str
    llm_ok: bool
    telegram_ok: bool


class RequestLogOut(BaseModel):
    request_id: str
    prompt_slug: str
    chat_id: int
    user_id: int

    llm_ok: bool
    llm_error: str | None = None
    telegram_ok: bool
    telegram_error: str | None = None

    llm_response_text: str | None = None

    class Config:
        from_attributes = True
