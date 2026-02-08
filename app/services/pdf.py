from __future__ import annotations

import datetime as dt
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


def build_daily_mind_pdf(
    text: str,
    *,
    logo_path: str | None,
    font_path_regular: str | None,
    font_path_bold: str | None,
    title: str = "Гороскоп",
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
    pdf.set_y(body_y)
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(226, 232, 246)
    pdf.set_line_width(0.2)
    card_height = max(120, pdf.h - body_y - 18)
    pdf.rect(x=14, y=body_y, w=182, h=card_height, style="FD")

    headline, bullets, paragraphs = _parse_text(text)

    pdf.set_xy(22, body_y + 10)
    pdf.set_font(font_family, "B", 16)
    pdf.set_text_color(*TEXT_PRIMARY)
    pdf.multi_cell(w=0, h=8, txt=headline or title, align="L")

    pdf.set_font(font_family, "", 11)
    pdf.set_text_color(*TEXT_SECONDARY)
    pdf.cell(w=0, h=6, txt=f"{title} · {dt.datetime.now().strftime('%d %B %Y')}", ln=1)
    pdf.ln(4)

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
