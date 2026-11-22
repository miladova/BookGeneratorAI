#!/usr/bin/env python3
"""Typeset TWO FIRES as a 6x9 PDF reading copy.

    pip install reportlab pyphen
    python3 build_pdf.py

Output: "Two Fires.pdf"
"""
import io
import pathlib
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.flowables import Flowable

HERE = pathlib.Path(__file__).parent
FONTS = HERE / "fonts"
OUT = HERE / "Two Fires.pdf"

PAGE_W, PAGE_H = 6 * inch, 9 * inch
M_TOP, M_BOT, M_SIDE = 56, 64, 57
FRAME_W = PAGE_W - 2 * M_SIDE
FRAME_H = PAGE_H - M_TOP - M_BOT

TITLE = "Two Fires"
SUBTITLE = "A Novella of Poland, 1958"

CHAPTERS = [
    "01-the-dossier.md", "02-two-fires.md", "03-the-machine-and-the-willow.md",
    "04-what-the-living-do.md", "05-the-plank.md", "06-room-214.md",
    "07-the-file.md", "08-the-empty-church.md", "09-the-opinion.md",
    "10-the-second-fire.md",
]
BACK = "99-back-matter.md"
NUMERALS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]


# ---------------------------------------------------------------- fonts
FONT_FILES = ["Regular", "Italic", "Bold", "BoldItalic", "SemiBold"]
FONT_URL = ("https://api.github.com/repos/octaviopardo/EBGaramond12/contents/"
            "fonts/ttf/EBGaramond-{}.ttf?ref=master")


def ensure_fonts():
    """Fetch EB Garamond (SIL OFL 1.1) if the fonts folder is empty."""
    FONTS.mkdir(exist_ok=True)
    for style in FONT_FILES:
        dest = FONTS / f"EBGaramond-{style}.ttf"
        if dest.exists() and dest.stat().st_size > 100_000:
            continue
        import urllib.request
        print(f"fetching {dest.name} ...")
        req = urllib.request.Request(
            FONT_URL.format(style),
            headers={"Accept": "application/vnd.github.raw", "User-Agent": "two-fires-build"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())


def register_fonts():
    faces = {
        "EBG": "EBGaramond-Regular.ttf",
        "EBG-Bold": "EBGaramond-Bold.ttf",
        "EBG-Italic": "EBGaramond-Italic.ttf",
        "EBG-BoldItalic": "EBGaramond-BoldItalic.ttf",
        "EBG-Semi": "EBGaramond-SemiBold.ttf",
    }
    for name, fn in faces.items():
        pdfmetrics.registerFont(TTFont(name, str(FONTS / fn)))
    registerFontFamily("EBG", normal="EBG", bold="EBG-Bold",
                       italic="EBG-Italic", boldItalic="EBG-BoldItalic")


# ---------------------------------------------------------------- text
INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*)")


def smart(s: str) -> str:
    s = s.replace("...", "\u2026")
    out = []
    open_dq = True
    for i, ch in enumerate(s):
        if ch == '"':
            out.append("\u201c" if open_dq else "\u201d")
            open_dq = not open_dq
        elif ch == "'":
            prev = s[i - 1] if i else " "
            out.append("\u2019" if (prev.isalnum() or prev in ".,!?\u201d") else "\u2018")
        else:
            out.append(ch)
    return "".join(out)


def rich(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = smart(s)
    s = INLINE.sub(
        lambda m: f"<b>{m.group(0)[2:-2]}</b>" if m.group(0).startswith("**")
        else f"<i>{m.group(0)[1:-1]}</i>", s)
    return s


# ---------------------------------------------------------------- flowables
class LetterSpaced(Flowable):
    """A single line of letterspaced type, centred in the frame."""

    def __init__(self, text, font="EBG", size=8, leading=None, charspace=2.2,
                 color=colors.black):
        Flowable.__init__(self)
        self.text, self.font, self.size = text, font, size
        self.leading = leading if leading else size * 1.6
        self.charspace, self.color = charspace, color

    def wrap(self, aw, ah):
        return aw, self.leading

    def draw(self):
        c = self.canv
        from reportlab.pdfbase.pdfmetrics import stringWidth
        w = (stringWidth(self.text, self.font, self.size)
             + self.charspace * max(0, len(self.text) - 1))
        x = FRAME_W / 2 - w / 2
        c.saveState()
        c.setFillColor(self.color)
        to = c.beginText()
        to.setTextOrigin(x, self.size * 0.28)
        to.setFont(self.font, self.size)
        to.setCharSpace(self.charspace)
        to.textOut(self.text)
        c.drawText(to)
        c.restoreState()


class Flag(Flowable):
    """Zero-size marker that flips a document attribute when it is drawn."""

    def __init__(self, book, attr, value):
        Flowable.__init__(self)
        self.book, self.attr, self.value = book, attr, value

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        setattr(self.book, self.attr, self.value)


class Anchor(Flowable):
    """Zero-size marker: records the page a chapter starts on, and bookmarks it."""



    def wrap(self, aw, ah):
        return 0, 0

    def __init__(self, key, label, book, chapter=""):
        Flowable.__init__(self)
        self.key, self.label, self.book, self.chapter = key, label, book, chapter

    def draw(self):
        c = self.canv
        self.book.current_chapter = self.chapter
        self.book.pages[self.key] = c.getPageNumber()
        c.bookmarkPage(self.key)
        c.addOutlineEntry(self.label, self.key, level=0, closed=False)


# ---------------------------------------------------------------- styles
def styles():
    body = ParagraphStyle(
        "body", fontName="EBG", fontSize=11.4, leading=16.2,
        alignment=TA_JUSTIFY, firstLineIndent=15, spaceBefore=0, spaceAfter=0,
        hyphenationLang="en_GB", embeddedHyphenation=1,
        allowWidows=0, allowOrphans=0, wordWrap="LTR",
    )
    body_first = ParagraphStyle("body_first", parent=body, firstLineIndent=0)
    body_flat = ParagraphStyle("body_flat", parent=body, firstLineIndent=0)
    scene = ParagraphStyle("scene", parent=body, alignment=TA_CENTER, firstLineIndent=0,
                           fontSize=11.5, leading=16, spaceBefore=13, spaceAfter=13,
                           textColor=colors.HexColor("#333333"))
    h2 = ParagraphStyle("h2", parent=body, fontName="EBG-Semi", fontSize=8.6, leading=12,
                        alignment=TA_CENTER, firstLineIndent=0, spaceBefore=20,
                        spaceAfter=9, textColor=colors.HexColor("#333333"))
    chtitle = ParagraphStyle("chtitle", parent=body, fontName="EBG", fontSize=25,
                             leading=29, alignment=TA_CENTER, firstLineIndent=0,
                             spaceBefore=4, spaceAfter=2)
    chsub = ParagraphStyle("chsub", parent=body, fontName="EBG-Italic", fontSize=10.4,
                           leading=14, alignment=TA_CENTER, firstLineIndent=0,
                           spaceBefore=6, spaceAfter=0,
                           textColor=colors.HexColor("#333333"))
    epi = ParagraphStyle("epi", parent=body, fontName="EBG-Italic", fontSize=11.2,
                         leading=17, alignment=TA_CENTER, firstLineIndent=0,
                         leftIndent=26, rightIndent=26)
    attrib = ParagraphStyle("attrib", parent=epi, fontSize=9.4, leading=13,
                            spaceBefore=12, textColor=colors.HexColor("#333333"))
    frontbig = ParagraphStyle("frontbig", parent=body, fontName="EBG", fontSize=31,
                              leading=36, alignment=TA_CENTER, firstLineIndent=0)
    frontsub = ParagraphStyle("frontsub", parent=body, fontName="EBG-Italic", fontSize=12.5,
                              leading=18, alignment=TA_CENTER, firstLineIndent=0,
                              spaceBefore=10)
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=13,
                           alignment=TA_LEFT, firstLineIndent=0, spaceAfter=7)
    toc = ParagraphStyle("toc", parent=body, fontSize=10.6, leading=15,
                         alignment=TA_LEFT, firstLineIndent=0)
    tocn = ParagraphStyle("tocn", parent=toc, alignment=TA_RIGHT)
    backh = ParagraphStyle("backh", parent=body, fontName="EBG", fontSize=16, leading=20,
                           alignment=TA_CENTER, firstLineIndent=0, spaceBefore=6,
                           spaceAfter=14)
    return locals()


# ---------------------------------------------------------------- parsing
def parse_chapter(path):
    lines = [ln.rstrip() for ln in path.read_text().splitlines()]
    blocks, title, sub, i = [], None, None, 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("# ") and title is None:
            title = re.sub(r"^Chapter\s+\w+\s*[\u2014\u2013-]\s*", "", s[2:].strip())
        elif s.startswith("## ") and not s.startswith("###") and sub is None and title:
            sub = s[3:].strip()
        else:
            break
        i += 1
    fresh = True
    for ln in lines[i:]:
        s = ln.strip()
        if not s:
            continue
        if s == "---":
            blocks.append(("scene",))
            fresh = True
        elif s.startswith("## "):
            blocks.append(("h2", s[3:].strip()))
            fresh = True
        elif s.startswith("# "):
            continue
        else:
            blocks.append(("p0" if fresh else "p", s))
            fresh = False
    return title, sub, blocks


def parse_back(path):
    blocks, fresh = [], True
    for ln in path.read_text().splitlines():
        s = ln.strip()
        if not s or s == "---":
            continue
        if s.startswith("## "):
            blocks.append(("bh", s[3:].strip()))
            fresh = True
        else:
            blocks.append(("p0", s))
            fresh = False
    return blocks


# ---------------------------------------------------------------- build
class Book(BaseDocTemplate):
    def __init__(self, filename, **kw):
        starts = set(kw.pop("chapter_starts", ()) or ())
        BaseDocTemplate.__init__(self, filename, pagesize=(PAGE_W, PAGE_H),
                                 leftMargin=M_SIDE, rightMargin=M_SIDE,
                                 topMargin=M_TOP, bottomMargin=M_BOT, **kw)
        self.pages = {}
        self.chapter_starts = starts
        self.current_chapter = ""
        self.front_matter = True
        frame = Frame(M_SIDE, M_BOT, FRAME_W, FRAME_H, id="main",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=self.decorate)])

    def decorate(self, canv, doc):
        pn = canv.getPageNumber()
        if self.front_matter or pn in self.chapter_starts:
            return
        canv.saveState()
        canv.setFillColor(colors.HexColor("#555555"))
        head = TITLE.upper() if pn % 2 == 0 else self.current_chapter.upper()
        from reportlab.pdfbase.pdfmetrics import stringWidth
        cs = 1.6
        w = stringWidth(head, "EBG", 7.8) + cs * max(0, len(head) - 1)
        to = canv.beginText()
        to.setTextOrigin((PAGE_W - w) / 2, PAGE_H - M_TOP + 24)
        to.setFont("EBG", 7.8)
        to.setCharSpace(cs)
        to.textOut(head)
        canv.drawText(to)
        canv.setFont("EBG", 9.4)
        canv.drawCentredString(PAGE_W / 2, M_BOT - 30, str(pn - self.offset))
        canv.restoreState()

    offset = 0


def build(path, pages=None):
    doc = Book(path if hasattr(path, "write") else str(path), title=TITLE, author="", subject=SUBTITLE,
               creator="Two Fires build_pdf.py",
               chapter_starts=set(pages.values()) if pages else ())
    S = styles()
    story = []

    # ---- half title
    story += [Spacer(1, 150),
              LetterSpaced("TWO FIRES", "EBG", 15, leading=24, charspace=6.5),
              Spacer(1, 14),
              Paragraph("A Novella of Poland, 1958", S["frontsub"]),
              PageBreak()]

    # ---- title page
    story += [Spacer(1, 130),
              Paragraph("Two Fires", S["frontbig"]),
              Spacer(1, 6),
              HRFlowable(width="18%", thickness=0.6, color=colors.HexColor("#777777"),
                         spaceBefore=14, spaceAfter=16, hAlign="CENTER"),
              Paragraph("A Novella of Poland, 1958", S["frontsub"]),
              Spacer(1, 120),
              LetterSpaced("W A R S A W   \u00b7   M C M L V I I I", "EBG", 8.5, leading=14,
                           charspace=1.6, color=colors.HexColor("#444444")),
              PageBreak()]

    # ---- copyright
    story += [Spacer(1, 300),
              Paragraph("This is a work of fiction. The historical setting is real; the people, "
                        "parishes, villages and dioceses depicted are invented, and any resemblance "
                        "to persons living or dead is coincidental. Real places are used fictitiously.",
                        S["small"]),
              Spacer(1, 10),
              Paragraph("Set in EB Garamond, 11&#189;/16.2. Typeset at 6 &#215; 9 inches. "
                        "EB Garamond is released under the SIL Open Font License 1.1.",
                        S["small"]),
              PageBreak()]

    # ---- epigraph
    story += [Spacer(1, 175),
              Paragraph("&#8220;A village has two fires: the one in the hearth and the one in "
                        "the church. A woman&#8217;s life is carrying a coal from the one to the "
                        "other without dropping it.&#8221;", S["epi"]),
              Paragraph("&#8212; saying attributed to Marianna K&#281;dzierska (1893&#8211;1944)",
                        S["attrib"]),
              Spacer(1, 90),
              Paragraph("For everyone who carried a coal.", ParagraphStyle(
                  "ded", parent=S["epi"], fontSize=10, leading=15)),
              PageBreak()]

    # ---- contents
    story += [Spacer(1, 40),
              LetterSpaced("CONTENTS", "EBG", 9, leading=20, charspace=4.0),
              Spacer(1, 26)]
    rows = []
    for n, fn in enumerate(CHAPTERS):
        title, _sub, _b = parse_chapter(HERE / fn)
        key = f"ch{n + 1}"
        num = ""
        if pages and key in pages:
            num = pages[key] - Book.offset
        rows.append([Paragraph(f"{NUMERALS[n]} &#183; <i>{rich(title)}</i>", S["toc"]),
                     Paragraph(str(num), S["tocn"])])
    t = Table(rows, colWidths=[FRAME_W - 34, 34])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [t, PageBreak()]

    # ---- chapters
    story.append(Flag(doc, "front_matter", False))
    for n, fn in enumerate(CHAPTERS):
        title, sub, blocks = parse_chapter(HERE / fn)
        key = f"ch{n + 1}"
        if n > 0:
            story.append(PageBreak())
        label = f"CHAPTER {NUMERALS[n].upper()}"
        mark = Anchor(key, f"{NUMERALS[n]}. {title}", doc, chapter=title)
        story += [mark, Spacer(1, 62),
                  LetterSpaced(label, "EBG", 8.4, leading=16, charspace=3.4),
                  Spacer(1, 8),
                  Paragraph(rich(title), S["chtitle"])]
        if sub:
            story += [Paragraph(rich(sub), S["chsub"])]
        story += [HRFlowable(width="12%", thickness=0.5, color=colors.HexColor("#888888"),
                             spaceBefore=16, spaceAfter=20, hAlign="CENTER")]
        for b in blocks:
            kind = b[0]
            if kind == "scene":
                story.append(Paragraph("\u00b7&nbsp;&nbsp;\u00b7&nbsp;&nbsp;\u00b7", S["scene"]))
            elif kind == "h2":
                story.append(Paragraph(rich(b[1]).upper(), S["h2"]))
            elif kind == "p0":
                story.append(Paragraph(rich(b[1]), S["body_first"]))
            else:
                story.append(Paragraph(rich(b[1]), S["body"]))

    # ---- back matter
    story.append(PageBreak())
    for b in parse_back(HERE / BACK):
        if b[0] == "bh":
            story.append(Paragraph(rich(b[1]), S["backh"]))
            story.append(HRFlowable(width="10%", thickness=0.5,
                                    color=colors.HexColor("#888888"),
                                    spaceBefore=2, spaceAfter=16, hAlign="CENTER"))
        else:
            story.append(Paragraph(rich(b[1]), S["body_flat"]))
            story.append(Spacer(1, 8))

    story.append(Spacer(1, 26))
    story.append(HRFlowable(width="8%", thickness=0.5, color=colors.HexColor("#888888"),
                            spaceBefore=10, spaceAfter=12, hAlign="CENTER"))
    story.append(LetterSpaced("TWO FIRES", "EBG", 7.4, leading=12, charspace=4.2,
                              color=colors.HexColor("#555555")))

    doc.build(story)
    return doc


def main():
    ensure_fonts()
    register_fonts()
    # pass one: find the page each chapter starts on
    tmp = io.BytesIO()
    doc = build(tmp, pages=None)
    pages = dict(doc.pages)
    # figure the head-matter offset so chapter one is page 1 in the folio
    first_chapter_page = pages.get("ch1", 9)
    Book.offset = first_chapter_page - 1
    doc2 = build(OUT, pages=pages)
    print(f"wrote {OUT} ({len(pages)} chapters anchored, front matter "
          f"{first_chapter_page - 1} pages)")


if __name__ == "__main__":
    main()
