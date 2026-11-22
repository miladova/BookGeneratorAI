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


if __name__ == "__main__":
    unittest.main()
