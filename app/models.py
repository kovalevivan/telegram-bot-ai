from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # slug используется как prompt_id при вызове из Puzzlebot
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    system_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)

    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=512)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    prompt_slug: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    rendered_system: Mapped[str | None] = mapped_column(Text, nullable=True)
    rendered_user: Mapped[str | None] = mapped_column(Text, nullable=True)

    llm_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    telegram_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    telegram_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
