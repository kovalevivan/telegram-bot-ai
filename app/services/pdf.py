from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Iterable

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


def _draw_header(pdf: FPDF, *, font_family: str, logo_path: str | None) -> None:
    pdf.set_fill_color(*HEADER_DEEP)
    pdf.rect(x=0, y=0, w=210, h=82, style="F")
    pdf.set_fill_color(*HEADER_NIGHT)
    pdf.rect(x=0, y=40, w=210, h=42, style="F")

    # Underlay glow
    pdf.set_draw_color(72, 86, 138)
    pdf.set_line_width(0.3)
    pdf.ellipse(x=120, y=6, w=80, h=40)
    pdf.ellipse(x=145, y=14, w=52, h=32)

    logo_size = 42
    logo_x = 18
    logo_y = 18
    logo = Path(logo_path) if logo_path else None
    if logo and logo.exists():
        pdf.image(str(logo), x=logo_x, y=logo_y, w=logo_size)
    else:
        # Fallback: simple constellations ring
        pdf.set_draw_color(*ACCENT_GOLD)
        pdf.set_line_width(1.2)
        pdf.ellipse(x=logo_x, y=logo_y, w=logo_size, h=logo_size)
        pdf.set_line_width(0.6)
        pdf.ellipse(x=logo_x + 8, y=logo_y + 8, w=logo_size - 16, h=logo_size - 16)
        pdf.set_draw_color(*ACCENT_TEAL)
        pdf.set_line_width(0.8)
        pdf.line(logo_x + 12, logo_y + 26, logo_x + 22, logo_y + 16)
        pdf.line(logo_x + 22, logo_y + 16, logo_x + 33, logo_y + 20)
        pdf.line(logo_x + 33, logo_y + 20, logo_x + 28, logo_y + 32)
        pdf.set_fill_color(*ACCENT_TEAL)
        for cx, cy in [(logo_x + 12, logo_y + 26), (logo_x + 22, logo_y + 16), (logo_x + 33, logo_y + 20), (logo_x + 28, logo_y + 32)]:
            pdf.ellipse(cx, cy, 3.6, 3.6, style="F")

    pdf.set_xy(logo_x + logo_size + 8, 22)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font_family, "B", 26)
    pdf.cell(w=0, h=12, txt="DailyMind", ln=2)
    pdf.set_font(font_family, "", 12)
    pdf.set_text_color(221, 225, 236)
    pdf.cell(w=0, h=8, txt="Гороскоп на день", ln=1)
    pdf.ln(2)
    pdf.set_text_color(179, 190, 221)
    pdf.set_font(font_family, "", 10)
    pdf.cell(w=0, h=6, txt="Создано искусственным интеллектом специально для вас", ln=1)


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
    title: str = "Гороскоп на день",
) -> bytes:
    """
    Render a branded DailyMind PDF and return raw bytes.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)

    font_family = _register_fonts(pdf, regular_path=font_path_regular, bold_path=font_path_bold)
    pdf.add_page()

    _draw_header(pdf, font_family=font_family, logo_path=logo_path)

    pdf.set_y(86)
    pdf.set_fill_color(*CARD_BG)
    pdf.set_draw_color(226, 232, 246)
    pdf.set_line_width(0.2)
    pdf.rect(x=14, y=86, w=182, h=185, style="FD")

    headline, bullets, paragraphs = _parse_text(text)

    pdf.set_xy(22, 96)
    pdf.set_font(font_family, "B", 16)
    pdf.set_text_color(*TEXT_PRIMARY)
    pdf.cell(w=0, h=9, txt=headline or title, ln=1)

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
        txt="Совет: сохраните PDF, чтобы вернуться к рекомендациям позже. Generated by DailyMind AI.",
        align="L",
    )

    raw = pdf.output(dest="S")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return raw.encode("latin-1")
