from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import session_scope
from app.models import Prompt, RequestLog
from app.services.llm import LLMError, openai_chat_completion
from app.services.rendering import render_template
from app.settings import settings


router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


def _is_authed(request: Request) -> bool:
    return bool(request.session.get("authed"))


def _require_auth(request: Request) -> None:
    if not _is_authed(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


@router.get("/")
async def ui_index(request: Request):
    if not _is_authed(request):
        return RedirectResponse(url="/ui/login", status_code=302)
    return RedirectResponse(url="/ui/prompts", status_code=302)


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "app_name": settings.app_name})


@router.post("/login")
async def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == settings.admin_username and password == settings.admin_password:
        request.session["authed"] = True
        return RedirectResponse(url="/ui/prompts", status_code=302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "app_name": settings.app_name, "error": "Неверный логин или пароль"},
        status_code=401,
    )


@router.post("/logout")
async def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(url="/ui/login", status_code=302)

@router.get("/llm")
async def llm_status(request: Request):
    _require_auth(request)
    base = settings.llm_base_url.rstrip("/")
    url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    api_key = settings.llm_api_key
    auth_value = api_key if not settings.llm_auth_prefix else f"{settings.llm_auth_prefix} {api_key}"
    headers = {
        settings.llm_auth_header: auth_value,
        "Accept": "application/json",
    }
    status = None
    body_snippet = None
    error = None
    if not api_key:
        error = "LLM_API_KEY не задан"
    else:
        try:
            r = await request.app.state.http.get(url, headers=headers)
            status = r.status_code
            body_snippet = (r.text or "")[:2000]
        except Exception as e:  # noqa: BLE001
            error = str(e)
    return templates.TemplateResponse(
        "llm_status.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "url": url,
            "status": status,
            "body_snippet": body_snippet,
            "error": error,
        },
    )

@router.get("/integration-test")
async def integration_test_page(request: Request, prompt_id: str | None = None):
    _require_auth(request)
    # Prefill with the new (recommended) payload shape.
    prefill = {
        "prompt": "Напиши короткий ответ: ok",
        "chat_id": 123456789,
        "bot_api_key": "123456:ABCDEF...",
    }
    if prompt_id:
        # Legacy prefill for stored prompt templates
        prefill = {
            "prompt_id": prompt_id,
            "params": {},
            "chat_id": 123456789,
            "bot_api_key": "123456:ABCDEF...",
        }
    return templates.TemplateResponse(
        "integration_test.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "request_json": json.dumps(prefill, ensure_ascii=False, indent=2),
            "accepted": None,
            "log": None,
            "error": None,
        },
    )


@router.post("/integration-test")
async def integration_test_run(request: Request, request_json: str = Form(...)):
    _require_auth(request)
    error = None
    accepted = None
    log = None

    try:
        payload = json.loads(request_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError("request must be a JSON object")
    except Exception as e:  # noqa: BLE001
        error = f"Некорректный JSON запроса: {e}"
        payload = {}

    if error is None:
        # Call the same endpoint internally (so validation + background task path are the same)
        import asyncio

        import httpx

        transport = httpx.ASGITransport(app=request.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://app") as client:
            r = await client.post("/api/v1/puzzlebot/ai", json=payload)
            if r.status_code >= 400:
                error = f"API error {r.status_code}: {(r.text or '')[:2000]}"
            else:
                accepted = r.json()

        # Poll logs by request_id (background task writes it)
        if accepted and "request_id" in accepted:
            request_id = accepted["request_id"]
            for _ in range(30):  # ~3s
                async with session_scope() as session:
                    res = await session.execute(select(RequestLog).where(RequestLog.request_id == request_id))
                    log = res.scalar_one_or_none()
                if log is not None:
                    break
                await asyncio.sleep(0.1)

    return templates.TemplateResponse(
        "integration_test.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "request_json": request_json,
            "accepted": accepted,
            "log": log,
            "error": error,
        },
    )


@router.get("/prompts")
async def prompts_list(request: Request):
    _require_auth(request)
    async with session_scope() as session:
        res = await session.execute(select(Prompt).order_by(Prompt.slug.asc()))
        prompts = list(res.scalars().all())
    return templates.TemplateResponse(
        "prompts_list.html",
        {"request": request, "app_name": settings.app_name, "prompts": prompts},
    )


@router.get("/prompts/new")
async def prompt_new(request: Request):
    _require_auth(request)
    return templates.TemplateResponse(
        "prompt_form.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "mode": "create",
            "prompt": None,
        },
    )


@router.post("/prompts/new")
async def prompt_create(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    system_template: str = Form(""),
    user_template: str = Form(...),
    provider: str = Form("openai"),
    model: str = Form(...),
    temperature: float = Form(0.2),
    max_tokens: str = Form("512"),
):
    _require_auth(request)
    mt = (max_tokens or "").strip()
    mt_int = int(mt) if mt != "" else 0
    async with session_scope() as session:
        obj = Prompt(
            slug=slug.strip(),
            name=name.strip(),
            system_template=(system_template or "").strip() or None,
            user_template=user_template,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=mt_int,
        )
        session.add(obj)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return templates.TemplateResponse(
                "prompt_form.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                    "mode": "create",
                    "prompt": obj,
                    "error": "Такой slug уже существует",
                },
                status_code=409,
            )
    return RedirectResponse(url="/ui/prompts", status_code=302)


@router.get("/prompts/{slug}")
async def prompt_edit(request: Request, slug: str):
    _require_auth(request)
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == slug))
        prompt = res.scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return templates.TemplateResponse(
        "prompt_form.html",
        {"request": request, "app_name": settings.app_name, "mode": "edit", "prompt": prompt},
    )

@router.get("/prompts/{slug}/test")
async def prompt_test_page(request: Request, slug: str):
    _require_auth(request)
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == slug))
        prompt = res.scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return templates.TemplateResponse(
        "prompt_test.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "prompt": prompt,
            "params_json": "{}",
            "rendered_system": None,
            "rendered_user": None,
            "llm_text": None,
            "error": None,
        },
    )


@router.post("/prompts/{slug}/test")
async def prompt_test_run(request: Request, slug: str, params_json: str = Form("{}")):
    _require_auth(request)
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == slug))
        prompt = res.scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")

    error = None
    rendered_system = None
    rendered_user = None
    llm_text = None

    try:
        params = json.loads(params_json or "{}")
        if not isinstance(params, dict):
            raise ValueError("params must be a JSON object")
    except Exception as e:  # noqa: BLE001
        error = f"Некорректный JSON в params: {e}"
        params = {}

    if error is None:
        try:
            rendered_system = render_template(prompt.system_template, params)
            rendered_user = render_template(prompt.user_template, params) or ""
        except Exception as e:  # noqa: BLE001
            error = f"Ошибка рендеринга шаблона: {e}"

    if error is None:
        api_key = settings.llm_api_key
        if not api_key:
            error = "LLM_API_KEY не задан в .env"
        else:
            http = request.app.state.http
            try:
                res = await openai_chat_completion(
                    http,
                    model=prompt.model,
                    api_key=api_key,
                    system=rendered_system,
                    user=rendered_user or "",
                    temperature=prompt.temperature,
                    max_tokens=prompt.max_tokens,
                )
                llm_text = res.text
            except LLMError as e:
                error = str(e)

    return templates.TemplateResponse(
        "prompt_test.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "prompt": prompt,
            "params_json": params_json or "{}",
            "rendered_system": rendered_system,
            "rendered_user": rendered_user,
            "llm_text": llm_text,
            "error": error,
        },
    )


@router.post("/prompts/{slug}")
async def prompt_update(
    request: Request,
    slug: str,
    name: str = Form(...),
    system_template: str = Form(""),
    user_template: str = Form(...),
    provider: str = Form("openai"),
    model: str = Form(...),
    temperature: float = Form(0.2),
    max_tokens: str = Form("512"),
):
    _require_auth(request)
    mt = (max_tokens or "").strip()
    mt_int = int(mt) if mt != "" else 0
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == slug))
        prompt = res.scalar_one_or_none()
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        prompt.name = name.strip()
        prompt.system_template = (system_template or "").strip() or None
        prompt.user_template = user_template
        prompt.provider = provider
        prompt.model = model
        prompt.temperature = temperature
        prompt.max_tokens = mt_int
        await session.commit()
    return RedirectResponse(url="/ui/prompts", status_code=302)


@router.post("/prompts/{slug}/delete")
async def prompt_delete(request: Request, slug: str):
    _require_auth(request)
    async with session_scope() as session:
        res = await session.execute(select(Prompt).where(Prompt.slug == slug))
        prompt = res.scalar_one_or_none()
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        await session.delete(prompt)
        await session.commit()
    return RedirectResponse(url="/ui/prompts", status_code=302)


