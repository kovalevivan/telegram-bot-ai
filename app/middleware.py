from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.settings import settings


# NOTE: don't use uvicorn.access here; its formatter expects access-log arguments.
logger = logging.getLogger("uvicorn.error")


def _mask_secret(value: str, *, keep_start: int = 6, keep_end: int = 4) -> str:
    if value is None:
        return ""
    s = str(value)
    if len(s) <= keep_start + keep_end:
        return "***"
    return f"{s[:keep_start]}***{s[-keep_end:]}"


def _safe_json_body(body_bytes: bytes) -> dict[str, Any] | None:
    if not body_bytes:
        return None
    try:
        data = json.loads(body_bytes.decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return {"_raw": data}
    # mask secrets in known fields
    if "bot_api_key" in data and isinstance(data["bot_api_key"], str):
        data["bot_api_key"] = _mask_secret(data["bot_api_key"])
    return data


class PuzzlebotRequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        if not settings.log_incoming_puzzlebot:
            return await call_next(request)

        if request.method.upper() != "POST" or request.url.path != "/api/v1/puzzlebot/ai":
            return await call_next(request)

        start = time.perf_counter()
        body = await request.body()

        # Re-create request so downstream can read body again
        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        req2 = Request(request.scope, receive)

        response: Response | None = None
        try:
            response = await call_next(req2)
            return response
        finally:
            dur_ms = int((time.perf_counter() - start) * 1000)
            client = request.client.host if request.client else "-"
            base = {
                "method": request.method,
                "path": request.url.path,
                "client": client,
                "ms": dur_ms,
                "status": getattr(response, "status_code", None),
            }
            if settings.log_incoming_puzzlebot_body:
                base["json"] = _safe_json_body(body)
            logger.info("incoming_puzzlebot %s", base)


