"""Golden defects: every failure found in a finished manuscript becomes a fixture here.

Both fixtures below are real sentences from the novella in novella-two-fires/.
The first is the defect exactly as a reader encountered it; the second is the
repair. A continuity check that cannot fail on the first and pass on the second
is not doing the job.
"""

import unittest

from tools.continuity import Character, check_chapter, numbers_in

CAST = [
    Character("Zofia Kędzierska", birth_year=1922, aliases=("Kędzierska", "Zofia")),
    Character("Aleksander Zaremba", birth_year=1922, aliases=("Zaremba", "Aleksander")),
    Character("Adam Turski", birth_year=1900, aliases=("Turski",)),
    Character("Tadeusz Rybak", birth_year=1932, aliases=("Rybak", "Tadeusz")),
]

# Chapter One, October 1958 — as published before the fix.
BEFORE = ('"Rygier wants to arrest the vicar." Turski said it mildly. '
          '"A boy at St Kazimierz, twenty-six, teaching the catechism to children '
          'in a private flat in Żoliborz, which is of course illegal, and which half '
          'the parishes in Warsaw do.')

# Chapter One, October 1958 — after the fix.
AFTER = ('"Rygier wants to arrest the vicar." Turski said it mildly. '
         '"The young one — Rybak, twenty-six, at St Kazimierz, teaching the catechism '
         'to children in a private flat in Żoliborz, which is of course illegal, and '
         'which half the parishes in Warsaw do.')

# Chapter Five, April 1955. Rybak is twenty-three on his appointment.
CH5_OK = "His vicar was Father Tadeusz Rybak, twenty-three, from a village near Płock."
CH5_DRIFT = "His vicar was Father Tadeusz Rybak, twenty-six, from a village near Płock."


class TestNumberParsing(unittest.TestCase):
    def test_spelled_and_digit_forms(self):
        self.assertIn(26, numbers_in("twenty-six"))
        self.assertIn(26, numbers_in("twenty six"))
        self.assertIn(36, numbers_in("aged 36"))
        self.assertIn(15, numbers_in("she was fifteen"))

    def test_no_false_positives_in_prose(self):
        self.assertEqual(numbers_in("He had nothing to say."), [])


class TestReferentIsNamed(unittest.TestCase):
    def test_original_sentence_is_flagged(self):
        findings = check_chapter(BEFORE, year=1958, cast=CAST)
        codes = [f.code for f in findings]
        self.assertIn("UNNAMED_NUMERIC", codes)

    def test_repaired_sentence_is_clean(self):
        findings = check_chapter(AFTER, year=1958, cast=CAST)
        self.assertEqual([f for f in findings if f.code == "UNNAMED_NUMERIC"], [])

    def test_single_character_scene_is_not_flagged(self):
        lone = [CAST[3]]
        findings = check_chapter(BEFORE, year=1958, cast=lone)
        self.assertEqual([f for f in findings if f.code == "UNNAMED_NUMERIC"], [])


class TestAgeFromBirthYear(unittest.TestCase):
    def test_correct_age_passes(self):
        findings = check_chapter(CH5_OK, year=1955, cast=CAST)
        self.assertEqual(findings, [])

    def test_drifted_age_is_caught(self):
        findings = check_chapter(CH5_DRIFT, year=1955, cast=CAST)
        codes = [f.code for f in findings]
        self.assertIn("AGE_CONFLICT", codes)
        detail = " ".join(f.detail for f in findings)
        self.assertIn("Tadeusz Rybak is 23 in 1955", detail)

    def test_same_sentence_passes_in_1958(self):
        findings = check_chapter(CH5_DRIFT, year=1958, cast=CAST)
        self.assertEqual(findings, [])


class TestNoFalsePositives(unittest.TestCase):
    """A gate that cries wolf gets switched off, and then nothing is detected.

    These are real sentences from the manuscript that must stay silent.
    """

    def assertSilent(self, sentence, year=1958):
        self.assertEqual(check_chapter(sentence, year=year, cast=CAST), [])

    def test_measurement_is_not_an_age(self):
        self.assertSilent("The file on Aleksander Zaremba was four centimetres thick.")

    def test_clock_time_is_not_an_age(self):
        self.assertSilent("Irena brought them in at three; they sat on chairs.")

    def test_count_is_not_an_age(self):
        self.assertSilent("The flat had a bookcase with sixty books in it, forty of them Bogdan's.")

    def test_named_minor_character_is_not_unresolved(self):
        self.assertSilent("The rector was a canon named Kaczorowski, seventy, who had "
                          "spent the war in the seminary at Kraków.")


class TestRegistryToCanon(unittest.TestCase):
    """The pipeline adapter: canonical birth years in, derived ages checked."""

    def setUp(self):
        from schemas.models import CharacterProfile, CharacterRegistry
        self.registry = CharacterRegistry(characters=[
            CharacterProfile(name="Tadeusz Rybak", role="Curate", birth_year=1932,
                             aliases=["Rybak", "Tadeusz"]),
            CharacterProfile(name="Aleksander Zaremba", role="Parish priest", birth_year=1922,
                             aliases=["Zaremba", "Olek"]),
        ])

    def test_birth_year_drives_the_check(self):
        from tools.continuity import canon_from_registry, check_chapter
        cast = canon_from_registry(self.registry)
        self.assertEqual(len(cast), 2)
        findings = check_chapter(CH5_DRIFT, year=1955, cast=cast)
        self.assertIn("AGE_CONFLICT", [f.code for f in findings])

    def test_no_year_means_no_age_claims_are_judged(self):
        from tools.continuity import canon_from_registry, check_chapter
        findings = check_chapter(CH5_DRIFT, year=None, cast=canon_from_registry(self.registry))
        self.assertEqual([f for f in findings if f.code == "AGE_CONFLICT"], [])

    def test_unnamed_referent_still_caught_without_a_year(self):
        from tools.continuity import canon_from_registry, check_chapter
        findings = check_chapter(BEFORE, year=None, cast=canon_from_registry(self.registry))
        self.assertIn("UNNAMED_NUMERIC", [f.code for f in findings])


class TestDrafterReceivesCanon(unittest.TestCase):
    """The draft prompt must carry the facts, or the model cannot honour them."""

    def _prompt(self):
        from agents.prose_drafter import ProseDrafterAgent
        from schemas.models import (BookBrief, ChapterBeat, CharacterProfile,
                                    CharacterRegistry, SubBeat, WorldBible)
        from tests.fake_llm import FakeLlm

        registry = CharacterRegistry(characters=[
            CharacterProfile(name="Tadeusz Rybak", role="Curate", birth_year=1932,
                             aliases=["Rybak"], canonical_facts={"birthplace": "a village near Płock"}),
            CharacterProfile(name="Aleksander Zaremba", role="Parish priest", birth_year=1922),
        ])
        chapter = ChapterBeat(chapter_number=6, title="Room 214", year=1958,
                              pov_character="Zofia Kędzierska")
        sub = SubBeat(section_number="6.1", characters_present=["Tadeusz Rybak"],
                      scene_objective="Deliver the summons.")
        drafter = ProseDrafterAgent(FakeLlm())
        return drafter._scene_prompt(chapter, sub, WorldBible(), registry,
                                     self._empty_state(), BookBrief(), "")

    @staticmethod
    def _empty_state():
        from schemas.models import StoryState
        return StoryState()

    def test_canon_block_contains_derived_age(self):
        prompt = self._prompt()
        self.assertIn("born 1932", prompt)
        self.assertIn("26 in 1958", prompt)

    def test_canon_block_contains_aliases_and_facts(self):
        prompt = self._prompt()
        self.assertIn("also called Rybak", prompt)
        self.assertIn("birthplace: a village near Płock", prompt)

    def test_first_mention_rule_is_in_the_prompt(self):
        prompt = self._prompt()
        self.assertIn("First mention", prompt)
        self.assertIn("give the name before the age", prompt)


class TestMechanicalFindingsReachTheRevisionBrief(unittest.TestCase):
    """A finding the model never sees is a finding nobody fixes."""

    def test_contradiction_becomes_a_continuity_issue(self):
        from agents.critics import MasterAdversarialReviewer
        from schemas.models import (ChapterBeat, CharacterProfile, CharacterRegistry,
                                    StoryState, WorldBible)
        from tests.fake_llm import FakeLlm

        registry = CharacterRegistry(characters=[
            CharacterProfile(name="Tadeusz Rybak", role="Curate", birth_year=1932, aliases=["Rybak"])])
        chapter = ChapterBeat(chapter_number=5, title="The Plank", year=1955)
        reviewer = MasterAdversarialReviewer(FakeLlm())
        brief = reviewer.evaluate_chapter(chapter, CH5_DRIFT, WorldBible(), registry, StoryState())
        self.assertTrue(any("Tadeusz Rybak is 23 in 1955" in i.description
                            for i in brief.continuity_issues))


class TestColdReader(unittest.TestCase):
    def test_confusion_is_reported(self):
        from agents.cold_reader import ColdReaderAgent
        from tests.fake_llm import FakeLlm
        import json

        class Reader(FakeLlm):
            def _cold_read(self, prompt):
                return json.dumps({
                    "who_is_on_stage": ["Turski", "a boy of twenty-six"],
                    "what_changed": ["The Office will consider the nomination"],
                    "unresolved_references": ["a boy at St Kazimierz, twenty-six"],
                    "questions": ["Which priest is twenty-six?"],
                })

        report = ColdReaderAgent(Reader()).read(1, BEFORE)
        self.assertTrue(report.is_confused)
        self.assertIn("a boy at St Kazimierz, twenty-six", report.unresolved_references)


class TestEngineAuthorsTheCanon(unittest.TestCase):
    """The user supplies an idea; the engine must supply the facts."""

    def test_chapters_inherit_the_anchor_year(self):
        from pipeline import apply_anchor_years
        from schemas.models import ChapterBeat, MasterOutline, WorldBible

        outline = MasterOutline(chapters=[
            ChapterBeat(chapter_number=1, year=None),
            ChapterBeat(chapter_number=2, year=None),
            ChapterBeat(chapter_number=3, year=1961),
        ])
        apply_anchor_years(outline, WorldBible(anchor_year=1958))
        self.assertEqual([c.year for c in outline.chapters], [1958, 1958, 1961])

    def test_undated_worlds_stay_undated(self):
        from pipeline import apply_anchor_years
        from schemas.models import ChapterBeat, MasterOutline, WorldBible

        outline = MasterOutline(chapters=[ChapterBeat(chapter_number=1)])
        apply_anchor_years(outline, WorldBible())
        self.assertIsNone(outline.chapters[0].year)

    def test_thin_canon_is_reported(self):
        from schemas.models import CharacterProfile, CharacterRegistry
        from tools.continuity import canon_gaps

        registry = CharacterRegistry(characters=[
            CharacterProfile(name="Tadeusz Rybak", birth_year=1932, aliases=["Rybak"]),
            CharacterProfile(name="A Man In A Grey Suit", role="Antagonist"),
        ])
        self.assertEqual(canon_gaps(registry), ["A Man In A Grey Suit"])

    def test_prompts_ask_for_the_facts(self):
        from prompts.system_prompts import CHARACTER_ARCHITECT_PROMPT, WORLD_BUILDER_PROMPT

        self.assertIn("birth_year", CHARACTER_ARCHITECT_PROMPT)
        self.assertIn("aliases", CHARACTER_ARCHITECT_PROMPT)
        self.assertIn("canonical_facts", CHARACTER_ARCHITECT_PROMPT)
        self.assertIn("anchor_year", WORLD_BUILDER_PROMPT)


if __name__ == "__main__":
    unittest.main()
