"""Render case PDFs and capture the positions printed on each native A4 page.

Coordinates and bounding boxes use PDF points from the upper left. Page indices
start at zero. A section can have one bounding box on each page it occupies.
"""

import os
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from evals.variant_pages import polish_font


class Page:
    def __init__(self, path):
        # Use the same invariant timestamp as the variant renderer, including in CI.
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": ""}):
            self.canvas = Canvas(str(path), pagesize=A4, invariant=True)
        self.width, self.height = A4
        self.page_index = 0
        self.sections = []
        self.value_boxes = []
        self._section_name = None
        self._section_box = None

    def section(self, name):
        self._section_name = name
        self._section_box = None

    def _extend_section(self, box):
        if self._section_name is None:
            return
        if self._section_box is None:
            self._section_box = list(box)
            self.sections.append({"name": self._section_name, "page": self.page_index, "bbox": self._section_box})
            return
        left, top, right, bottom = self._section_box
        self._section_box[:] = [min(left, box[0]), min(top, box[1]), max(right, box[2]), max(bottom, box[3])]

    @staticmethod
    def _font(bold, mono):
        face = "Courier" if mono else "Helvetica"
        return polish_font(face + ("-Bold" if bold else ""))

    def measure(self, text, *, size=10, bold=False, mono=False):
        return pdfmetrics.stringWidth(text, self._font(bold, mono), size)

    def text(self, x, y, text, *, size=10, bold=False, width=470, role=None, mono=False):
        """Draw wrapped text starting at the top of its first line and return the next y."""
        font = self._font(bold, mono)
        self.canvas.setFont(font, size)
        for paragraph in text.split("\n"):
            for line in simpleSplit(paragraph, font, size, width) or [""]:
                if line:
                    baseline = y + size
                    self.canvas.drawString(x, self.height - baseline, line)
                    end = x + pdfmetrics.stringWidth(line, font, size)
                    box = [round(float(n), 3) for n in (x, y, end, baseline + size * 0.23)]
                    self._extend_section(box)
                    if role:
                        self.value_boxes.append({"role": role, "page": self.page_index, "bbox": box, "text": line})
                y += size * 1.3
        return y

    def line(self, x1, y1, x2, y2):
        self.canvas.setStrokeGray(0.55)
        self.canvas.setLineWidth(0.55)
        self.canvas.line(x1, self.height - y1, x2, self.height - y2)
        self._extend_section([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])

    def new_page(self):
        self.canvas.showPage()
        self.page_index += 1
        self._section_box = None

    def finish(self):
        self.canvas.showPage()
        self.canvas.save()
        return {
            "page_count": self.page_index + 1,
            "sections": self.sections,
            "role_ids": sorted({item["role"] for item in self.value_boxes}),
            "value_boxes": self.value_boxes,
        }
