from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Iterable, Tuple

from html import unescape

from html.parser import HTMLParser
from PIL import Image
from fpdf import FPDF
from app.settings import settings
from fpdf.html import HTMLMixin


ACCENT_GOLD = (231, 193, 117)
ACCENT_TEAL = (88, 195, 184)
HEADER_DEEP = (14, 19, 42)
HEADER_NIGHT = (28, 35, 66)
CARD_BG = (246, 248, 254)
TEXT_PRIMARY = (26, 31, 45)
TEXT_SECONDARY = (94, 104, 128)


class DailyMindPDF(FPDF, HTMLMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dm_body_y: float | None = None
        self.dm_body_y_first: float | None = None
        self.dm_body_y_next: float | None = None
        self.dm_draw_bg = None
        self.dm_header_drawer = None

    def add_page(self, *args, **kwargs):
        super().add_page(*args, **kwargs)
        if self.page > 1 and self.dm_body_y_next is not None:
            self.dm_body_y = self.dm_body_y_next
        elif self.page == 1 and self.dm_body_y_first is not None:
            self.dm_body_y = self.dm_body_y_first
        if self.dm_draw_bg:
            self.dm_draw_bg()
        if self.dm_body_y:
            self.set_y(self.dm_body_y)


def _register_fonts(
    pdf: FPDF,
    *,
    heading_regular: str | None,
    heading_bold: str | None,
    body_regular: str | None,
    body_bold: str | None,
    body_italic: str | None,
    body_bold_italic: str | None,
    emoji_font: str | None = None,
) -> tuple[str, str, str | None]:
    """
    Register Unicode fonts for PDF rendering.
    Returns (heading_family, body_family, emoji_family).
    """
    heading_family = "Helvetica"
    body_family = "Helvetica"
    emoji_family: str | None = None

    hr = Path(heading_regular) if heading_regular else None
    hb = Path(heading_bold) if heading_bold else None
    if hr and hr.exists():
        heading_family = "DailyMind"
        pdf.add_font(heading_family, "", str(hr), uni=True)
        pdf.add_font(heading_family, "B", str(hb if hb and hb.exists() else hr), uni=True)
        pdf.add_font(heading_family, "I", str(hr), uni=True)
        pdf.add_font(heading_family, "BI", str(hb if hb and hb.exists() else hr), uni=True)

    br = Path(body_regular) if body_regular else None
    bb = Path(body_bold) if body_bold else None
    bi = Path(body_italic) if body_italic else None
    bbi = Path(body_bold_italic) if body_bold_italic else None
    if br and br.exists():
        body_family = "DailyMindSerif"
        pdf.add_font(body_family, "", str(br), uni=True)
        pdf.add_font(body_family, "B", str(bb if bb and bb.exists() else br), uni=True)
        pdf.add_font(body_family, "I", str(bi if bi and bi.exists() else br), uni=True)
        pdf.add_font(body_family, "BI", str(bbi if bbi and bbi.exists() else (bb if bb and bb.exists() else br)), uni=True)
    else:
        body_family = heading_family

    ef = Path(emoji_font) if emoji_font else None
    if ef and ef.exists():
        try:
            emoji_family = "DailyMindEmoji"
            pdf.add_font(emoji_family, "", str(ef), uni=True)
            pdf.add_font(emoji_family, "B", str(ef), uni=True)
            pdf.add_font(emoji_family, "I", str(ef), uni=True)
            pdf.add_font(emoji_family, "BI", str(ef), uni=True)
        except Exception:  # noqa: BLE001
            emoji_family = None

    return heading_family, body_family, emoji_family


def _draw_header(pdf: FPDF, *, logo_path: str | None) -> float:
    """
    Draw branded header image; returns used height in mm.
    """
    logo = Path(logo_path) if logo_path else None
    page_width = 210.0
    default_height = 88.0
    if logo and logo.exists():
        try:
            with Image.open(logo) as im:
                w, h = im.size
            ratio = h / w if w else 0.5
            header_h = max(70.0, min(130.0, page_width * ratio))
        except Exception:  # noqa: BLE001
            header_h = default_height
        pdf.image(str(logo), x=0, y=0, w=page_width)
        return header_h

    # Fallback simple gradient header if image missing
    pdf.set_fill_color(*HEADER_DEEP)
    pdf.rect(x=0, y=0, w=page_width, h=default_height, style="F")
    pdf.set_fill_color(*HEADER_NIGHT)
    pdf.rect(x=0, y=40, w=page_width, h=default_height - 40, style="F")
    return default_height


def _parse_text(text: str) -> tuple[str | None, list[str], list[str]]:
    """
    Extract a headline (first meaningful line), bullet-like items, and the rest paragraphs.
    """
    headline: str | None = None
    bullets: list[str] = []
    paragraphs: list[str] = []

    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if headline is None and not re.match(r"^[-*•\d]", line):
            headline = line
            continue

        normalized = re.sub(r"^[\s\-•\*\d\)\.(]+", "", line).strip()
        if normalized and normalized != line:
            bullets.append(normalized)
        else:
            paragraphs.append(line)

    return headline, bullets, paragraphs


class _HTMLBlockParser(HTMLParser):
    """
    Tiny HTML walker that keeps only structure we care about.
    Produces blocks of types: heading, paragraph, li, hr.
    """

    def __init__(self):
        super().__init__()
        self.blocks: list[dict] = []
        self._current_tag: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "p", "div", "section", "li"}:
            self._flush()
            self._current_tag = tag
        elif tag == "hr":
            self._flush()
            self.blocks.append({"type": "hr"})

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "p", "div", "section", "li"} and self._current_tag:
            self._flush()
            self._current_tag = None

    def handle_data(self, data):
        if self._current_tag:
            self._current_text.append(data)

    def handle_entityref(self, name):
        self.handle_data(unescape(f"&{name};"))

    def handle_charref(self, name):
        try:
            codepoint = int(name[1:], 16) if name.startswith("x") else int(name)
            self.handle_data(chr(codepoint))
        except Exception:  # noqa: BLE001
            pass

    def _flush(self):
        if not self._current_text:
            return
        text = "".join(self._current_text).strip()
        self._current_text = []
        if not text:
            return
        tag = (self._current_tag or "").lower()
        if tag in {"h1", "h2", "h3"}:
            self.blocks.append({"type": "heading", "text": text})
        elif tag == "li":
            self.blocks.append({"type": "li", "text": text})
        else:
            self.blocks.append({"type": "paragraph", "text": text})


def _parse_html_blocks(html: str) -> tuple[str | None, list[dict]]:
    parser = _HTMLBlockParser()
    parser.feed(html or "")
    parser.close()
    blocks = parser.blocks
    if not blocks:
        return None, []
    main_heading = None
    for idx, blk in enumerate(blocks):
        if blk.get("type") == "heading":
            main_heading = blk.get("text")
            blocks = blocks[idx + 1 :]
            break

    # Drop duplicate headings that match the main heading (case-insensitive)
    if main_heading:
        blocks = [b for b in blocks if not (b.get("type") == "heading" and b.get("text", "").strip().lower() == main_heading.strip().lower())]
    return main_heading, blocks


def _multi_paragraph(pdf: FPDF, *, font_family: str, text_blocks: Iterable[str]) -> None:
    for block in text_blocks:
        pdf.set_font(font_family, "", 12)
        pdf.set_text_color(*TEXT_PRIMARY)
        pdf.multi_cell(w=0, h=7, txt=block, align="J")
        pdf.ln(2)


def _html_to_text(s: str) -> str:
    if not s:
        return ""
    t = re.sub(r"<br\\s*/?>", "\n", s, flags=re.I)
    t = re.sub(r"</p>", "\n\n", t, flags=re.I)
    t = re.sub(r"</li>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return unescape(t)


def _sanitize_html(s: str) -> str:
    if not s:
        return ""
    # Drop script/style
    s = re.sub(r"<(script|style)[^>]*?>[\\s\\S]*?</\\1>", "", s, flags=re.I)
    # Remove inline colors and redundant tags that may force red text
    s = re.sub(r'style=["\'][^"\']*?color[^"\']*?["\']', "", s, flags=re.I)
    s = re.sub(r"<font[^>]*?color=[\"'][^\"']+[\"'][^>]*?>", "", s, flags=re.I)
    s = re.sub(r"<span[^>]*?color=[\"'][^\"']+[\"'][^>]*?>", "<span>", s, flags=re.I)
    s = re.sub(r"</font>", "", s, flags=re.I)
    return s


def _extract_first_block(html: str) -> tuple[str | None, str]:
    """
    Return (first_block_text, html_without_that_block)
    """
    if not html:
        return None, html
    patterns = [
        r"<(h1|h2|h3|p|div|section)[^>]*?>[\\s\\S]*?</\\1>",
        r"<li[^>]*?>[\\s\\S]*?</li>",
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.I)
        if m:
            block_html = m.group(0)
            text = _html_to_text(block_html).strip()
            remainder = (html[: m.start()] + html[m.end() :]).lstrip()
            return (text or None), remainder
    br = re.search(r"<br\\s*/?>", html, flags=re.I)
    if br:
        remainder = html[br.end() :].lstrip()
        return None, remainder
    return None, html


def _looks_like_html(s: str) -> bool:
    return bool(re.search(r"<[a-zA-Z][^>]*>", s or ""))


def _safe_text(s: str) -> str:
    """
    Remove control characters; keep emoji as-is so they can be rendered by emoji font.
    """
    if not s:
        return ""
    s = s.replace("\ufeff", "")
    # Drop control chars
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s


def _safe_multicell(pdf: FPDF, *, width: float, line_height: float, text: str, align: str = "J"):
    txt = _safe_text(text)
    try:
        pdf.multi_cell(w=width, h=line_height, txt=txt, align=align)
    except Exception:  # noqa: BLE001
        fallback = txt.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(w=width, h=line_height, txt=fallback, align=align)


def _font_for_text(text: str, *, heading_family: str, body_family: str, emoji_family: str | None) -> str:
    """
    Use the emoji-capable body font when text includes emoji/variation selectors.
    """
    if emoji_family and re.search(r"[\U0001F000-\U0010FFFF\u2600-\u27BF\ufe0f]", text or ""):
        return emoji_family
    return heading_family


def _estimate_multiline_height(pdf: FPDF, *, text: str, width: float, line_height: float) -> float:
    words = (text or "").split()
    if not words:
        return 0.0
    lines = 1
    current_width = 0.0
    for w in words:
        ww = pdf.get_string_width(w)
        if current_width and current_width + ww + pdf.get_string_width(" ") > width:
            lines += 1
            current_width = ww
        else:
            current_width += ww + pdf.get_string_width(" ")
    return lines * line_height


def build_daily_mind_pdf(
    text: str,
    *,
    logo_path: str | None,
    font_path_regular: str | None,
    font_path_bold: str | None,
    title: str = "",
    birth_date: str | None = None,
    birth_time: str | None = None,
    birth_city: str | None = None,
    forecast_date: str | None = None,
) -> bytes:
    """
    Render a branded DailyMind PDF and return raw bytes.
    """
    pdf = DailyMindPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)

    heading_family, body_family, emoji_family = _register_fonts(
        pdf,
        heading_regular=font_path_regular,
        heading_bold=font_path_bold,
        body_regular=settings.pdf_body_font_path,
        body_bold=settings.pdf_body_font_bold_path,
        body_italic=settings.pdf_body_font_italic_path,
        body_bold_italic=settings.pdf_body_font_bold_italic_path,
        emoji_font=settings.pdf_emoji_font_path,
    )
    pdf.add_page()

    header_height = _draw_header(pdf, logo_path=logo_path)
    body_y_first = header_height + 8
    body_y_next = pdf.t_margin + 6

    def draw_background():
        y0 = pdf.dm_body_y or body_y_first
        prev_auto = pdf.auto_page_break
        prev_margin = pdf.b_margin
        pdf.set_auto_page_break(auto=False)
        h = max(40.0, pdf.h - y0 - prev_margin)
        pdf.set_fill_color(*CARD_BG)
        pdf.set_draw_color(226, 232, 246)
        pdf.set_line_width(0.2)
        pdf.rect(x=14, y=y0, w=182, h=h, style="FD")
        pdf.set_auto_page_break(auto=prev_auto, margin=prev_margin)

    pdf.dm_body_y_first = body_y_first
    pdf.dm_body_y_next = body_y_next
    pdf.dm_body_y = body_y_first
    pdf.dm_draw_bg = draw_background
    draw_background()

    is_html = _looks_like_html(text)
    sanitized_html = _sanitize_html(text) if is_html else ""
    html_blocks: list[dict] = []
    headline = None
    bullets: list[str] = []
    paragraphs: list[str] = []

    if is_html:
        headline, html_blocks = _parse_html_blocks(sanitized_html)
    else:
        headline, bullets, paragraphs = _parse_text(text)
        if paragraphs and headline and paragraphs[0].strip().lower() == headline.strip().lower():
            paragraphs = paragraphs[1:]

    content_x = 22
    content_width = pdf.w - content_x - pdf.r_margin
    pdf.set_left_margin(content_x)
    pdf.set_right_margin(pdf.r_margin)
    pdf.set_x(content_x)
    pdf.set_y((pdf.dm_body_y or body_y_first) + 6)

    title_text = re.sub(r"^[\\s•·\\-]+", "", (headline or title or "DailyMind")).strip()
    heading_for_title = _font_for_text(title_text, heading_family=heading_family, body_family=body_family, emoji_family=emoji_family)
    pdf.set_font(heading_for_title, "B", 18)
    pdf.set_text_color(*TEXT_PRIMARY)
    _safe_multicell(pdf, width=content_width, line_height=8, text=title_text, align="L")
    pdf.ln(2)

    info_chunks = []
    if birth_date:
        info_chunks.append(f"Дата рождения: {birth_date}")
    if birth_time:
        info_chunks.append(f"Время рождения: {birth_time}")
    if birth_city:
        info_chunks.append(f"Город: {birth_city}")
    info_line = "  •  ".join(info_chunks)
    if info_line:
        pdf.set_font(_font_for_text(info_line, heading_family=heading_family, body_family=body_family, emoji_family=emoji_family), "", 10)
        pdf.set_text_color(*TEXT_PRIMARY)
        _safe_multicell(pdf, width=content_width, line_height=6, text=info_line, align="L")
        pdf.ln(2)

    pdf.set_font(body_family, "", 12)
    pdf.set_text_color(*TEXT_PRIMARY)

    def height_for_block(block: dict) -> float:
        btype = block.get("type")
        btext = block.get("text", "")
        if btype == "heading":
            pdf.set_font(_font_for_text(btext, heading_family=heading_family, body_family=body_family, emoji_family=emoji_family), "B", 13)
            return _estimate_multiline_height(pdf, text=btext, width=content_width, line_height=7) + 2
        if btype == "li" or re.match(r"^[\\s•·\\-]+", btext):
            pdf.set_font(_font_for_text(btext, heading_family=body_family, body_family=body_family, emoji_family=emoji_family), "", 12)
            return _estimate_multiline_height(pdf, text=re.sub(r\"^[\\s•·\\-]+\", \"\", btext, count=1).lstrip(), width=content_width - 8, line_height=7) + 3
        if btype == "hr":
            return 4
        pdf.set_font(_font_for_text(btext, heading_family=body_family, body_family=body_family, emoji_family=emoji_family), "", 12)
        return _estimate_multiline_height(pdf, text=btext, width=content_width, line_height=7) + 2

    def ensure_space(needed: float):
        if pdf.get_y() + needed <= pdf.h - pdf.b_margin:
            return
        pdf.add_page()
        pdf.set_x(content_x)

    if is_html:
        for idx, blk in enumerate(html_blocks):
            btype = blk.get("type")
            btext = blk.get("text", "")
            if btype == "paragraph" and re.match(r"^[\\s•·\\-]+", btext):
                btype = "li"
                btext = re.sub(r"^[\\s•·\\-]+", "", btext, count=1).lstrip()
            # Keep heading with next block if possible
            if btype == "heading":
                next_block = html_blocks[idx + 1] if idx + 1 < len(html_blocks) else None
                needed = height_for_block(blk) + (height_for_block(next_block) if next_block else 0)
                ensure_space(needed + 2)
            else:
                ensure_space(height_for_block(blk))
            pdf.set_x(content_x)
            if btype == "heading":
                pdf.set_font(_font_for_text(btext, heading_family=heading_family, body_family=body_family, emoji_family=emoji_family), "B", 13)
                pdf.set_text_color(*TEXT_PRIMARY)
                _safe_multicell(pdf, width=content_width, line_height=7, text=btext, align="L")
                pdf.set_font(body_family, "", 12)
                pdf.ln(2)
            elif btype == "li":
                clean = re.sub(r"^[\\s•·\\-]+", "", btext, count=1).lstrip()
                y = pdf.get_y()
                pdf.set_x(content_x)
                pdf.set_fill_color(*ACCENT_GOLD)
                pdf.set_draw_color(*ACCENT_GOLD)
                pdf.ellipse(pdf.get_x(), y + 2, 3, 3, style="F")
                pdf.set_x(content_x + 6)
                font_for_block = _font_for_text(clean, heading_family=body_family, body_family=body_family, emoji_family=emoji_family)
                pdf.set_font(font_for_block, "", 12)
                pdf.set_text_color(*TEXT_PRIMARY)
                _safe_multicell(pdf, width=content_width - 8, line_height=7, text=clean, align="J")
                pdf.ln(1)
            elif btype == "hr":
                pdf.ln(2)
            else:
                font_for_block = _font_for_text(btext, heading_family=body_family, body_family=body_family, emoji_family=emoji_family)
                pdf.set_font(font_for_block, "", 12)
                pdf.set_text_color(*TEXT_PRIMARY)
                _safe_multicell(pdf, width=content_width, line_height=7, text=btext, align="J")
                pdf.ln(2)
    else:
        # Treat leading bullet markers inside paragraphs as list items to avoid double bullets.
        for block in paragraphs:
            if re.match(r"^[\\s•·\\-]+", block):
                clean = re.sub(r"^[\\s•·\\-]+", "", block, count=1).lstrip()
                pdf.set_x(content_x)
                ensure_space(height_for_block({"type": "li", "text": clean}))
                y = pdf.get_y()
                pdf.set_fill_color(*ACCENT_GOLD)
                pdf.set_draw_color(*ACCENT_GOLD)
                pdf.ellipse(pdf.get_x(), y + 2, 3, 3, style="F")
                pdf.set_x(content_x + 6)
                font_for_block = _font_for_text(clean, heading_family=body_family, body_family=body_family, emoji_family=emoji_family)
                pdf.set_font(font_for_block, "", 12)
                _safe_multicell(pdf, width=content_width - 8, line_height=7, text=clean, align="J")
                pdf.ln(1)
            else:
                pdf.set_x(content_x)
                ensure_space(height_for_block({"type": "paragraph", "text": block}))
                font_for_block = _font_for_text(block, heading_family=body_family, body_family=body_family, emoji_family=emoji_family)
                pdf.set_font(font_for_block, "", 12)
                _safe_multicell(pdf, width=content_width, line_height=7, text=block, align="J")
                pdf.ln(2)
        for item in bullets:
            clean = re.sub(r"^[\\s•·\\-]+", "", item, count=1).lstrip()
            pdf.set_x(content_x)
            ensure_space(height_for_block({"type": "li", "text": clean}))
            y = pdf.get_y()
            pdf.set_fill_color(*ACCENT_GOLD)
            pdf.set_draw_color(*ACCENT_GOLD)
            pdf.ellipse(pdf.get_x(), y + 2, 3, 3, style="F")
            pdf.set_x(content_x + 6)
            font_for_block = _font_for_text(clean, heading_family=body_family, body_family=body_family, emoji_family=emoji_family)
            pdf.set_font(font_for_block, "", 12)
            _safe_multicell(pdf, width=content_width - 8, line_height=7, text=clean, align="J")
            pdf.ln(1)

    pdf.ln(2)
    date_line = (forecast_date or "").strip() or dt.datetime.now().strftime("%d %B %Y")
    pdf.set_font(heading_family, "", 10)
    pdf.set_text_color(*TEXT_SECONDARY)
    if date_line:
        pdf.set_x(content_x)
        _safe_multicell(pdf, width=content_width, line_height=6, text=date_line, align="R")

    raw = pdf.output(dest="S")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return raw.encode("latin-1")
