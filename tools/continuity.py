"""Deterministic tripwires for the two continuity failures an LLM reviewer misses.

1. AGE_CONFLICT — a number attached to a named character that contradicts canon.
   Canon stores a *birth year*, not an age, because ages drift and birth years cannot.

2. UNNAMED_NUMERIC — a person introduced by role and number with no name in the
   sentence, when other characters share the scene. The reader has to guess who
   the number belongs to, which is the defect this module was written after.

Neither check is an oracle. They are cheap, deterministic questions the author
must answer before a chapter is called finished: *does this number agree with
canon?* and *can the reader tell who this is?* Semantic review still matters;
this just guarantees the question gets asked.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

# Roles/nouns that can introduce a person without naming them.
ROLE_WORDS = {
    "boy", "girl", "man", "woman", "priest", "vicar", "curate", "pastor",
    "bishop", "canon", "monsignor", "nun", "monk", "soldier", "officer",
    "colonel", "clerk", "official", "teacher", "doctor", "widow", "farmer",
}

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_WORD = re.compile(
    r"\b(?:(?P<tens>" + "|".join(_TENS) + r")(?:[-\s](?P<unit>" + "|".join(_UNITS) + r"))?"
    r"|(?P<small>" + "|".join(_UNITS) + r"))\b",
    re.IGNORECASE,
)
_DIGITS = re.compile(r"\b(\d{1,3})\b")
_SENTENCE = re.compile(r"[^.!?]*[.!?]")


@dataclass(frozen=True)
class Character:
    """The minimum canon a chapter can be checked against."""

    name: str
    birth_year: Optional[int] = None
    aliases: Sequence[str] = ()

    def all_names(self) -> Sequence[str]:
        return (self.name, *self.aliases)


@dataclass(frozen=True)
class Finding:
    code: str
    sentence: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.detail}\n    \"{self.sentence.strip()}\""


def load_canon(path: str | Path) -> List[Character]:
    """Read a canon file: {"characters": [{"name":..., "birth_year":..., "aliases":[...]}]}."""
    data = json.loads(Path(path).read_text())
    return [
        Character(
            name=c["name"],
            birth_year=c.get("birth_year"),
            aliases=tuple(c.get("aliases", ())),
        )
        for c in data.get("characters", [])
    ]


def numbers_in(sentence: str) -> List[int]:
    found = [int(m.group(1)) for m in _DIGITS.finditer(sentence)]
    for m in _NUMBER_WORD.finditer(sentence):
        if m.group("tens"):
            value = _TENS[m.group("tens").lower()]
            if m.group("unit"):
                value += _UNITS[m.group("unit").lower()]
        else:
            value = _UNITS[m.group("small").lower()]
        found.append(value)
    return found


def _mentions(sentence: str, character: Character) -> bool:
    low = sentence.lower()
    return any(re.search(rf"\b{re.escape(n.lower())}\b", low) for n in character.all_names())


def _has_role_word(sentence: str) -> bool:
    low = sentence.lower()
    return any(re.search(rf"\b{w}\b", low) for w in ROLE_WORDS)


def _number_tokens(sentence: str):
    """Yield (value, start, end) for every number in the sentence."""
    for m in _DIGITS.finditer(sentence):
        yield int(m.group(1)), m.start(), m.end()
    for m in _NUMBER_WORD.finditer(sentence):
        if m.group("tens"):
            value = _TENS[m.group("tens").lower()]
            if m.group("unit"):
                value += _UNITS[m.group("unit").lower()]
        else:
            value = _UNITS[m.group("small").lower()]
        yield value, m.start(), m.end()


def _is_appositive(sentence: str, start: int, end: int) -> bool:
    before = sentence[:start].rstrip()
    after = sentence[end:].lstrip()
    return before.endswith(",") and after.startswith(",")


# Words that turn a number into a measurement, a duration or a count.
_UNIT_AFTER = re.compile(
    r"^\s*(?:centimet|metre|meter|kilometre|kilometer|mile|kilo|gram|z\u0142ot|"
    r"books?|pages?|people|persons?|men|women|children|soldiers?|copies|minutes?|"
    r"hours?|days?|weeks?|months?|years?\s+(?:before|after|earlier|later)|"
    r"per\s+cent|%|o.clock|times)", re.I)


def _cued(sentence: str, start: int, end: int) -> bool:
    """True when the number is being asserted as an age, not used as a time or a count."""
    before = sentence[:start]
    after = sentence[end:]
    if _UNIT_AFTER.match(after):
        return False
    if re.search(r"\b(?:was|is|were|aged|age)\s+(?:about\s+|only\s+|already\s+)?$", before, re.I):
        return True
    if re.search(r"\bat\s+the\s+age\s+of\s+$", before, re.I):
        return True
    if re.match(r"\s*years?\s+(?:old|of\s+age)", after, re.I):
        return True
    if _UNIT_AFTER.match(after):
        return False
    return False


def _alias_before(sentence: str, start: int, cast: Sequence[Character], window: int = 60):
    zone = sentence[max(0, start - window):start]
    best = None
    for character in cast:
        for alias in character.all_names():
            m = re.search(rf"\b{re.escape(alias)}\b", zone, re.I)
            if m and (best is None or m.end() > best[1]):
                best = (character, m.end())
    return best[0] if best else None


_PROPER_NAME = re.compile(r"(?<![.!?]\s)\b[A-Z\u015a\u017b\u0141\u0143\u0106\u0118\u00d3\u0104][a-z\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c]{2,}")


def _named_stranger_before(sentence: str, start: int, window: int = 70) -> bool:
    """True if a capitalised name appears before the number (Kaczorowski, seventy).

    The tool only checks canon members; a named minor character is a person the
    reader *can* resolve, so it should not be reported as an unresolved referent.
    """
    zone = sentence[max(0, start - window):start]
    for m in _PROPER_NAME.finditer(zone):
        word = m.group(0).lower()
        if word in ROLE_WORDS:
            continue
        prev = zone[:m.start()]
        # "at St Kazimierz" is a place, not a person
        if re.search(r"(?:\b(?:at|in|from|of|to|near|outside|across|parish\s+of)\s+"
                     r"|\bSt\.?\s+|\b\u015aw\.?\s+)$", prev, re.I):
            continue
        if not any(w in word for w in ("chapter", "father", "sunday", "monday", "tuesday",
                                       "wednesday", "thursday", "friday", "saturday",
                                       "christmas", "easter", "polish", "warsaw", "krak")):
            return True
    return False


def _role_before(sentence: str, start: int, window: int = 60) -> Optional[str]:
    zone = sentence[max(0, start - window):start].lower()
    hits = [w for w in ROLE_WORDS if re.search(rf"\b{w}\b", zone)]
    return hits[-1] if hits else None


def check_chapter(
    text: str,
    *,
    year: int,
    cast: Sequence[Character],
    require_named_numbers: bool = True,
) -> List[Finding]:
    """Return findings for one chapter.

    ``year`` is the in-world year of the scene, so ages are derived from birth
    years rather than stored. ``cast`` is the characters present in the scene;
    more than one character enables UNNAMED_NUMERIC.

    Precision matters more than recall here: a check that flags clocks, book
    counts and ordinals gets switched off within a week. So a number is only an
    age claim when it is appositive (``Rybak, twenty-six,``), cued
    (``was thirty-six``, ``aged fifty``, ``twenty-six years old``) or otherwise
    explicitly predicated of a person.
    """
    findings: List[Finding] = []
    sentences = [s for s in _SENTENCE.findall(text.replace("\n", " ")) if s.strip()]

    for sentence in sentences:
        for value, start, end in _number_tokens(sentence):
            if not (0 < value < 120):
                continue
            appositive = _is_appositive(sentence, start, end)
            if not (appositive or _cued(sentence, start, end)):
                continue

            character = _alias_before(sentence, start, cast)
            if character is not None:
                if character.birth_year is None:
                    continue
                expected = year - character.birth_year
                if value != expected:
                    findings.append(Finding(
                        "AGE_CONFLICT", sentence,
                        f"{character.name} is {expected} in {year} "
                        f"(born {character.birth_year}); the sentence says {value}.",
                    ))
                continue

            if not require_named_numbers or len(cast) <= 1:
                continue
            role = _role_before(sentence, start)
            if role and appositive and not _named_stranger_before(sentence, start):
                findings.append(Finding(
                    "UNNAMED_NUMERIC", sentence,
                    f"A person is described as \"{role}\" and given a number, but is "
                    "not named, while other characters share the scene. Name them, or "
                    "make the withholding deliberate and unambiguous.",
                ))
    return findings


def check_file(path: str | Path, *, year: int, cast: Sequence[Character]) -> List[Finding]:
    return check_chapter(Path(path).read_text(), year=year, cast=cast)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Flag canon conflicts and unresolvable introductions in a chapter.")
    parser.add_argument("chapter", help="markdown or text file")
    parser.add_argument("--year", type=int, required=True,
                        help="in-world year of the scene")
    parser.add_argument("--canon", required=True, help="canon JSON with birth years and aliases")
    args = parser.parse_args(argv)

    findings = check_file(args.chapter, year=args.year, cast=load_canon(args.canon))
    for finding in findings:
        print(finding)
    print(f"\n{len(findings)} finding(s) in {args.chapter}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(_main())
