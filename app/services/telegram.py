from __future__ import annotations

import httpx


class TelegramError(RuntimeError):
    pass


TELEGRAM_MESSAGE_LIMIT = 4096
# небольшой запас, чтобы не упираться в пограничные случаи (форматирование/юникод)
TELEGRAM_SAFE_LIMIT = 3900


def _split_text(text: str, limit: int = TELEGRAM_SAFE_LIMIT) -> list[str]:
    """
    Best-effort split of long text into chunks suitable for Telegram sendMessage.
    Tries to split by double-newline, then newline, then hard-cut.
    """
    text = text or ""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    parts = text.split("\n\n")
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            chunks.append(buf)
            buf = ""

    for p in parts:
        candidate = (buf + ("\n\n" if buf else "") + p).strip()
        if len(candidate) <= limit:
            buf = candidate
            continue

        # candidate too big — flush current buffer and split this part further
        flush()

        if len(p) <= limit:
            chunks.append(p.strip())
            continue

        # split by single newline
        lines = p.split("\n")
        line_buf = ""
        for line in lines:
            cand2 = (line_buf + ("\n" if line_buf else "") + line).strip()
            if len(cand2) <= limit:
                line_buf = cand2
                continue
            if line_buf:
                chunks.append(line_buf)
                line_buf = ""
            # line itself too big — hard cut
            s = line
            while s:
                chunks.append(s[:limit])
                s = s[limit:]
        if line_buf:
            chunks.append(line_buf)

    flush()
    # safety: remove empty chunks
    return [c for c in chunks if c]


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

    chunks = _split_text(text, TELEGRAM_SAFE_LIMIT)
    # Если включён parse_mode и нужно резать — безопаснее отправить plain text,
    # иначе можно порезать HTML/Markdown посередине и получить 400.
    effective_parse_mode = parse_mode if len(chunks) == 1 else None

    for part in chunks:
        payload: dict = {
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if effective_parse_mode:
            payload["parse_mode"] = effective_parse_mode
        try:
            r = await client.post(url, json=payload)
        except httpx.HTTPError as e:
            raise TelegramError(f"Telegram request failed: {e}") from e
        if r.status_code >= 400:
            raise TelegramError(f"Telegram error {r.status_code}: {r.text[:2000]}")


