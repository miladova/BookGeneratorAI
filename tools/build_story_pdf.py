#!/usr/bin/env python3
"""Typeset 'The Fifth Officer' as a 6x9 trade-paperback interior PDF.

Deterministic build: no network, no LLM. Reads the markdown story and writes
stories/the-fifth-officer.pdf.

    python3 -m venv .venv-pdf
    .venv-pdf/bin/pip install reportlab fonttools brotli
    sh tools/fetch_fonts.sh
    .venv-pdf/bin/python tools/build_story_pdf.py

Layout: 6x9 trim, mirrored margins, running heads, generated table of contents,
PDF outline, small-caps-style chapter openings and a closing historical note.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)
from reportlab.platypus.tables import Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "stories" / "the-fifth-officer.md"
OUTPUT = ROOT / "stories" / "the-fifth-officer.pdf"
FONT_DIR = ROOT / ".assets" / "fonts"

PAGE_W, PAGE_H = 6 * inch, 9 * inch
MARGIN_INNER = 20 * mm
MARGIN_OUTER = 16 * mm
MARGIN_TOP = 18 * mm
MARGIN_BOTTOM = 20 * mm
TEXT_W = PAGE_W - MARGIN_INNER - MARGIN_OUTER

INK = HexColor("#141414")
GREY = HexColor("#6f6a62")
RULE = HexColor("#cdc6ba")
ORNAMENT = "\u00b7&nbsp;&nbsp;&nbsp;\u00b7&nbsp;&nbsp;&nbsp;\u00b7"
PAPER = HexColor("#fffdf8")

DROP_BEFORE = {1}  # chapters whose first paragraph gets a drop capital


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
def register_fonts() -> None:
    faces = {
        "Garamond": "eb-garamond-latin-400-normal.ttf",
        "Garamond-Italic": "eb-garamond-latin-400-italic.ttf",
        "Garamond-Semi": "eb-garamond-latin-600-normal.ttf",
        "Garamond-SemiItalic": "eb-garamond-latin-600-italic.ttf",
        "Garamond-Bold": "eb-garamond-latin-700-normal.ttf",
    }
    missing = [f for f in faces.values() if not (FONT_DIR / f).exists()]
    if missing:
        raise SystemExit(
            "Missing font files in .assets/fonts: "
            + ", ".join(missing)
            + "\nRun: sh tools/fetch_fonts.sh"
        )
    for name, filename in faces.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
    pdfmetrics.registerFontFamily(
        "Garamond",
        normal="Garamond",
        bold="Garamond-Bold",
        italic="Garamond-Italic",
        boldItalic="Garamond-SemiItalic",
    )


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
def build_styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle(
        "Body",
        fontName="Garamond",
        fontSize=12.4,
        leading=17.6,
        firstLineIndent=16,
        alignment=TA_JUSTIFY,
        textColor=INK,
        spaceBefore=0,
        spaceAfter=0,
        allowWidows=0,
        allowOrphans=0,
        # hyphenation off: at this measure (about 62 characters) justification
        # holds up, and nothing breaks a Welsh proper noun across a line
        hyphenationLang="",
        splitLongWords=0,
        uriWasteReduce=0.3,
    )
    small_caps = ParagraphStyle(
        "Small",
        parent=body,
        fontName="Garamond-Semi",
        fontSize=9.4,
        leading=12,
        alignment=TA_CENTER,
        firstLineIndent=0,
        textColor=GREY,
    )
    return {
        "body": body,
        "body_first": ParagraphStyle("BodyFirst", parent=body, firstLineIndent=0),
        "eyebrow": ParagraphStyle(
            "Eyebrow",
            parent=small_caps,
            spaceAfter=10,
        ),
        "chapter_title": ParagraphStyle(
            "ChapterTitle",
            fontName="Garamond",
            fontSize=23,
            leading=28,
            alignment=TA_CENTER,
            textColor=INK,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "ornament": ParagraphStyle(
            "Ornament",
            fontName="Garamond",
            fontSize=16,
            leading=24,
            alignment=TA_CENTER,
            textColor=GREY,
        ),
        "title": ParagraphStyle(
            "Title",
            fontName="Garamond",
            fontSize=36,
            leading=42,
            alignment=TA_CENTER,
            textColor=INK,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            fontName="Garamond-Italic",
            fontSize=14.5,
            leading=21,
            alignment=TA_CENTER,
            textColor=GREY,
        ),
        "epigraph": ParagraphStyle(
            "Epigraph",
            fontName="Garamond-Italic",
            fontSize=12.2,
            leading=19,
            alignment=TA_CENTER,
            textColor=INK,
        ),
        "note_body": ParagraphStyle(
            "NoteBody",
            parent=body,
            fontSize=10.9,
            leading=16.2,
            firstLineIndent=0,
            spaceAfter=9,
            alignment=TA_JUSTIFY,
        ),
        "imprint": ParagraphStyle(
            "Imprint",
            fontName="Garamond-Semi",
            fontSize=8.4,
            leading=12,
            alignment=TA_CENTER,
            textColor=GREY,
        ),
        "toc_entry": ParagraphStyle(
            "TocEntry",
            fontName="Garamond",
            fontSize=11.6,
            leading=17,
            textColor=INK,
        ),
        "toc_page": ParagraphStyle(
            "TocPage",
            fontName="Garamond",
            fontSize=11.6,
            leading=17,
            alignment=2,
            textColor=INK,
        ),
        "toc_title": ParagraphStyle(
            "TocTitle",
            fontName="Garamond",
            fontSize=19,
            leading=24,
            alignment=TA_CENTER,
            textColor=INK,
            spaceAfter=30,
        ),
    }


# --------------------------------------------------------------------------- #
# Inline markdown -> reportlab mini-HTML (with British typographic quotes)
# --------------------------------------------------------------------------- #
def smart(segment: str) -> str:
    """Typographic quotes. Markers (\x01-\x04) are skipped when reading context."""
    out = []
    last = " "
    for i, ch in enumerate(segment):
        if ch == "\x01" or ch == "\x03":
            last = " "  # an opening tag behaves like a space
            out.append(ch)
        elif ch == "\x02" or ch == "\x04":
            last = "a"  # a closing tag behaves like a letter
            out.append(ch)
        elif ch == '"':
            nxt = segment[i + 1] if i + 1 < len(segment) else " "
            closes = (
                nxt in " ,.;:?!)}\n\u2014\u201d"          # "sir," he said / stand back-"
                or last.isalnum()
                or last in ",.!?;:)\u2019\u201d"
            )
            out.append("\u201d" if closes else "\u201c")
            last = ch
        elif ch == "'":
            if last.isalnum():
                out.append("\u2019")
            elif last in " \u2014([{\u2018\u201c":
                out.append("\u2018")
            else:
                out.append("\u2019")
            last = ch
        else:
            out.append(ch)
            last = ch
    return "".join(out)


def inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace(" -- ", " \u2014 ").replace("--", "\u2014")
    text = re.sub(r"\*\*(.+?)\*\*", "\x01\\1\x02", text)        # bold marker
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", "\x03\\1\x04", text)  # italic marker
    text = smart(text)  # one pass, with markers standing in for tags
    text = text.replace("\x01", "<b>").replace("\x02", "</b>")
    text = text.replace("\x03", "<i>").replace("\x04", "</i>")
    return text


# --------------------------------------------------------------------------- #
# Markdown parsing
# --------------------------------------------------------------------------- #
CHAPTER_RE = re.compile(r"^([IVXLC]+)\.\s+(.*)$")


def parse(markdown: str) -> tuple[dict, list[dict], dict]:
    lines = markdown.splitlines()
    meta = {"title": "", "subtitle": "", "epigraph": ""}
    chapters: list[dict] = []
    note: dict = {"blocks": []}

    current: dict | None = None
    para: list[str] = []
    in_note = False
    in_quote = False

    def flush() -> None:
        nonlocal para, in_quote
        if not para:
            in_quote = False
            return
        text = " ".join(para)
        if in_note:
            note["blocks"].append(("quote" if in_quote else "para", text))
        elif current is not None:
            current["blocks"].append(("quote" if in_quote else "para", text))
        elif not meta["epigraph"]:
            meta["epigraph"] = text
        para = []
        in_quote = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("# "):
            if not meta["title"]:
                meta["title"] = line[2:].strip()
            else:
                in_note = True
                current = None
        elif line.startswith("### "):
            meta["subtitle"] = line[4:].strip()
        elif line.startswith("## "):
            flush()
            heading = line[3:].strip()
            if heading.lower().startswith("a note"):
                in_note = True
                current = None
            else:
                m = CHAPTER_RE.match(heading)
                current = {
                    "num": m.group(1) if m else "",
                    "title": m.group(2).strip() if m else heading,
                    "blocks": [],
                }
                chapters.append(current)
        elif line in {"---", "***", "___"}:
            flush()
        elif line.startswith(">"):
            if not in_quote and para:
                flush()
            para.append(line.lstrip("> ").strip())
            in_quote = True
        elif not line:
            flush()
        else:
            para.append(line)
    flush()
    return meta, chapters, note


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #
class StoryDoc(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        self.page_chapter = ""
        self.heading_pages: dict[str, int] = {}
        self.heading_titles: dict[str, str] = {}
        self.chapter_order: list[tuple[str, str]] = []

    def afterFlowable(self, flowable) -> None:
        if not getattr(flowable, "_toc_key", None):
            return
        key = flowable._toc_key
        text = flowable._toc_text
        if key not in self.heading_pages:
            self.chapter_order.append((key, text))
        self.heading_pages[key] = self.page
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=0, closed=False)
        self.notify("TOCEntry", (0, text, self.page, key))

    # page furniture ----------------------------------------------------
    def chapter_for_page(self, page: int) -> str:
        """Chapter running at the top of a page (stable from the second pass)."""
        current = ""
        for key, title in self.chapter_order:
            start = self.heading_pages.get(key)
            if start is not None and start <= page:
                current = title
            else:
                break
        return current

    def _report_hyphenation(self) -> None:
        pairs = [(getattr(f, "_hyphenations", 0), getattr(f, "_splitLongWordCount", 0))
                 for f in getattr(self, "_hyphenationFrags", [])]
        self._hyphenationTotals = (
            sum(p[0] for p in pairs), sum(p[1] for p in pairs)
        )

    def _paper(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFillColor(PAPER)
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canvas.restoreState()

    def _chrome(self, canvas, doc) -> None:
        page = canvas.getPageNumber()
        if page < 5:
            return
        if self.pageTemplate.id == "recto" and page in self.heading_pages.values():
            return  # chapter openings carry no running head
        canvas.saveState()
        is_left = self.pageTemplate.id == "verso"
        head_y = PAGE_H - MARGIN_TOP + 8.5 * mm
        canvas.setFont("Garamond-Semi", 7.8)
        canvas.setFillColor(GREY)
        canvas._charSpace = 1.15
        if is_left:
            text = "THE FIFTH OFFICER"
            canvas.drawString(MARGIN_INNER - 2 * mm, head_y, text.upper())
        else:
            text = self.chapter_for_page(page).upper()
            canvas.drawRightString(PAGE_W - MARGIN_INNER + 2 * mm, head_y, text)
        canvas._charSpace = 0
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.35)
        canvas.line(MARGIN_INNER - 2 * mm, head_y - 2.6 * mm,
                    PAGE_W - MARGIN_INNER + 2 * mm, head_y - 2.6 * mm)
        canvas.setFont("Garamond", 9.2)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(PAGE_W / 2, MARGIN_BOTTOM - 11 * mm, str(page))
        canvas.restoreState()


def recto_frame() -> Frame:
    return Frame(MARGIN_INNER, MARGIN_BOTTOM, TEXT_W, PAGE_H - MARGIN_TOP - MARGIN_BOTTOM,
                 id="recto", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)


def verso_frame() -> Frame:
    return Frame(MARGIN_OUTER, MARGIN_BOTTOM, TEXT_W, PAGE_H - MARGIN_TOP - MARGIN_BOTTOM,
                 id="verso", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)


def heading(flowable, key: str, text: str):
    flowable._toc_key = key
    flowable._toc_text = text
    return flowable


CAP_SIZE = 17.5


def initial_cap_para(raw: str, styles: dict) -> list:
    """Opening paragraph with a raised initial capital.

    reportlab grows only the first line box, so the opening paragraph gets its
    own slightly airier leading to keep the taller glyph clear of the second line.
    """
    text = raw.lstrip()
    style = ParagraphStyle(
        "Opening", parent=styles["body_first"], leading=styles["body"].leading + 3.2,
        spaceAfter=1.2,
    )
    if not text or text[0] in "*\u201c'\"([":
        return [Paragraph(inline(raw), style)]
    letter, rest = inline(text[0]), inline(text[1:])
    opening = f'<font name="Garamond" size="{CAP_SIZE}">{letter}</font>'
    return [Paragraph(opening + rest, style)]



def contents_page(entries: list[tuple[str, int]], styles: dict) -> list:
    """Static contents list with dotted leaders (numbers come from a first pass)."""
    rows = []
    for title, page in entries:
        rows.append([
            Paragraph(inline(title), styles["toc_entry"]),
            Paragraph(str(page) if page != "" else "&nbsp;", styles["toc_page"]),
        ])
    if not rows:
        rows = [[Paragraph("&nbsp;", styles["toc_entry"]), Paragraph("&nbsp;", styles["toc_page"])]]
    table = Table(rows, colWidths=[TEXT_W - 26, 26])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (0, -1), 0.55, RULE, None, (1, 2)),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    return [table]


def make_doc() -> StoryDoc:
    doc = StoryDoc(
        str(OUTPUT),
        pagesize=(PAGE_W, PAGE_H),
        title="The Fifth Officer",
        author="Arena Agent Mode",
        subject="A story of the Titanic, April 1912",
        creator="tools/build_story_pdf.py",
        leftMargin=MARGIN_INNER,
        rightMargin=MARGIN_OUTER,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
    )
    full = Frame(0, 0, PAGE_W, PAGE_H, id="full", leftPadding=0, rightPadding=0,
                 topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="plain", frames=[full], onPage=doc._paper),
        PageTemplate(id="toc", frames=[full], onPage=doc._paper),
        PageTemplate(id="recto", frames=[recto_frame()], onPage=doc._paper,
                     onPageEnd=doc._chrome),
        PageTemplate(id="verso", frames=[verso_frame()], onPage=doc._paper,
                     onPageEnd=doc._chrome),
    ])
    return doc


def build() -> Path:
    register_fonts()
    styles = build_styles()
    meta, chapters, note = parse(SOURCE.read_text(encoding="utf-8"))
    doc = make_doc()

    def assemble(toc_entries: list[tuple[str, int]]) -> list:
        story: list = []

        # title page -------------------------------------------------------- #
        story.append(NextPageTemplate("plain"))
        story.append(Spacer(1, 58 * mm))
        story.append(Paragraph(inline(meta["title"]), styles["title"]))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(ORNAMENT, styles["ornament"]))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(inline(meta["subtitle"]), styles["subtitle"]))
        story.append(Spacer(1, 96 * mm))
        story.append(Paragraph("1912", styles["imprint"]))
        story.append(PageBreak())

        # epigraph ---------------------------------------------------------- #
        story.append(Spacer(1, 74 * mm))
        story.append(Paragraph(inline(meta["epigraph"].strip("*")), styles["epigraph"]))
        story.append(PageBreak())

        # contents ---------------------------------------------------------- #
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("Contents", styles["toc_title"]))
        story.extend(contents_page(toc_entries, styles))
        story.append(PageBreak())
        story.append(NextPageTemplate(["recto", "verso"]))
        story.append(PageBreak())

        # chapters ---------------------------------------------------------- #
        for chapter in chapters:
            heading_text = (
                f"{chapter['num']}. {chapter['title']}" if chapter["num"] else chapter["title"]
            )
            key = "sec-" + re.sub(r"[^a-z0-9]+", "-", heading_text.lower()).strip("-")
            doc.heading_titles[key] = heading_text

            story.append(Spacer(1, 16 * mm))
            eyebrow = heading(
                Paragraph(f"Chapter {chapter['num']}".upper() if chapter["num"] else "",
                          styles["eyebrow"]),
                key, heading_text,
            )
            story.append(eyebrow)
            story.append(Paragraph(inline(chapter["title"]), styles["chapter_title"]))
            story.append(Spacer(1, 4.5 * mm))
            story.append(Paragraph(ORNAMENT, styles["ornament"]))
            story.append(Spacer(1, 7 * mm))
            doc.page_chapter = chapter["title"]

            first = True
            for kind, text in chapter["blocks"]:
                if kind == "quote":
                    story.append(Spacer(1, 2 * mm))
                    q = Paragraph(inline(text), styles["note_body"])
                    q.hAlign = "LEFT"
                    q.style = ParagraphStyle("Quote", parent=styles["note_body"],
                                             leftIndent=8, rightIndent=8, fontSize=11)
                    story.append(q)
                    story.append(Spacer(1, 2 * mm))
                    first = True
                    continue
                if first:
                    story.extend(initial_cap_para(text, styles))
                else:
                    story.append(Paragraph(inline(text), styles["body"]))
                first = False
            story.append(PageBreak())

        # historical note --------------------------------------------------- #
        story.append(PageBreak())  # leaves a blank verso so the note opens recto
        story.append(Spacer(1, 16 * mm))
        story.append(heading(Paragraph("A Note on the History", styles["chapter_title"]),
                             "sec-note", "A Note on the History"))
        story.append(Spacer(1, 4.5 * mm))
        story.append(Paragraph(ORNAMENT, styles["ornament"]))
        story.append(Spacer(1, 7 * mm))
        for _, text in note["blocks"]:
            story.append(Paragraph(inline(text), styles["note_body"]))

        # multiBuild fixes the table of contents, but the TOC page count can shift
        # the body by a page; a final pass with everything known is exact.
        return story

    titles = [
        f"{c['num']}. {c['title']}" if c["num"] else c["title"] for c in chapters
    ] + ["A Note on the History"]

    # Pass one lays the book out with a placeholder contents of the right length,
    # so every chapter's page number is known; pass two sets those numbers. The
    # table's height is identical in both passes, so the pagination cannot move.
    doc.build(assemble([(title, "") for title in titles]))
    first_pass_pages = list(doc.heading_pages.values())
    doc = make_doc()
    doc.build(assemble(list(zip(titles, first_pass_pages))))
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")
    sys.exit(0)
