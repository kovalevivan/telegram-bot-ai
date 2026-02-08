from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import Iterable

from PIL import Image
from fpdf import FPDF


ACCENT_GOLD = (231, 193, 117)
ACCENT_TEAL = (88, 195, 184)
HEADER_DEEP = (14, 19, 42)
HEADER_NIGHT = (28, 35, 66)
CARD_BG = (246, 248, 254)
TEXT_PRIMARY = (26, 31, 45)
TEXT_SECONDARY = (94, 104, 128)


def _register_fonts(pdf: FPDF, *, regular_path: str | None, bold_path: str | None) -> str:
    """
    Register Unicode fonts for PDF rendering.
    Returns the font family name to use (or falls back to Helvetica if missing).
    """
    regular = Path(regular_path) if regular_path else None
    bold = Path(bold_path) if bold_path else None
    if regular and regular.exists():
        family = "DailyMind"
        pdf.add_font(family, "", str(regular), uni=True)
        pdf.add_font(family, "B", str(bold if bold and bold.exists() else regular), uni=True)
        return family
    return "Helvetica"


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
) -> bytes:
    """
    Render a branded DailyMind PDF and return raw bytes.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)

    font_family = _register_fonts(pdf, regular_path=font_path_regular, bold_path=font_path_bold)
    pdf.add_page()

    header_height = _draw_header(pdf, logo_path=logo_path)
    body_y = header_height + 8

    headline, bullets, paragraphs = _parse_text(text)

    content_x = 22
    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    start_y = body_y + 8

    # Estimate card height before drawing background
    pdf.set_font(font_family, "B", 16)
    headline_height = _estimate_multiline_height(pdf, text=headline or title or "DailyMind", width=content_width, line_height=8)

    pdf.set_font(font_family, "", 11)
    date_line = dt.datetime.now().strftime("%d %B %Y")
    date_height = 6 if date_line else 0

    info_rows = []
    if birth_date:
        info_rows.append(("Дата рождения", birth_date))
    if birth_time:
        info_rows.append(("Время рождения", birth_time))
    if birth_city:
        info_rows.append(("Город", birth_city))
    info_height = len(info_rows) * 6

    pdf.set_font(font_family, "", 12)
    bullet_height = 0.0
    for item in bullets:
        bullet_height += _estimate_multiline_height(pdf, text=item, width=content_width - 12, line_height=7) + 3

    paragraph_height = 0.0
    for block in paragraphs:
        paragraph_height += _estimate_multiline_height(pdf, text=block, width=content_width, line_height=7) + 2

    content_height = (
        headline_height
        + 4
        + date_height
        + (3 if info_rows else 0)
        + info_height
        + (6 if bullets else 0)
        + bullet_height
        + (6 if paragraphs else 0)
        + paragraph_height
        + 12  # footer hint
    )
    card_height = max(60.0, content_height + 12)

    pdf.set_y(body_y)
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(226, 232, 246)
    pdf.set_line_width(0.2)
    pdf.rect(x=14, y=body_y, w=182, h=card_height, style="FD")

    pdf.set_xy(content_x, start_y)
    pdf.set_font(font_family, "B", 16)
    pdf.set_text_color(*TEXT_PRIMARY)
    pdf.multi_cell(w=0, h=8, txt=headline or title or "DailyMind", align="L")

    pdf.set_font(font_family, "", 11)
    pdf.set_text_color(*TEXT_SECONDARY)
    pdf.cell(w=0, h=6, txt=date_line, ln=1)
    pdf.ln(2)

    if info_rows:
        pdf.set_font(font_family, "", 10)
        pdf.set_text_color(*TEXT_PRIMARY)
        for label, value in info_rows:
            pdf.cell(w=0, h=6, txt=f"{label}: {value}", ln=1)
        pdf.ln(2)

    if bullets:
        pdf.set_font(font_family, "B", 12)
        pdf.set_text_color(*TEXT_PRIMARY)
        pdf.cell(w=0, h=7, txt="Ключевые моменты", ln=1)
        pdf.ln(2)

        for item in bullets:
            y = pdf.get_y()
            pdf.set_fill_color(*ACCENT_GOLD)
            pdf.set_draw_color(*ACCENT_GOLD)
            pdf.ellipse(pdf.l_margin, y + 2, 4, 4, style="F")
            pdf.set_xy(pdf.l_margin + 8, y)
            pdf.set_font(font_family, "", 12)
            pdf.set_text_color(*TEXT_PRIMARY)
            pdf.multi_cell(w=0, h=7, txt=item, align="L")
            pdf.ln(1)
        pdf.ln(2)

    if paragraphs:
        pdf.set_font(font_family, "B", 12)
        pdf.set_text_color(*TEXT_PRIMARY)
        pdf.cell(w=0, h=7, txt="Расшифровка", ln=1)
        pdf.ln(1)
        _multi_paragraph(pdf, font_family=font_family, text_blocks=paragraphs)

    pdf.ln(2)
    pdf.set_font(font_family, "", 10)
    pdf.set_text_color(*TEXT_SECONDARY)
    pdf.multi_cell(
        w=0,
        h=6,
        txt="Совет: сохраните PDF, чтобы вернуться к рекомендациям позже.",
        align="L",
    )

    raw = pdf.output(dest="S")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return raw.encode("latin-1")
