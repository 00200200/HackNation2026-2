"""reportlab glue: vendored DejaVu fonts, paragraph styles and a one- or two-column page builder."""

import io
from dataclasses import dataclass
from pathlib import Path

from reportlab import rl_config
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, PageTemplate

rl_config.invariant = 1  # no timestamps or random ids: the same seed gives the same bytes
FONT_DIR = Path(__file__).parent / "fonts"
FAMILIES = {"sans": "DejaVuSans", "serif": "DejaVuSerif", "mono": "DejaVuSansMono"}
ALIGN = {"left": TA_LEFT, "right": TA_RIGHT, "center": TA_CENTER, "justify": TA_JUSTIFY}
PAGE_SIZES = {"a4": A4, "letter": LETTER}


def register_fonts() -> None:
    for family in FAMILIES.values():
        if family not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(family, FONT_DIR / f"{family}.ttf"))
            pdfmetrics.registerFont(TTFont(f"{family}-Bold", FONT_DIR / f"{family}-Bold.ttf"))
            pdfmetrics.registerFontFamily(
                family, normal=family, bold=f"{family}-Bold", italic=family, boldItalic=f"{family}-Bold"
            )


@dataclass(frozen=True)
class Rendered:
    """One generated PDF with its reference JSON ({} for a negative) and the tags of every choice made."""

    pdf: bytes
    gold: dict
    tags: dict[str, str]


@dataclass(frozen=True)
class Look:
    """Typography of one document: font family, size, page size and how the text is aligned."""

    family: str = "sans"
    size: float = 9.5
    page: str = "a4"
    align: str = "left"
    margin_mm: float = 20

    def style(self, name: str = "body", **overrides) -> ParagraphStyle:
        font = FAMILIES[self.family]
        base = {
            "name": name,
            "fontName": font,
            "fontSize": self.size,
            "leading": self.size * 1.35,
            "alignment": ALIGN[self.align],
            "spaceAfter": self.size * 0.45,
        }
        return ParagraphStyle(**{**base, **overrides})

    def bold(self, name: str = "bold", **overrides) -> ParagraphStyle:
        return self.style(name, fontName=f"{FAMILIES[self.family]}-Bold", **overrides)


def build_pdf(story: list, look: Look, *, columns: int = 1, footer: str = "", head: int = 0) -> bytes:
    """Lay `story` out on pages. With two columns, the first `head` flowables span the page width above the columns."""
    width, height = PAGE_SIZES[look.page]
    margin = look.margin_mm * mm
    inner_w, inner_h = width - 2 * margin, height - 2 * margin
    gap = 8 * mm

    def draw_footer(canvas, doc):
        if footer:
            canvas.saveState()
            canvas.setFont(FAMILIES[look.family], 7.5)
            canvas.drawCentredString(width / 2, margin / 2, footer.format(page=doc.page))
            canvas.restoreState()

    def frame(name: str, x: float, y: float, w: float, h: float) -> Frame:
        return Frame(x, y, w, h, id=name, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    templates = []
    if columns == 2:
        col_w = (inner_w - gap) / 2
        cols = [("c1", margin, col_w), ("c2", margin + col_w + gap, col_w)]
        later = [frame(n, x, margin, w, inner_h) for n, x, w in cols]
        if head:
            head_h = sum(f.wrap(inner_w, inner_h)[1] + f.getSpaceAfter() for f in story[:head]) + 3 * mm
            first = [frame("head", margin, margin + inner_h - head_h, inner_w, head_h)]
            first += [frame(n, x, margin, w, inner_h - head_h) for n, x, w in cols]
            story = [*story[:head], FrameBreak(), *story[head:]]
        else:
            first = later
        templates.append(PageTemplate(id="first", frames=first, onPage=draw_footer, autoNextPageTemplate="later"))
        templates.append(PageTemplate(id="later", frames=later, onPage=draw_footer))
    else:
        main = [frame("main", margin, margin, inner_w, inner_h)]
        templates.append(PageTemplate(id="first", frames=main, onPage=draw_footer))
    out = io.BytesIO()
    doc = BaseDocTemplate(out, pagesize=(width, height), pageTemplates=templates, title="", author="", invariant=1)
    doc.build(story)
    return out.getvalue()


register_fonts()  # before any Paragraph is built: reportlab resolves <b> through the registered families

__all__ = ["FrameBreak", "Look", "Rendered", "build_pdf", "mm"]
