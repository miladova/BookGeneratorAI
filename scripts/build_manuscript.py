"""Build the manuscript deliverables for `manuscripts/the-bell-in-the-river/`.

Uses the repository's own compilers:
  * generator/docx_compiler.py -> print-ready 6x9 DOCX with TOC and running heads
  * tools/epub_compiler.py     -> EPUB 3 with navigation

Usage:
    .venv/bin/python scripts/build_manuscript.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from generator.docx_compiler import compile_book  # noqa: E402
from tools.epub_compiler import compile_epub  # noqa: E402

BOOK_DIR = os.path.join(ROOT, "manuscripts", "the-bell-in-the-river")
CHAPTERS_DIR = os.path.join(BOOK_DIR, "chapters")
OUT_DIR = os.path.join(BOOK_DIR, "build")

TITLE = "The Bell in the River"
AUTHOR = "M. L. Wrona"
LANGUAGE = "english"

DEDICATION = (
    "For those who carried the parish records out of burning churches,\n"
    "and for those who did not have a church to carry them out of."
)

NOTE = (
    "This is a work of fiction. Its two central characters, Zofia Wierzbicka and "
    "Michał Żurawski, their families and their parishes are invented. Where they "
    "meet real events of 1958 — the campaign against the Great Novena, the August "
    "schools decrees, the death of Pius XII and the election of John XXIII, the "
    "consistory of December 1958 — the novel follows the public record, and its "
    "interpretation of men's motives is its own. Jerzy Sztachelski, Stefan "
    "Wyszyński and the other historical figures who appear in these pages are "
    "presented as the historical record presents them; the private conversations "
    "in which they appear are invented."
)

HISTORICAL_NOTE = """# Historical Note

This novel takes place in a country that no longer exists, and it uses that
country's institutions as they were, not as they are remembered. These pages
separate what the record establishes from what this book has invented.

**The Office.** The Office for Religious Denominations (*Urząd do Spraw Wyznań*)
was created on 19 April 1950, attached directly to the Presidium of the
Government, and dissolved in 1989. It licensed church buildings, approved or
refused the appointment of parish priests, kept files on the clergy, ran the
"patriotic priest" movement, and was in the ordinary course of business the
interlocutor of every bishop in Poland. From 1956 to 1961 it was headed by
**Jerzy Sztachelski**, a physician by training and a minister without portfolio,
who appears in this book as a historical figure. The scenes in which he appears
are invented; the position he argues — that the state could not abolish the
Church and would have to administer it — is the position the record attributes to
him, and the reader may judge how well he argued it.

**The Great Novena.** On 3 May 1957 the Episcopate, under **Stefan Wyszyński**,
Primate of Poland, opened the Great Novena (*Wielka Nowenna*): nine years of
prayer, confession and parish missions preparing for the millennium of the
baptism of Poland in 1966. Its engine was a consecrated copy of the icon of Our
Lady of Częstochowa that travelled from parish to parish; by the end of 1958 it
had been met by crowds the Party could not explain and could not stop. The state's
counter-campaign of 1958 — the refusal of building permits, the pressure on local
officials, the July letter of the Party Secretariat to the voivodeship
committees, the raid on Jasna Góra on 21 July — is the weather of this book, and
the picture's detour around Świerczyna is the kind of thing that
happened in hundreds of parishes that year.

**The fourth of August.** On 4 August 1958 the Minister of Education, Władysław
Bieńkowski, issued a circular on the secular school: crucifixes and religious
emblems were to be removed from classrooms, prayer was forbidden at the start and
end of lessons, and religious instruction was to be taught only after the
compulsory timetable, by catechists who were not members of religious orders. In
the villages it was called *the night of the fourth of August*, and the memory of
it outlasted the circular; teachers who removed the cross from the wall and
teachers who refused were both, in different parishes, made to answer for it. One
chapter takes the liberty of putting a cross in a drawer and a broken window in a
village school — an event of the kind that occurred, not a documented event at a
documented place.

On 24 September 1958, at the Twelfth Plenum of the Central Committee, Władysław
Gomułka announced the campaign of *a thousand schools for the thousand years*, the
state's secular answer to the Church's millennium. The phrase was on the hoardings
before the speech was made, exactly as the novel says.

**Rome, 1958.** Pius XII died on 9 October 1958. The conclave of 25–28 October
elected Angelo Giuseppe Roncalli, who took the name John XXIII and was crowned on
4 November. The consistory he announced on 17 November, and held on 15 December
1958, created twenty-three cardinals. It did not create Stefan Wyszyński: the
Primate had been made a cardinal by Pius XII on 12 January 1953, had been unable
to travel to Rome to receive the red hat, and had finally received it from the
Pope's own hands in May 1957. The Office's file on the matter, in this book, did
not know that. The novel's red hat is therefore not a hat but a protocol about a
hat — which is, in the view of this book, the more accurate comedy.

**The roundup and the number.** The roundups of Polish civilians in the spring of
1943, in reprisal for the killing of German gendarmes, are documented; the number
this novel gives its central character, 119278, is invented, and so is the miller's
family that carries it. The tattooing of numbers at Auschwitz-Birkenau from 1943 is
not. The letter from the camp is invented, but it is built out of
the forms such letters had to be written on, the censors they passed, and the
things men in them were permitted to say and were not.

**Two liberties.** The parish of Świerczyna, its mill, its river, its bell and its
people are invented, though their like stood in every second parish in Mazowsze. And
the arrangement at the centre of the book — a bishop who agrees to sit in a room
with the Office every quarter so that a church can be built, and an officer who
agrees to be the person in the room — is a fiction of motive and not of fact. No
such bargain is recorded. But the men and women who negotiated the real ones are
dead, and the files they left are open, and the files do not agree with each other.
"""


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text))


def assemble_staging_dir(staging: str) -> dict:
    """Write front matter + chapter files into `staging` in the layout the compilers expect."""
    dedication = DEDICATION

    title_page = f"""# {TITLE}

## A novel

### {AUTHOR}

> *Ojczyzna — to wielki zbiorowy obowiązek.*
> — Cyprian Kamil Norwid
>
> *Fatherland — it is a great collective obligation.*
"""
    with open(os.path.join(staging, "chapter_00.md"), "w", encoding="utf-8") as fh:
        fh.write(title_page)

    chapters = sorted(
        p for p in os.listdir(CHAPTERS_DIR) if re.fullmatch(r"chapter_\d{2}\.md", p)
    )
    # Renumber: front matter occupies 00, the prologue is part of chapter_01,
    # so we simply copy the chapter files byte-for-byte.
    report = {}
    for name in chapters:
        src = os.path.join(CHAPTERS_DIR, name)
        dst = os.path.join(staging, name)
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(read(src))
        report[name] = words(read(src))

    with open(os.path.join(staging, "chapter_11.md"), "w", encoding="utf-8") as fh:
        fh.write(HISTORICAL_NOTE)
    report["chapter_11 (historical note)"] = words(HISTORICAL_NOTE)
    return report


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    metadata = {
        "subtitle": "A novel of Warsaw, 1958",
        "year": datetime.now().year,
        "is_fiction": True,
        "dedication": DEDICATION,
        "description": NOTE,
        "language": LANGUAGE,
    }

    with tempfile.TemporaryDirectory() as staging:
        report = assemble_staging_dir(staging)
        docx_path = os.path.join(OUT_DIR, "The_Bell_in_the_River.docx")
        epub_path = os.path.join(OUT_DIR, "The_Bell_in_the_River.epub")

        compile_book(
            title=TITLE,
            domain="historical fiction",
            author=AUTHOR,
            chapters_dir=staging,
            output_path=docx_path,
            language=LANGUAGE,
            metadata=metadata,
        )
        compile_epub(
            title=TITLE,
            author=AUTHOR,
            chapters_dir=staging,
            output_path=epub_path,
            language=LANGUAGE,
            metadata=metadata,
        )

    total = sum(v for k, v in report.items() if not k.startswith("chapter_00") and not k.startswith("chapter_11"))
    body_chapters = [v for k, v in report.items() if re.fullmatch(r"chapter_\d{2}\.md", k) and k != "chapter_00.md"]
    lines = ["# Word-count report", "", f"Total words (chapters incl. prologue): {total:,}", ""]
    lines.append("| File | Words |")
    lines.append("|---|---:|")
    for key in sorted(report):
        lines.append(f"| {key} | {report[key]:,} |")
    lines.append("")
    lines.append(f"Chapters: {len(body_chapters)}")
    lines.append(f"Mean words per chapter: {total // max(1, len(body_chapters)):,}")
    report_path = os.path.join(OUT_DIR, "word_counts.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\nDOCX: {docx_path}\nEPUB: {epub_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
