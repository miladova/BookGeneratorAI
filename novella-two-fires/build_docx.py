#!/usr/bin/env python3
"""Build a 6x9 print-ready DOCX manuscript of TWO FIRES from the markdown chapters.

Usage:  python3 build_docx.py
Output: Two Fires - manuscript.docx
"""
import re
import pathlib

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

HERE = pathlib.Path(__file__).parent

FRONT = "00-front-matter.md"
CHAPTERS = [
    "01-the-dossier.md",
    "02-two-fires.md",
    "03-the-machine-and-the-willow.md",
    "04-what-the-living-do.md",
    "05-the-plank.md",
    "06-room-214.md",
    "07-the-file.md",
    "08-the-empty-church.md",
    "09-the-opinion.md",
    "10-the-second-fire.md",
]
BACK = "99-back-matter.md"

INLINE = re.compile(r"(\*\*.+?\*\*|\*.+?\*)")


def add_runs(par, text):
    """Add text to a paragraph, honouring **bold** and *italic*."""
    for chunk in INLINE.split(text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            r = par.add_run(chunk[2:-2])
            r.bold = True
        elif chunk.startswith("*") and chunk.endswith("*"):
            r = par.add_run(chunk[1:-1])
            r.italic = True
        else:
            par.add_run(chunk)


def body_par(doc, text, indent=True):
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    fmt.first_line_indent = Inches(0.22) if indent else Inches(0)
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1.38
    add_runs(p, text)
    return p


def centred(doc, text, size=11, italic=False, bold=False, before=0, after=0,
            spacing=1.0, caps=False):
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fmt.first_line_indent = Inches(0)
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = spacing
    r = p.add_run(text.upper() if caps else text)
    r.font.size = Pt(size)
    r.italic = italic
    r.bold = bold
    return p


def scene_break(doc):
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fmt.first_line_indent = Inches(0)
    fmt.space_before = Pt(10)
    fmt.space_after = Pt(10)
    r = p.add_run("*  *  *")
    r.font.size = Pt(11)


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def setup(doc):
    s = doc.sections[0]
    s.page_width = Inches(6)
    s.page_height = Inches(9)
    s.top_margin = Inches(0.75)
    s.bottom_margin = Inches(0.75)
    s.left_margin = Inches(0.75)
    s.right_margin = Inches(0.85)
    s.gutter = Inches(0.15)
    s.mirror_margins = True

    normal = doc.styles["Normal"]
    normal.font.name = "Garamond"
    normal.font.size = Pt(11.5)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), "Garamond")
    rfonts.set(qn("w:hAnsi"), "Garamond")
    rfonts.set(qn("w:eastAsia"), "Garamond")


def title_page(doc):
    for _ in range(5):
        doc.add_paragraph()
    centred(doc, "TWO FIRES", size=30, bold=True, after=8)
    centred(doc, "A Novella of Poland, 1958", size=13, italic=True, after=0)
    for _ in range(4):
        doc.add_paragraph()
    centred(doc, "A village has two fires: the one in the hearth\nand the one in the church.", size=10,
            italic=True, spacing=1.3)
    page_break(doc)

    centred(doc, "Two Fires", size=12, bold=True, after=4)
    centred(doc, "Copyright © 1958–1959 by the author. All rights reserved.", size=9, after=10)
    centred(
        doc,
        "This is a work of fiction. The historical setting is real; the people, "
        "parishes, villages and dioceses depicted are invented, and any resemblance "
        "to persons living or dead is coincidental. Real places are used fictitiously.",
        size=9, spacing=1.25,
    )
    for _ in range(2):
        doc.add_paragraph()
    centred(doc, "For everyone who carried a coal.", size=10, italic=True)
    page_break(doc)

    centred(doc, "Contents", size=14, bold=True, after=16)
    contents = [
        ("One", "The Dossier"),
        ("Two", "Two Fires"),
        ("Three", "The Machine and the Willow"),
        ("Four", "What the Living Do"),
        ("Five", "The Plank"),
        ("Six", "Room 214"),
        ("Seven", "The File"),
        ("Eight", "The Empty Church"),
        ("Nine", "The Opinion"),
        ("Ten", "The Second Fire"),
    ]
    for num, name in contents:
        p = doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.first_line_indent = Inches(0)
        fmt.left_indent = Inches(1.0)
        fmt.space_after = Pt(7)
        fmt.line_spacing = 1.0
        r = p.add_run(f"{num}  ·  ")
        r.font.size = Pt(10.5)
        r2 = p.add_run(name)
        r2.font.size = Pt(10.5)
        r2.italic = True
    page_break(doc)


def chapter(doc, path, number):
    lines = [ln.rstrip() for ln in path.read_text().splitlines()]
    title = None
    subhead = None
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("# ") and title is None:
            title = ln[2:].strip()
            # "Chapter One — The Dossier" -> "The Dossier"
            title = re.sub(r"^Chapter\s+\w+\s*[—–-]\s*", "", title)
            i += 1
            continue
        if ln.startswith("## ") and subhead is None:
            subhead = ln[3:].strip()
            i += 1
            continue
        break

    words = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN"]
    for _ in range(2):
        doc.add_paragraph()
    centred(doc, words[number], size=11, caps=True, after=6)
    centred(doc, title, size=21, bold=True, after=10)
    if subhead:
        centred(doc, subhead, size=10.5, italic=True, after=0)
    doc.add_paragraph()

    for ln in lines[i:]:
        s = ln.strip()
        if not s:
            continue
        if s == "---":
            scene_break(doc)
        elif s.startswith("## "):
            centred(doc, s[3:].strip(), size=10.5, italic=True, before=16, after=6, caps=True)
        elif s.startswith("# "):
            continue
        else:
            body_par(doc, s)


def back_matter(doc):
    page_break(doc)
    for ln in pathlib.Path(HERE / BACK).read_text().splitlines():
        s = ln.strip()
        if not s or s == "---":
            continue
        if s.startswith("## "):
            centred(doc, s[3:].strip(), size=13, bold=True, before=16, after=12)
        elif s.startswith("*") and s.endswith("*") and len(s) > 2:
            centred(doc, s.strip("*"), size=10, italic=True, after=18)
        else:
            body_par(doc, s, indent=False)
            doc.paragraphs[-1].paragraph_format.space_after = Pt(7)


def main():
    doc = Document()
    setup(doc)
    title_page(doc)
    for n, fn in enumerate(CHAPTERS, start=1):
        if n > 1:
            page_break(doc)
        chapter(doc, HERE / fn, n)
    back_matter(doc)
    out = HERE / "Two Fires - manuscript.docx"
    doc.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
