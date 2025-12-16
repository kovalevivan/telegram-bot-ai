from __future__ import annotations

import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.protocols.utils import get_path_with_query_string

from app import __version__
from app.api import get_http_client, router as api_router
from app.db import engine
from app.middleware import PuzzlebotRequestLoggingMiddleware
from app.models import Base
from app.settings import settings
from app.ui import router as ui_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # env + data dir
    load_dotenv(override=True)
    os.makedirs("./data", exist_ok=True)

    # db init
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # shared http client (LLM + Telegram)
    limits = httpx.Limits(max_connections=500, max_keepalive_connections=100)
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=30.0)
    app.state.http = httpx.AsyncClient(limits=limits, timeout=timeout)
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(PuzzlebotRequestLoggingMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")

@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def root_health():
    # Many platforms use HEAD / for health checks.
    return {"status": "ok"}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Make 422 debuggable in logs (masking secrets is handled by middleware; here we only log the error details).
    import logging

    # NOTE: don't use uvicorn.access here; its formatter expects access-log arguments.
    log = logging.getLogger("uvicorn.error")
    if request.url.path == "/api/v1/puzzlebot/ai":
        safe_errors = jsonable_encoder(exc.errors())
        log.info(
            "puzzlebot_422 %s errors=%s",
            get_path_with_query_string(request.scope),
            safe_errors,
        )
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


async def _http_dep(request: Request):
    return request.app.state.http


app.dependency_overrides[get_http_client] = _http_dep

app.include_router(api_router)
app.include_router(ui_router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
