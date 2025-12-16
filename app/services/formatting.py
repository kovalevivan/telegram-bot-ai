from __future__ import annotations

import html
import re


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _escape_and_bold(s: str) -> str:
    """
    Convert very small subset of Markdown to Telegram HTML:
      - **bold** -> <b>bold</b>
    Everything else is HTML-escaped.
    """
    if not s:
        return ""

    out: list[str] = []
    last = 0
    for m in _BOLD_RE.finditer(s):
        out.append(html.escape(s[last : m.start()]))
        out.append("<b>")
        out.append(html.escape(m.group(1)))
        out.append("</b>")
        last = m.end()
    out.append(html.escape(s[last:]))
    return "".join(out)


def markdown_to_telegram_html_blocks(md: str) -> list[str]:
    """
    Best-effort conversion of a markdown-ish LLM output into Telegram HTML blocks.

    Supported:
      - **bold**
      - bullet lists starting with "- "

    Returns a list of HTML blocks that are safe to concatenate with "<br><br>".
    Each list block is a self-contained <ul>...</ul>.
    """
    md = (md or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not md:
        return [""]

    blocks: list[str] = []
    para_lines: list[str] = []
    list_items: list[str] = []

    def flush_para() -> None:
        nonlocal para_lines
        if not para_lines:
            return
        html_lines = [_escape_and_bold(line) for line in para_lines]
        blocks.append("<br>".join(html_lines))
        para_lines = []

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        lis = "".join(f"<li>{_escape_and_bold(item.strip())}</li>" for item in list_items if item.strip())
        blocks.append(f"<ul>{lis}</ul>")
        list_items = []

    for raw in md.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            continue
        if line.lstrip().startswith("- "):
            flush_para()
            list_items.append(line.lstrip()[2:])
            continue
        flush_list()
        para_lines.append(line)

    flush_para()
    flush_list()
    return blocks if blocks else [""]


def pack_html_blocks(blocks: list[str], *, limit: int) -> list[str]:
    """
    Pack blocks into chunks not exceeding limit, joining with <br><br>.
    If a single block exceeds limit, it will be split in a conservative way.
    """
    blocks = blocks or [""]
    chunks: list[str] = []
    cur = ""

    def push(s: str) -> None:
        if s:
            chunks.append(s)

    for block in blocks:
        sep = "<br><br>" if cur else ""
        candidate = f"{cur}{sep}{block}" if cur else block
        if len(candidate) <= limit:
            cur = candidate
            continue

        push(cur)
        cur = ""

        if len(block) <= limit:
            cur = block
            continue

        # Split oversized block:
        if block.startswith("<ul>") and block.endswith("</ul>"):
            # Split list items into multiple <ul> blocks
            items = re.findall(r"<li>.*?</li>", block, flags=re.DOTALL)
            buf_items: list[str] = []
            for it in items:
                candidate_ul = "<ul>" + "".join(buf_items + [it]) + "</ul>"
                if len(candidate_ul) <= limit:
                    buf_items.append(it)
                    continue
                if buf_items:
                    push("<ul>" + "".join(buf_items) + "</ul>")
                    buf_items = []
                # item itself too large: hard cut inside li
                if len("<ul>" + it + "</ul>") <= limit:
                    buf_items.append(it)
                else:
                    # fallback: drop tags and hard split plain text
                    txt = re.sub(r"<.*?>", "", it)
                    while txt:
                        push(html.escape(txt[:limit]))
                        txt = txt[limit:]
            if buf_items:
                cur = "<ul>" + "".join(buf_items) + "</ul>"
            continue

        # Paragraph: split by <br> boundaries then hard cut
        parts = block.split("<br>")
        buf = ""
        for p in parts:
            sep2 = "<br>" if buf else ""
            cand2 = f"{buf}{sep2}{p}" if buf else p
            if len(cand2) <= limit:
                buf = cand2
                continue
            if buf:
                push(buf)
                buf = ""
            if len(p) <= limit:
                buf = p
            else:
                # last resort: hard cut (avoid breaking tags by stripping them)
                txt = re.sub(r"<.*?>", "", p)
                while txt:
                    push(html.escape(txt[:limit]))
                    txt = txt[limit:]
        cur = buf

    push(cur)
    return chunks or [""]


