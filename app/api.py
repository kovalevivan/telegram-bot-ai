from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import session_scope
from app.models import Prompt, RequestLog
from app.schemas import AcceptedResponse, PromptCreate, PromptOut, PromptUpdate, PuzzlebotAIRequest
from app.services.llm import LLMError, openai_chat_completion
from app.services.rendering import render_template
from app.services.telegram import TelegramError, send_message
from app.settings import settings


router = APIRouter(prefix="/api/v1", tags=["api"])


async def _get_prompt_by_slug(prompt_id: str) -> Prompt:
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == prompt_id))
        prompt = res.scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' not found")
    return prompt


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/prompts", response_model=list[PromptOut])
async def list_prompts() -> list[PromptOut]:
    async with session_scope() as session:
        res = await session.execute(select(Prompt).order_by(Prompt.slug.asc()))
        return list(res.scalars().all())


@router.post("/prompts", response_model=PromptOut)
async def create_prompt(payload: PromptCreate) -> PromptOut:
    async with session_scope() as session:
        obj = Prompt(
            slug=payload.slug,
            name=payload.name,
            system_template=payload.system_template,
            user_template=payload.user_template,
            provider=payload.provider,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
        session.add(obj)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Prompt slug must be unique") from e
        await session.refresh(obj)
        return obj


@router.get("/prompts/{slug}", response_model=PromptOut)
async def get_prompt(slug: str) -> PromptOut:
    prompt = await _get_prompt_by_slug(slug)
    return prompt


@router.put("/prompts/{slug}", response_model=PromptOut)
async def update_prompt(slug: str, payload: PromptUpdate) -> PromptOut:
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == slug))
        prompt = res.scalar_one_or_none()
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")

        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(prompt, k, v)
        await session.commit()
        await session.refresh(prompt)
        return prompt


@router.delete("/prompts/{slug}")
async def delete_prompt(slug: str) -> dict:
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == slug))
        prompt = res.scalar_one_or_none()
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        await session.delete(prompt)
        await session.commit()
    return {"status": "deleted"}


async def get_http_client() -> "object":
    # overridden in app.main via dependency override to return app.state.http
    raise RuntimeError("HTTP client not configured")


async def _process_request(
    *,
    request_id: str,
    body: PuzzlebotAIRequest,
    http,
) -> None:
    chat_id = body.chat_id

    rendered_system = None
    rendered_user = None
    llm_text = None
    llm_ok = False
    tg_ok = False
    llm_error = None
    tg_error = None

    # Resolve prompt config:
    # - Mode A: raw prompt in request
    # - Mode B: stored prompt template (legacy)
    prompt_slug_for_log = "__raw__"
    params_for_log = body.params or {}

    if body.prompt is not None:
        rendered_system = body.system
        rendered_user = body.prompt
        model = body.model or settings.llm_default_model
        temperature = body.temperature if body.temperature is not None else 0.2
        max_tokens = body.max_tokens if body.max_tokens is not None else 0  # default: unlimited
    else:
        if not body.prompt_id:
            llm_error = "Either 'prompt' or 'prompt_id' must be provided"
            model = settings.llm_default_model
            temperature = 0.2
            max_tokens = 0
        else:
            prompt_slug_for_log = body.prompt_id
            prompt = await _get_prompt_by_slug(body.prompt_id)
            model = prompt.model
            temperature = prompt.temperature
            max_tokens = prompt.max_tokens
            try:
                rendered_system = render_template(prompt.system_template, body.params)
                rendered_user = render_template(prompt.user_template, body.params) or ""
            except Exception as e:  # noqa: BLE001
                llm_error = f"Prompt render error: {e}"

    if llm_error is None:
        api_key = settings.llm_api_key
        if not api_key:
            llm_error = "LLM_API_KEY is not configured"
        else:
            try:
                res = await openai_chat_completion(
                    http,
                    model=model,
                    api_key=api_key,
                    system=rendered_system,
                    user=rendered_user or "",
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                llm_text = res.text
                llm_ok = True
            except LLMError as e:
                llm_error = str(e)

    if llm_ok and llm_text:
        try:
            await send_message(
                http,
                bot_token=body.bot_api_key,
                chat_id=chat_id,
                text=llm_text,
                parse_mode=body.parse_mode,
            )
            tg_ok = True
        except TelegramError as e:
            tg_error = str(e)

    async with session_scope() as session:
        session.add(
            RequestLog(
                request_id=request_id,
                prompt_slug=prompt_slug_for_log,
                user_id=body.user_id or 0,
                chat_id=chat_id,
                params=params_for_log,
                rendered_system=rendered_system,
                rendered_user=rendered_user,
                llm_ok=llm_ok,
                llm_error=llm_error,
                llm_response_text=llm_text,
                telegram_ok=tg_ok,
                telegram_error=tg_error,
            )
        )
        await session.commit()


@router.post("/puzzlebot/ai", response_model=AcceptedResponse, status_code=202)
async def puzzlebot_ai(
    body: PuzzlebotAIRequest,
    background: BackgroundTasks,
    http=Depends(get_http_client),
) -> AcceptedResponse:
    request_id = uuid.uuid4().hex
    background.add_task(_process_request, request_id=request_id, body=body, http=http)
    return AcceptedResponse(request_id=request_id)


