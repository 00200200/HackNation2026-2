"""Assemble docs/pitch/index.html from project/deck.json and project/slides/*.html.

Run from anywhere: python docs/pitch/build.py
Slides reference images by paths relative to index.html. Export the PDF as described in README.md.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = "../../frontend/public/fonts"
LATIN = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
LATIN_EXT = "U+0100-02AF,U+0304,U+0308,U+0329,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"
FACES = [
    ("Geist", "geist-latin", LATIN),
    ("Geist", "geist-latin-ext", LATIN_EXT),
    ("Geist Mono", "geist-mono-latin", LATIN),
    ("Geist Mono", "geist-mono-latin-ext", LATIN_EXT),
]
PAGE_CSS = """@page { size: 1920px 1080px; margin: 0; }
* { margin:0 }
html, body { background:#1a1a1a; }
body > section { width:1920px; height:1080px; overflow:hidden; box-sizing:border-box; position:relative; isolation:isolate; margin:0 auto 24px; break-after:page; }
aside { display:none !important }
h1 { font-size:96px } h2 { font-size:64px } h3 { font-size:44px }
@media print { html, body { background:none; } body > section { margin:0; } .in, .fade { animation:none !important; } }"""


def font_face(family: str, file: str, ranges: str) -> str:
    return (
        f"@font-face {{ font-family:'{family}'; src:url({FONTS}/{file}.woff2) format('woff2'); "
        f"font-weight:100 900; unicode-range:{ranges}; }}"
    )


def build() -> str:
    deck = json.loads((HERE / "project" / "deck.json").read_text(encoding="utf-8"))
    slides = [
        (HERE / "project" / "slides" / f"{slide}.html").read_text(encoding="utf-8").strip() for slide in deck["order"]
    ]
    head = "\n".join([font_face(*face) for face in FACES] + [PAGE_CSS])
    return (
        '<!doctype html>\n<html lang="pl"><head><meta charset="utf-8">\n'
        f"<title>{deck['title']}</title>\n"
        '<meta name="viewport" content="width=1920">\n'
        '<link rel="stylesheet" href="project/deck.css">\n'
        f"<style>\n{head}\n</style>\n</head><body>\n" + "\n\n".join(slides) + "\n\n</body></html>\n"
    )


if __name__ == "__main__":
    (HERE / "index.html").write_text(build(), encoding="utf-8")
