from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.settings import settings

_FALLBACK_MAX_COMPLETION_TOKENS_FOR_UNLIMITED = 8192


@dataclass(frozen=True)
class LLMResult:
    text: str


class LLMError(RuntimeError):
    pass


def _chat_completions_url(base_url: str) -> str:
    """
    OpenAI-compatible servers are inconsistent about whether the "base url" ends with /v1.
    We accept both:
      - https://api.openai.com          -> /v1/chat/completions
      - https://.../v1                 -> /chat/completions
    """
    base = (base_url or "").rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _needs_max_completion_tokens(r: httpx.Response) -> bool:
    """
    Some OpenAI-compatible providers (or specific models like gpt-5.*) reject `max_tokens`
    and require `max_completion_tokens`.
    We detect that case and retry once with the alternative field.
    """
    if r.status_code != 400:
        return False
    snippet = (r.text or "")[:5000]
    return ("max_completion_tokens" in snippet) and ("max_tokens" in snippet)


async def openai_chat_completion(
    client: httpx.AsyncClient,
    *,
    model: str,
    api_key: str,
    system: str | None,
    user: str,
    temperature: float,
    max_tokens: int | None,
) -> LLMResult:
    url = _chat_completions_url(settings.llm_base_url)
    headers = {
        settings.llm_auth_header: (api_key if not settings.llm_auth_prefix else f"{settings.llm_auth_prefix} {api_key}"),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    # If max_tokens <= 0 (or None) => do not send a limit at all
    if max_tokens is not None and max_tokens > 0:
        payload["max_tokens"] = max_tokens
    try:
        r = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise LLMError(f"LLM request failed: {e}") from e

    # Fallback: retry with max_completion_tokens if provider rejects max_tokens
    if _needs_max_completion_tokens(r):
        payload2 = dict(payload)
        payload2.pop("max_tokens", None)
        # If "unlimited" requested, use a large safe default
        payload2["max_completion_tokens"] = (
            max_tokens if (max_tokens is not None and max_tokens > 0) else _FALLBACK_MAX_COMPLETION_TOKENS_FOR_UNLIMITED
        )
        try:
            r = await client.post(url, headers=headers, json=payload2)
        except httpx.HTTPError as e:
            raise LLMError(f"LLM request failed: {e}") from e

    if r.status_code >= 400:
        snippet = (r.text or "")[:2000]
        hint = ""
        if "text/html" in (r.headers.get("content-type") or "") or "<!DOCTYPE html" in snippet:
            hint = (
                " (Похоже, это HTML 404. Проверьте LLM_BASE_URL: он должен указывать на OpenAI-compatible API. "
                "Если base url уже заканчивается на /v1, уберите лишний /v1 или используйте корректный base.)"
            )
        raise LLMError(f"LLM error {r.status_code} at {url}: {snippet}{hint}")

    data = r.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"Unexpected LLM response format: {data}") from e
    return LLMResult(text=text)


