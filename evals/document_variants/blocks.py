"""Small flowable helpers shared by the renderers."""

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from evals.document_variants.pdfkit import FAMILIES, Look, mm


def P(text: str, style, *, raw: bool = False) -> Paragraph:
    """Paragraph with escaped text; `raw=True` lets the caller pass reportlab markup such as <b>."""
    body = text if raw else escape(text)
    return Paragraph(body.replace("\n", "<br/>"), style)


def sentence_end(text: str) -> str:
    """Close a sentence without doubling the full stop of an abbreviation such as "sp. z o.o."."""
    return text if text.endswith(".") else f"{text}."


def gap(height_mm: float = 3) -> Spacer:
    return Spacer(1, height_mm * mm)


def rule(width: str = "100%", thickness: float = 0.6, color=colors.black) -> HRFlowable:
    return HRFlowable(width=width, thickness=thickness, color=color, spaceBefore=2, spaceAfter=4)


def grid(
    rows: list[list], widths: list[float], *, lines: str = "none", pad: float = 2.5, valign: str = "TOP", extra=()
) -> Table:
    """Table whose cells are strings or flowables. `lines`: none, grid, box, under (rule below each row)."""
    commands = [
        ("VALIGN", (0, 0), (-1, -1), valign),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]
    edge = (0.5, colors.Color(0.35, 0.35, 0.35))
    if lines == "grid":
        commands.append(("GRID", (0, 0), (-1, -1), *edge))
    elif lines == "box":
        commands.append(("BOX", (0, 0), (-1, -1), *edge))
    elif lines == "under":
        commands.append(("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.Color(0.6, 0.6, 0.6)))
    table = Table(rows, colWidths=[w * mm for w in widths], hAlign="LEFT")
    table.setStyle(TableStyle([*commands, *extra]))
    return table


def leader(
    label: str, value: str, look: Look, width_mm: float, *, dot: str = ".", bold_value: bool = False
) -> Paragraph:
    """`LABEL ........ value`: dots fill the line to the value, as on till-slip style receipts."""
    font = FAMILIES[look.family]
    avail = width_mm * mm - stringWidth(f"{label}  {value} ", font, look.size)
    dots = dot * max(3, int(avail / stringWidth(dot, font, look.size)))
    value_markup = f"<b>{escape(value)}</b>" if bold_value else escape(value)
    return Paragraph(f"{escape(label)} {dots} {value_markup}", look.style("leader", spaceAfter=1))
