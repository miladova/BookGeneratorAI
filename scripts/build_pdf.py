"""Typeset `manuscripts/the-bell-in-the-river/` as a print-ready 6x9 PDF.

Pure Python (reportlab + pyphen), using STIX General — a Times-class serif that
covers every Polish diacritic the book needs. Two passes: the first discovers
where each chapter falls so that running heads, the contents page and the PDF
bookmarks can all be correct.

Usage:
    .venv/bin/python scripts/build_pdf.py
"""

from __future__ import annotations

import os
import re
import sys
from io import BytesIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BOOK_DIR = os.path.join(ROOT, "manuscripts", "the-bell-in-the-river")
CHAPTERS_DIR = os.path.join(BOOK_DIR, "chapters")
OUT_DIR = os.path.join(BOOK_DIR, "build")
OUT_PDF = os.path.join(OUT_DIR, "The_Bell_in_the_River.pdf")

TITLE = "The Bell in the River"
AUTHOR = "M. L. WRONA"
RUNNING_TITLE = "THE BELL IN THE RIVER"

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import inch  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------- fonts


def font_dir() -> str:
    import matplotlib

    return os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")


def register_fonts() -> None:
    d = font_dir()
    for name, file in (
        ("Body", "STIXGeneral.ttf"),
        ("Body-Bold", "STIXGeneralBol.ttf"),
        ("Body-Italic", "STIXGeneralItalic.ttf"),
        ("Body-BoldItalic", "STIXGeneralBolIta.ttf"),
    ):
        pdfmetrics.registerFont(TTFont(name, os.path.join(d, file)))
    pdfmetrics.registerFontFamily(
        "Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-BoldItalic"
    )
    pdfmetrics.registerFont(TTFont("Display", os.path.join(d, "STIXGeneralBol.ttf")))
    pdfmetrics.registerFont(TTFont("Display-Italic", os.path.join(d, "STIXGeneralItalic.ttf")))


# ---------------------------------------------------------------- geometry

PAGE_W, PAGE_H = 6 * inch, 9 * inch
MARGIN_TOP = 0.78 * inch
MARGIN_BOTTOM = 0.80 * inch
MARGIN_INNER = 0.82 * inch
MARGIN_OUTER = 0.66 * inch

LEADING = 15.4
BODY_SIZE = 11

FRONT_PAGES = 6  # title, copyright, epigraph, blank, contents, blank

BASE_BODY = dict(
    fontName="Body",
    fontSize=BODY_SIZE,
    leading=LEADING,
    alignment=TA_JUSTIFY,
    spaceBefore=0,
    spaceAfter=0,
    hyphenationLang="en_GB",
    embeddedHyphenation=1,
    allowWidows=0,
    allowOrphans=0,
)

STYLE = {
    "body": ParagraphStyle("body", firstLineIndent=0.2 * inch, **BASE_BODY),
    "body_no_indent": ParagraphStyle("body_ni", firstLineIndent=0, **BASE_BODY),
    "docitalic": ParagraphStyle(
        "docitalic", firstLineIndent=0, fontName="Body-Italic",
        fontSize=BODY_SIZE - 0.6, leading=LEADING - 1.0, alignment=TA_JUSTIFY,
        leftIndent=0.16 * inch, rightIndent=0.10 * inch,
        spaceBefore=2.5, spaceAfter=2.5, hyphenationLang="en_GB", embeddedHyphenation=1,
    ),
    "quote": ParagraphStyle(
        "quote", fontName="Body-Italic", fontSize=BODY_SIZE - 1.2, leading=LEADING - 1.6,
        alignment=TA_JUSTIFY, firstLineIndent=0, leftIndent=0.30 * inch,
        rightIndent=0.20 * inch, spaceBefore=3.2, spaceAfter=3.2,
        hyphenationLang="en_GB", embeddedHyphenation=1, allowWidows=0, allowOrphans=0,
    ),
    "place": ParagraphStyle(
        "place", fontName="Body-Italic", fontSize=9.6, leading=13,
        alignment=TA_CENTER, spaceBefore=14, spaceAfter=26, textColor="#333333",
    ),
    "chapter_number": ParagraphStyle(
        "chnum", fontName="Display", fontSize=10, leading=14, alignment=TA_CENTER,
        spaceAfter=15, charSpace=2.6, textColor="#3a3a3a",
    ),
    "chapter_title": ParagraphStyle(
        "chtitle", fontName="Display", fontSize=21, leading=25, alignment=TA_CENTER,
        spaceAfter=3, textColor="#111111",
    ),
    "front_title": ParagraphStyle(
        "ftitle", fontName="Display", fontSize=27, leading=31, alignment=TA_CENTER, spaceAfter=18,
    ),
    "front_sub": ParagraphStyle(
        "fsub", fontName="Display-Italic", fontSize=13, leading=18, alignment=TA_CENTER, spaceAfter=8,
    ),
    "front_author": ParagraphStyle(
        "fauthor", fontName="Display", fontSize=13.5, leading=18, alignment=TA_CENTER,
        charSpace=2.4, spaceAfter=6,
    ),
    "front_body": ParagraphStyle(
        "fbody", fontName="Body", fontSize=9.6, leading=13.6, alignment=TA_JUSTIFY,
        hyphenationLang="en_GB", embeddedHyphenation=1,
    ),
    "epigraph": ParagraphStyle(
        "epigraph", fontName="Body-Italic", fontSize=11.6, leading=17, alignment=TA_CENTER, spaceAfter=4,
    ),
    "epigraph_src": ParagraphStyle(
        "epigraph_src", fontName="Body", fontSize=9.2, leading=13, alignment=TA_CENTER, spaceBefore=2,
    ),
    "contents_head": ParagraphStyle(
        "chead", fontName="Display", fontSize=12, leading=16, alignment=TA_CENTER,
        charSpace=3.2, spaceAfter=26,
    ),
    "contents": ParagraphStyle(
        "centry", fontName="Body", fontSize=10.4, leading=17.4,
    ),
    "contents_dots": ParagraphStyle(
        "cdots", fontName="Body", fontSize=10.4, leading=17.4,
        alignment=TA_CENTER, textColor="#555555",
    ),
    "contents_folio": ParagraphStyle(
        "cfolio", fontName="Body", fontSize=10.4, leading=17.4, alignment=2,
    ),
}


# ---------------------------------------------------------------- markup


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text: str) -> str:
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text


SCENE_RE = re.compile(r"^\*\s*\*\s*\*$")
RULE_RE = re.compile(r"^-{3,}$")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _parse_one(raw: str) -> dict:
    lines = raw.replace("\r\n", "\n").split("\n")
    heading = ""
    blocks: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("# ") and not heading:
            heading = stripped[2:].strip()
            i += 1
            continue
        if SCENE_RE.match(stripped):
            blocks.append(("scene", ""))
            i += 1
            continue
        if RULE_RE.match(stripped):
            blocks.append(("rule", ""))
            i += 1
            continue
        if stripped.startswith(">"):
            chunk = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                chunk.append(re.sub(r"^\s*>\s?", "", lines[i]).strip())
                i += 1
            blocks.append(("quote", " ".join(x for x in chunk if x)))
            continue
        # A paragraph may be hard-wrapped across several source lines (the
        # Historical Note is). Chapter files keep one line per paragraph, where
        # this loop simply consumes the single line.
        chunk = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or nxt.startswith(("#", ">")) or SCENE_RE.match(nxt) or RULE_RE.match(nxt):
                break
            chunk.append(nxt)
            i += 1
        blocks.append(("para", " ".join(chunk)))

    number, title = "", heading
    m = re.match(r"^(Chapter [A-Za-z]+):\s*(.+)$", heading)
    if m:
        number, title = m.group(1).upper(), m.group(2)

    place = ""
    if blocks and blocks[0][0] == "para":
        first = blocks[0][1]
        if first.startswith("*") and first.endswith("*") and len(first.split()) <= 12:
            place = first.strip("*")
            blocks = blocks[1:]

    return {"number": number, "title": title, "place": place, "blocks": blocks}


# ---------------------------------------------------------------- flowables

STATE = {
    "chapter_starts": {},   # page -> label
    "starts_by_label": [],  # ordered (label, page, number, title)
    "owner": {},            # page -> label of the chapter that owns it
    "heads": {},            # page -> chapter title, for running heads
    "current_label": "",
}


class SceneBreak(Flowable):
    def __init__(self):
        super().__init__()
        self.width = 0

    def wrap(self, aw, ah):
        self.width = aw
        return (aw, 26)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont("Display", 10.5)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawCentredString(self.width / 2, 8, "*  *  *")
        c.restoreState()


class Ornament(Flowable):
    def __init__(self):
        super().__init__()
        self.width = 0

    def wrap(self, aw, ah):
        self.width = aw
        return (aw, 30)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.setLineWidth(0.5)
        mid = self.width / 2
        c.line(mid - 26, 14, mid + 26, 14)
        c.restoreState()


class TocLine(Flowable):
    """One contents entry: text, dot leaders, folio — drawn, not wrapped."""

    def __init__(self, label: str, page: int, width: float):
        super().__init__()
        self.label = label
        self.page = str(page)
        self.width = width
        self.height = 17.4

    def wrap(self, aw, ah):
        self.width = aw
        return (aw, self.height)

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont("Body", 10.4)
        c.setFillColorRGB(0.08, 0.08, 0.08)
        baseline = 4.0
        c.drawString(0, baseline, self.label)
        label_w = c.stringWidth(self.label, "Body", 10.4)
        folio_w = c.stringWidth(self.page, "Body", 10.4)
        right = self.width
        c.drawRightString(right, baseline, self.page)
        # dot leaders between the label and the folio
        c.setFont("Body", 10.4)
        start = label_w + 7
        end = right - folio_w - 7
        dot_w = c.stringWidth(".", "Body", 10.4)
        gap = c.stringWidth(" ", "Body", 10.4) * 0.55
        x = start
        c.setFillColorRGB(0.45, 0.45, 0.45)
        while x + dot_w <= end:
            c.drawString(x, baseline, ".")
            x += dot_w + gap
        c.restoreState()


class ChapterOpener(Flowable):
    """Chapter number, title and place line at the head of a fresh page."""

    def __init__(self, number: str, title: str, place: str):
        super().__init__()
        self.number = number
        self.title = title
        self.place = place
        self.width = 0
        self._story: list = []

    def wrap(self, aw, ah):
        self.width = aw
        self._story = [Spacer(1, 0.85 * inch)]
        if self.number:
            self._story.append(Paragraph(esc(self.number), STYLE["chapter_number"]))
            self._story.append(Paragraph(esc(self.title), STYLE["chapter_title"]))
        else:
            self._story.append(Spacer(1, 8))
            self._story.append(Paragraph(esc(self.title), STYLE["chapter_title"]))
        self._story.append(
            Paragraph(inline(self.place), STYLE["place"]) if self.place else Spacer(1, 26)
        )
        h = 0.0
        for f in self._story:
            _, fh = f.wrap(aw, ah)
            h += fh
        self.height = h + 6
        return (aw, self.height)

    def draw(self):
        y = self.height
        for f in self._story:
            _, h = f.wrap(self.width, self.height)
            y -= h
            f.drawOn(self.canv, 0, y)
        page = self.canv.getPageNumber()
        if self.number:
            label = f"{self.number.split()[-1].title()}. {self.title}"
        else:
            label = self.title
        key = f"ch{page}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(label, key, level=0, closed=False)
        STATE["chapter_starts"][page] = label
        STATE["heads"][page] = self.title
        STATE["starts_by_label"].append((label, page, self.number, self.title))


class EndMark(Flowable):
    def __init__(self):
        super().__init__()
        self.width = 0

    def wrap(self, aw, ah):
        self.width = aw
        return (aw, 1)

    def draw(self):
        pass


# ---------------------------------------------------------------- document


class Book(BaseDocTemplate):
    def __init__(self, target, **kw):
        super().__init__(target, pagesize=(PAGE_W, PAGE_H), **kw)
        inner, outer = MARGIN_INNER, MARGIN_OUTER
        text_w = PAGE_W - inner - outer
        text_h = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM
        recto = Frame(inner, MARGIN_BOTTOM, text_w, text_h, id="recto",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        verso = Frame(outer, MARGIN_BOTTOM, text_w, text_h, id="verso",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="recto", frames=[recto], onPage=self.decorate),
            PageTemplate(id="verso", frames=[verso], onPage=self.decorate),
        ])

    def handle_pageBegin(self):
        super().handle_pageBegin()
        nxt = "verso" if self.page % 2 == 0 else "recto"
        if nxt != self.pageTemplate.id:
            self.handle_nextPageTemplate(nxt)

    def decorate(self, canv, doc):
        # Running heads and folios are stamped after pagination is known; see
        # stamp_running_heads().
        pass


# ---------------------------------------------------------------- story


def front_matter(contents_rows: list[tuple[str, str]]) -> list:
    story: list = []
    story += [Spacer(1, 1.55 * inch)]
    story += [Paragraph(esc(TITLE), STYLE["front_title"])]
    story += [Paragraph("A Novel", STYLE["front_sub"])]
    story += [Spacer(1, 0.55 * inch)]
    story += [Paragraph(esc(AUTHOR), STYLE["front_author"])]
    story += [PageBreak()]

    story += [Spacer(1, 0.35 * inch)]
    story += [Paragraph(
        "This is a work of fiction. Its two central characters, Zofia Wierzbicka and "
        "Michał Żurawski, their families and their parishes are invented. Where they "
        "meet real events of 1958 — the campaign against the Great Novena, the August "
        "schools decrees, the death of Pius XII and the election of John XXIII — the "
        "narrative follows the public record, and its interpretation of men's motives "
        "is its own. Jerzy Sztachelski, Stefan Wyszyński and the other historical "
        "figures who appear in these pages are presented as the historical record "
        "presents them; the private conversations in which they appear are invented.",
        STYLE["front_body"])]
    story += [Spacer(1, 13)]
    story += [Paragraph("A NOTE ON NAMES AND MONEY", ParagraphStyle(
        "notehead", fontName="Display", fontSize=8.4, leading=12, spaceAfter=6, charSpace=1.5))]
    story += [Paragraph(
        "Polish names are given as the characters used them. In 1938 a village outside "
        "Mława spoke of <i>ojciec</i> and <i>matka</i>, of <i>pan</i> and <i>pani</i>, and used "
        "the diminutives that no official document ever recorded: Zosia, Róża, and, in one "
        "household only, <i>Zosieczka</i>. The narrator has kept them. A word about the "
        "surname Wierzbicka: the Office's files spell it correctly. Most of the people in "
        "this book do not.", STYLE["front_body"])]
    story += [Spacer(1, 10)]
    story += [Paragraph(
        "Money is in złoty. In 1938 a farm labourer earned about sixty złoty a month; a "
        "pair of good boots cost fifteen; a cow, three hundred. In 1958 a teacher earned "
        "eleven hundred a month and a decent coat cost nine hundred. The reader may find "
        "these figures useful; the people in this book certainly did.", STYLE["front_body"])]
    story += [PageBreak()]

    story += [Spacer(1, 1.9 * inch)]
    story += [Paragraph("Ojczyzna — to wielki zbiorowy obowiązek.", STYLE["epigraph"])]
    story += [Paragraph("Cyprian Kamil Norwid", STYLE["epigraph_src"])]
    story += [Spacer(1, 12)]
    story += [Paragraph("Fatherland — it is a great collective obligation.", STYLE["epigraph"])]
    story += [PageBreak(), Spacer(1, 1), PageBreak()]

    # contents
    story += [Spacer(1, 0.5 * inch)]
    story += [Paragraph("CONTENTS", STYLE["contents_head"])]
    if contents_rows:
        text_w = PAGE_W - MARGIN_INNER - MARGIN_OUTER
        for label, page in contents_rows:
            story += [TocLine(label, page, text_w)]
    story += [PageBreak(), Spacer(1, 1), PageBreak()]
    return story


def chapter_story(meta: dict, first: bool) -> list:
    story: list = []
    if not first:
        story.append(PageBreak())
    story.append(ChapterOpener(meta["number"], meta["title"], meta["place"]))
    prev = "opener"
    for kind, text in meta["blocks"]:
        if kind == "scene":
            story.append(SceneBreak())
            prev = "scene"
            continue
        if kind == "rule":
            story.append(Ornament())
            prev = "rule"
            continue
        if kind == "quote":
            story.append(Paragraph(inline(text), STYLE["quote"]))
            prev = "quote"
            continue
        if text.startswith("*") and text.endswith("*") and text.count("*") == 2:
            story.append(Paragraph(inline(text), STYLE["docitalic"]))
        else:
            style = STYLE["body"] if prev not in ("opener", "scene", "rule") else STYLE["body_no_indent"]
            story.append(Paragraph(inline(text), style))
        prev = "para"
    story.append(EndMark())
    return story


def parse_document(raw: str) -> dict:
    """Parse a single document. Use split_sections() for files with several."""
    return split_sections(raw)[0]


def split_sections(raw: str) -> list[dict]:
    """A chapter file may hold more than one H1 (chapter_01 = Prologue + Chapter One)."""
    text = raw.replace("\r\n", "\n")
    parts = re.split(r"(?m)^# ", text)
    out = []
    for part in parts:
        if not part.strip():
            continue
        out.append(_parse_one("# " + part))
    return out


def sections() -> list[dict]:
    out = []
    for i in range(1, 11):
        out += split_sections(read(os.path.join(CHAPTERS_DIR, f"chapter_{i:02d}.md")))
    from importlib import import_module

    build_mod = import_module("scripts.build_manuscript") if os.path.exists(
        os.path.join(ROOT, "scripts", "__init__.py")) else None
    if build_mod is None:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import build_manuscript as build_mod  # type: ignore

    note = parse_document(build_mod.HISTORICAL_NOTE)
    out.append(note)
    return out


def render(target, secs: list[dict], contents_rows) -> None:
    doc = Book(
        target,
        title=TITLE,
        author="M. L. Wrona",
        subject="A novel of Warsaw, 1958",
        creator="BookGeneratorAI",
    )
    story: list = front_matter(contents_rows)
    for n, meta in enumerate(secs):
        story += chapter_story(meta, first=(n == 0))
    doc.build(story)



def stamp_running_heads(path: str, secs: list[dict]) -> None:
    """Draw running heads and folios on the finished PDF.

    Must run after build(): only then is it known which chapter owns each page,
    and which pages are chapter openings (those get neither head nor folio).
    """
    import pymupdf

    doc = pymupdf.open(path)
    starts = dict(STATE["chapter_starts"])
    heads = dict(STATE["heads"])
    labels_by_page = {pg: lab for pg, lab in starts.items()}

    order = sorted(heads.items())  # (start_page, chapter title)
    fontfile = os.path.join(font_dir(), "STIXGeneral.ttf")
    grey = (0.36, 0.36, 0.36)
    dark = (0.24, 0.24, 0.24)

    for pno in range(len(doc)):
        page = doc[pno]
        n = pno + 1  # 1-based physical page
        if n <= FRONT_PAGES:
            continue
        if n in labels_by_page:
            continue
        owner = ""
        for sp, ttl in order:
            if sp <= n:
                owner = ttl
        head = RUNNING_TITLE if n % 2 == 0 else (owner.upper() or RUNNING_TITLE)
        folio = str(n - FRONT_PAGES)
        w = page.rect.width
        top = 0.78 * 72 - 26
        bottom = page.rect.height - 0.80 * 72 + 22

        # font
        page.insert_font(fontname="stix", fontfile=fontfile)
        if n % 2 == 0:  # verso: head at inner (right) edge
            tw = pymupdf.Font(fontfile=fontfile).text_length(head, fontsize=8.2)
            page.insert_text((w - 0.66 * 72 - tw, top), head, fontname="stix",
                             fontsize=8.2, color=grey)
            page.insert_text((0.82 * 72, bottom), folio, fontname="stix",
                             fontsize=9.2, color=dark)
        else:  # recto: head at inner (left) edge
            page.insert_text((0.82 * 72, top), head, fontname="stix",
                             fontsize=8.2, color=grey)
            tw = pymupdf.Font(fontfile=fontfile).text_length(folio, fontsize=9.2)
            page.insert_text((w - 0.66 * 72 - tw, bottom), folio, fontname="stix",
                             fontsize=9.2, color=dark)
    doc.saveIncr()
    doc.close()


def main() -> int:
    register_fonts()
    os.makedirs(OUT_DIR, exist_ok=True)
    secs = sections()

    # Pass 1: discover pagination with placeholder contents.
    STATE["chapter_starts"].clear()
    STATE["starts_by_label"].clear()
    render(BytesIO(), secs, [])
    rows = [(label, page - FRONT_PAGES) for label, page, _, _ in STATE["starts_by_label"]]

    # Pass 2: real render with the contents filled in.  Adding numbers to an
    # existing lines does not change line counts, so pagination is stable.
    STATE["chapter_starts"].clear()
    STATE["starts_by_label"].clear()
    render(OUT_PDF, secs, rows)

    final = [(label, page - FRONT_PAGES) for label, page, _, _ in STATE["starts_by_label"]]
    if final != rows:  # pragma: no cover - defensive
        STATE["chapter_starts"].clear()
        STATE["starts_by_label"].clear()
        render(OUT_PDF, secs, final)

    stamp_running_heads(OUT_PDF, secs)

    print("contents:")
    for label, page in final:
        print(f"   {label:<36}{page:>5}")
    print(f"\nPDF: {OUT_PDF}  ({os.path.getsize(OUT_PDF)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
