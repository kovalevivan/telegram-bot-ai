from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Iterable

from html import unescape

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
    pass


def _register_fonts(
    pdf: FPDF,
    *,
    heading_regular: str | None,
    heading_bold: str | None,
    body_regular: str | None,
    body_bold: str | None,
    body_italic: str | None,
    body_bold_italic: str | None,
) -> tuple[str, str]:
    """
    Register Unicode fonts for PDF rendering.
    Returns (heading_family, body_family).
    """
    heading_family = "Helvetica"
    body_family = "Helvetica"

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

    return heading_family, body_family


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
    return s


def _looks_like_html(s: str) -> bool:
    return bool(re.search(r"<[a-zA-Z][^>]*>", s or ""))


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

    heading_family, body_family = _register_fonts(
        pdf,
        heading_regular=font_path_regular,
        heading_bold=font_path_bold,
        body_regular=settings.pdf_body_font_path,
        body_bold=settings.pdf_body_font_bold_path,
        body_italic=settings.pdf_body_font_italic_path,
        body_bold_italic=settings.pdf_body_font_bold_italic_path,
    )
    pdf.add_page()

    header_height = _draw_header(pdf, logo_path=logo_path)
    body_y = header_height + 8

    def draw_background():
        h = max(40.0, pdf.h - body_y - pdf.b_margin)
        pdf.set_fill_color(*CARD_BG)
        pdf.set_draw_color(226, 232, 246)
        pdf.set_line_width(0.2)
        pdf.rect(x=14, y=body_y, w=182, h=h, style="FD")

    draw_background()

    is_html = _looks_like_html(text)
    sanitized_html = _sanitize_html(text) if is_html else ""
    text_for_height = _html_to_text(text) if is_html else text

    headline, bullets, paragraphs = _parse_text(text_for_height)

    content_x = 22
    content_width = pdf.w - content_x - pdf.r_margin
    start_y = body_y + 8

    render_headline = not is_html

    # Estimate card height before drawing background
    pdf.set_font(heading_family, "B", 16)
    headline_height = (
        _estimate_multiline_height(pdf, text=headline or title or "DailyMind", width=content_width, line_height=8)
        if render_headline
        else 0
    )

    pdf.set_font(heading_family, "", 11)
    date_line = (forecast_date or "").strip() or dt.datetime.now().strftime("%d %B %Y")
    date_height = 6 if date_line else 0

    info_chunks = []
    if birth_date:
        info_chunks.append(f"Дата рождения: {birth_date}")
    if birth_time:
        info_chunks.append(f"Время рождения: {birth_time}")
    if birth_city:
        info_chunks.append(f"Город: {birth_city}")
    info_line = "  •  ".join(info_chunks)
    info_height = 6 if info_line else 0

    pdf.set_font(body_family, "", 12)
    bullet_height = 0.0
    paragraph_height = 0.0
    html_height = 0.0
    if is_html:
        plain = text_for_height or ""
        html_height = _estimate_multiline_height(pdf, text=plain, width=content_width, line_height=7) + 4
    else:
        for item in bullets:
            bullet_height += _estimate_multiline_height(pdf, text=item, width=content_width - 10, line_height=7) + 3
        for block in paragraphs:
            paragraph_height += _estimate_multiline_height(pdf, text=block, width=content_width, line_height=7) + 2

    def ensure_space(needed: float):
        if pdf.get_y() + needed <= pdf.h - pdf.b_margin:
            return
        pdf.add_page()
        # Use plain background on continuation pages
        _draw_header(pdf, logo_path=None)
        draw_background()
        pdf.set_y(body_y)

    pdf.set_xy(content_x, start_y)
    if render_headline:
        pdf.set_font(heading_family, "B", 16)
        pdf.set_text_color(*TEXT_PRIMARY)
        ensure_space(headline_height + 4)
        pdf.multi_cell(w=0, h=8, txt=headline or title or "DailyMind", align="L")

    if info_line:
        pdf.set_x(content_x)
        pdf.set_font(heading_family, "", 10)
        pdf.set_text_color(*TEXT_PRIMARY)
        ensure_space(info_height + 2)
        pdf.multi_cell(w=content_width, h=6, txt=info_line, align="L")
        pdf.ln(2)

    if is_html:
        pdf.set_font(body_family, "", 12)
        pdf.set_text_color(*TEXT_PRIMARY)
        ensure_space(html_height + 4)
        pdf.write_html(sanitized_html.replace("\n", "<br>"))
    else:
        if bullets:
            pdf.set_font(heading_family, "B", 12)
            pdf.set_text_color(*TEXT_PRIMARY)
            ensure_space(7 + 2)
            pdf.cell(w=0, h=7, txt="Ключевые моменты", ln=1)
            pdf.ln(2)

            for item in bullets:
                ensure_space(9)
                y = pdf.get_y()
                pdf.set_fill_color(*ACCENT_GOLD)
                pdf.set_draw_color(*ACCENT_GOLD)
                pdf.ellipse(pdf.l_margin, y + 2, 4, 4, style="F")
                pdf.set_xy(pdf.l_margin + 8, y)
                pdf.set_font(body_family, "", 12)
                pdf.set_text_color(*TEXT_PRIMARY)
                pdf.multi_cell(w=0, h=7, txt=item, align="L")
                pdf.ln(1)
            pdf.ln(2)

        if paragraphs:
            pdf.set_font(heading_family, "B", 12)
            pdf.set_text_color(*TEXT_PRIMARY)
            ensure_space(7 + 1)
            pdf.cell(w=0, h=7, txt="Расшифровка", ln=1)
            pdf.ln(1)
            for block in paragraphs:
                block_height = _estimate_multiline_height(pdf, text=block, width=content_width, line_height=7) + 2
                ensure_space(block_height)
                pdf.set_font(body_family, "", 12)
                pdf.set_text_color(*TEXT_PRIMARY)
                pdf.multi_cell(w=0, h=7, txt=block, align="J")
                pdf.ln(2)

    pdf.ln(2)
    ensure_space(6 if date_line else 0)
    pdf.set_font(heading_family, "", 10)
    pdf.set_text_color(*TEXT_SECONDARY)
    if date_line:
        pdf.ln(2)
        pdf.set_font(heading_family, "", 10)
        pdf.set_text_color(*TEXT_SECONDARY)
        pdf.cell(w=0, h=6, txt=date_line, ln=1, align="R")

    raw = pdf.output(dest="S")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return raw.encode("latin-1")
