"""
Shelf Tag PDF Generator

Generates printable shelf tags on Avery 8371 business-card layout
(3.5" x 2", 10 per letter-size sheet, 2 columns x 5 rows).

Layout per card:
  Top 1.5" -- customer name + product name, auto-sized to largest readable font
  Bottom 0.5" -- SKU (small) + Code 39 barcode encoding the SKU
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

import barcode
from barcode.writer import ImageWriter
from fpdf import FPDF

logger = logging.getLogger(__name__)

_CODE39_CHARS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%")

# ---------------------------------------------------------------------------
# Avery 8371 layout constants (millimetres)
# ---------------------------------------------------------------------------
PAGE_W = 215.9  # 8.5"
PAGE_H = 279.4  # 11"
CARD_W = 88.9   # 3.5"
CARD_H = 50.8   # 2"
COLS = 2
ROWS = 5
MARGIN_LEFT = (PAGE_W - COLS * CARD_W) / 2   # ~19.05 mm (0.75")
MARGIN_TOP = (PAGE_H - ROWS * CARD_H) / 2    # ~12.7 mm  (0.5")
CELL_PAD = 2.5  # inner padding within each card

TOP_ZONE_H = 38.1    # 1.5"
BOTTOM_ZONE_H = 12.7  # 0.5"


def _generate_barcode_png(value: str) -> bytes:
    """Return a Code 39 barcode as PNG bytes for the given value (no text)."""
    code39_cls = barcode.get_barcode_class("code39")
    code39 = code39_cls(value, writer=ImageWriter(), add_checksum=False)
    buf = io.BytesIO()
    code39.write(buf, options={
        "module_width": 0.3,
        "module_height": 8.0,
        "font_size": 0,
        "write_text": False,
        "quiet_zone": 2,
    })
    return buf.getvalue()


def _barcode_value_for_product(product: Dict[str, Any]) -> str:
    """Prefer SKU for Code 39, falling back to DB id when SKU cannot be encoded."""
    sku = str(product.get("sku") or "").upper()
    if sku and all(ch in _CODE39_CHARS for ch in sku):
        return sku
    return str(product.get("id") or sku)


_UNICODE_REPLACEMENTS = {
    "\u2013": "-",   # en-dash
    "\u2014": "--",  # em-dash
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2026": "...", # ellipsis
    "\u00a0": " ",   # non-breaking space
    "\u00ae": "(R)", # registered
    "\u2122": "(TM)",# trademark
    "\u00b0": "deg", # degree
}


def _sanitize_for_pdf(text: str) -> str:
    """Replace Unicode characters unsupported by Helvetica with ASCII equivalents."""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _auto_size_text(
    pdf: FPDF, text: str, max_width: float, max_pt: int, min_pt: int, bold: bool = True,
) -> int:
    """Find the largest font size where text fits in one line within max_width."""
    style = "B" if bold else ""
    for pt in range(max_pt, min_pt - 1, -1):
        pdf.set_font("Helvetica", style, pt)
        if pdf.get_string_width(text) <= max_width:
            return pt
    return min_pt


def _fit_and_truncate(
    pdf: FPDF, text: str, max_width: float, max_pt: int, min_pt: int, bold: bool = True,
) -> str:
    """Auto-size font and truncate text with '...' if it still overflows at min_pt."""
    text = _sanitize_for_pdf(text)
    pt = _auto_size_text(pdf, text, max_width, max_pt, min_pt, bold)
    style = "B" if bold else ""
    pdf.set_font("Helvetica", style, pt)
    if pdf.get_string_width(text) <= max_width:
        return text
    while len(text) > 1 and pdf.get_string_width(text + "...") > max_width:
        text = text[:-1]
    return text + "..."


def generate_tags_pdf(products: List[Dict[str, Any]]) -> bytes:
    """Generate an Avery 8371 PDF containing one tag per product.

    Returns the raw PDF bytes ready for streaming to the client.
    """
    pdf = FPDF(unit="mm", format="letter")
    pdf.set_auto_page_break(auto=False)

    tag_index = 0

    for product in products:
        slot = tag_index % (COLS * ROWS)
        if slot == 0:
            pdf.add_page()

        col = slot % COLS
        row = slot // COLS

        x0 = MARGIN_LEFT + col * CARD_W + CELL_PAD
        y0 = MARGIN_TOP + row * CARD_H + CELL_PAD
        usable_w = CARD_W - 2 * CELL_PAD
        bottom_zone_y = y0 + TOP_ZONE_H

        # =================================================================
        # TOP ZONE (1.5"): customer name + product name, auto-sized
        # =================================================================

        customer_text = _fit_and_truncate(
            pdf, product.get("customer_name", ""), usable_w, 18, 10, bold=True,
        )
        customer_pt = _auto_size_text(
            pdf, customer_text, usable_w, 18, 10, bold=True,
        )
        customer_line_h = customer_pt * 0.4  # approximate mm per pt

        product_name = _fit_and_truncate(
            pdf, product.get("name", ""), usable_w, 22, 10, bold=True,
        )
        product_pt = _auto_size_text(
            pdf, product_name, usable_w, 22, 10, bold=True,
        )
        product_line_h = product_pt * 0.4

        total_text_h = customer_line_h + product_line_h + 2  # 2mm gap
        text_start_y = y0 + (TOP_ZONE_H - total_text_h) / 2

        pdf.set_font("Helvetica", "B", customer_pt)
        pdf.set_xy(x0, text_start_y)
        pdf.cell(usable_w, customer_line_h, customer_text, align="L")

        pdf.set_font("Helvetica", "B", product_pt)
        pdf.set_xy(x0, text_start_y + customer_line_h + 2)
        pdf.cell(usable_w, product_line_h, product_name, align="L")

        # =================================================================
        # BOTTOM ZONE (0.5"): SKU + barcode
        # =================================================================

        sku_line = _sanitize_for_pdf(product.get("sku", ""))
        if product.get("unit_type") == "pack" and product.get("pack_size"):
            sku_line += f"  |  Pack of {product['pack_size']}"

        pdf.set_font("Helvetica", "", 7)
        pdf.set_xy(x0, bottom_zone_y)
        pdf.cell(usable_w, 3.5, sku_line, align="L")

        try:
            barcode_value = _barcode_value_for_product(product)
            bc_png = _generate_barcode_png(barcode_value)
            bc_stream = io.BytesIO(bc_png)
            bc_w = 50
            bc_h = 8
            bc_x = x0 + (usable_w - bc_w) / 2
            bc_y = bottom_zone_y + 3.5
            pdf.image(bc_stream, x=bc_x, y=bc_y, w=bc_w, h=bc_h)
        except Exception:
            logger.exception("Failed to generate barcode for product %s", product.get("id"))
            pdf.set_font("Helvetica", "", 6)
            pdf.set_xy(x0, bottom_zone_y + 3.5)
            pdf.cell(usable_w, 3, f"[barcode error: {product.get('id')}]", align="C")

        tag_index += 1

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
