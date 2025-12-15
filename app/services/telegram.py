from __future__ import annotations

import httpx


class TelegramError(RuntimeError):
    pass


async def send_message(
    client: httpx.AsyncClient,
    *,
    bot_token: str,
    chat_id: int,
    text: str,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = True,
) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        r = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise TelegramError(f"Telegram request failed: {e}") from e
    if r.status_code >= 400:
        raise TelegramError(f"Telegram error {r.status_code}: {r.text[:2000]}")


