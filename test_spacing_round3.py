"""Regressions from the pre-restoration report; no movie directories are written."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import fix_english_punctuation_spacing as subject

PREFIX = "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,"
REGRESSIONS = [
    ("Farhan Qureshi. B.Tech. Engineer.", "Farhan Qureshi. B. Tech. Engineer."),
    ("Even, uh, Ph.D.'s...", "Even, uh, Ph. D. 's..."),
    ("IPR.VC", "IPR. VC"),
    ("That's how I got my M.D. and Ph.D. at the same time.", "That's how I got my M.D. and Ph. D. at the same time."),
    ("Ph.D. in Biochemistry from Stanford,", "Ph. D. in Biochemistry from Stanford,"),
    ("I also have a Ph.D. in calling people on their shit.", "I also have a Ph. D. in calling people on their shit."),
    ('but only flesh". "Merchant of Venice."', 'but only flesh"." Merchant of Venice."'),
    ("Don Mitchell, Jr.'s political career", "Don Mitchell, Jr. 's political career"),
    ("Jr.'s wife and son", "Jr. 's wife and son"),
    ('about a universal facebook within Harvard,\' he says."', 'about a universal facebook within Harvard, \' he says."'),
    ("tell him about your Ph.D.", "tell him about your Ph. D."),
    ("wall.e working to dig your own", "wall. e working to dig your own"),
    ("Wall.e.", "Wall. e."),
    ("Wall.e?", "Wall. e?"),
    ("Wall.e", "Wall. e"),
]


class RoundThreeTests(unittest.TestCase):
    def assert_stable(self, before, expected, terms=()):
        after = subject.normalize_english_segment(before, terms)
        self.assertEqual(expected, after)
        self.assertEqual(after, subject.normalize_english_segment(after, terms))

    def test_every_confirmed_report_regression_stays_intact(self):
        for original, _ in REGRESSIONS:
            with self.subTest(original=original):
                self.assert_stable(original, original)
                self.assertEqual([], subject.manual_review_reasons(PREFIX + original, PREFIX + original))

    def test_old_bad_outputs_are_detected_on_both_sides_of_quotes(self):
        for original, old_output in REGRESSIONS:
            with self.subTest(original=original):
                self.assertTrue(subject.manual_review_reasons(PREFIX + original, PREFIX + old_output))

    def test_multiletter_abbreviations_inflections_tags_and_sentence_end(self):
        for before, expected in [
            ("Ph.D.Next.", "Ph.D. Next."),
            ("He has a Ph.D", "He has a Ph.D"),
            ("B.Tech.,M.Tech. and LL.M.", "B.Tech., M.Tech. and LL.M."),
            ("His Ph.D.’s value,Jr.’s plan.", "His Ph.D.’s value, Jr.’s plan."),
            ("Dr.'s and Sr.'s notes.", "Dr.'s and Sr.'s notes."),
            ("Ph.D.'s. -Hello.", "Ph.D.'s.  - Hello."),
            (r"Ph.{\i1}D.{\i0}'s,Jr.{\i1}'s.", r"Ph.{\i1}D.{\i0}'s, Jr.{\i1}'s."),
            (r"B.{\i1}Tech.,yes.", r"B.{\i1}Tech., yes."),
            ("Mr.Saito,please. Next.Sentence.", "Mr. Saito, please. Next. Sentence."),
        ]:
            with self.subTest(before=before):
                self.assert_stable(before, expected)

    def test_names_custom_terms_and_unknown_dotted_identifiers(self):
        for before, expected in [
            ("IPR.VC.Next.", "IPR.VC. Next."),
            ("wall.e,hello. -Next.", "wall.e, hello.  - Next."),
            (r"Wall.{\i1}e,hi.", r"Wall.{\i1}e, hi."),
            (r"IPR.{\i1}VC,hi.", r"IPR.{\i1}VC, hi."),
            (r"https://example.{\i1}com, hi.", r"https://example.{\i1}com, hi."),
            (r"It is 3.{\i1}14mm,yes.", r"It is 3.{\i1}14mm, yes."),
            ("Hello.Next. Is this Mr.Smith?", "Hello. Next. Is this Mr. Smith?"),
        ]:
            with self.subTest(before=before):
                self.assert_stable(before, expected)
        self.assert_stable("ACME.XYZ,hello.", "ACME.XYZ,hello.")
        self.assertIn("DOTTED_TOKEN_REVIEW", subject.manual_review_reasons(PREFIX + "ACME.XYZ,hello.", PREFIX + "ACME.XYZ,hello."))
        self.assert_stable("ACME.XYZ,hello.", "ACME.XYZ, hello.", ("ACME.XYZ",))
        self.assert_stable("Hooli.Chat,hi.", "Hooli.Chat, hi.", ("Hooli.Chat",))
        self.assertEqual([], subject.manual_review_reasons(PREFIX + "ACME.XYZ,hello.", PREFIX + "ACME.XYZ, hello.", ("ACME.XYZ",)))

    def test_new_quote_after_a_closed_quote_is_an_opener(self):
        for before, expected in [
            ('flesh". "Merchant of Venice."', 'flesh". "Merchant of Venice."'),
            ('flesh"."Merchant of Venice."', 'flesh". "Merchant of Venice."'),
            (r'flesh".{\i1} "Merchant of Venice."', r'flesh".{\i1} "Merchant of Venice."'),
            ('flesh".  "Merchant." -Next.', 'flesh". "Merchant."  - Next.'),
            ("flesh'. 'Merchant of Venice.'", "flesh'. 'Merchant of Venice.'"),
            ('fine." And he left.', 'fine." And he left.'),
            ('weather..." Right.', 'weather..." Right.'),
            ('He said,"Hello."', 'He said, "Hello."'),
        ]:
            with self.subTest(before=before):
                self.assert_stable(before, expected)

    def test_cross_event_single_quote_and_real_elisions(self):
        for before, expected in [
            ("Harvard,' he says.", "Harvard,' he says."),
            ("Harvard,'he says.", "Harvard,' he says."),
            (r"Harvard,{\i0}' he says.", r"Harvard,{\i0}' he says."),
            ("fine.' Then he left.", "fine.' Then he left."),
            ("He said,'Hello.'", "He said, 'Hello.'"),
            ("You know,'cause I asked.", "You know, 'cause I asked."),
            ("He said, 'Hello.'", "He said, 'Hello.'"),
        ]:
            with self.subTest(before=before):
                self.assert_stable(before, expected)

    def test_source_ambiguities_are_preserved_and_listed(self):
        for original, reason in [
            ('"She\'s got a lot of signatures. "She\'ll ask really nicely?"', "SOURCE_QUOTE_STRUCTURE"),
            ("And don't ask for the fuckin' Wi- Fi, '", "SOURCE_DANGLING_APOSTROPHE"),
            ("Don't ask, ’", "SOURCE_DANGLING_APOSTROPHE"),
        ]:
            with self.subTest(original=original):
                self.assert_stable(original, original)
                self.assertIn(reason, subject.manual_review_reasons(PREFIX + original, PREFIX + original))
        for good in ['"A quotation begins...', 'the quotation ends."', "'Hello, '", 'flesh". "Merchant."', "...pass it onto him.'", "but the second mouse gets the cheese.'"]:
            self.assertNotIn("SOURCE_QUOTE_STRUCTURE", subject.manual_review_reasons(PREFIX + good, PREFIX + good))
            self.assertNotIn("SOURCE_DANGLING_APOSTROPHE", subject.manual_review_reasons(PREFIX + good, PREFIX + good))

    def test_source_detection_does_not_read_chinese_quotes_as_english_context(self):
        text = PREFIX + r'中文"这不影响英文"\N{\rEn}' + "Harvard,' he says.\""
        self.assertEqual(text, subject.fix_dialogue_line(text)[0])
        self.assertEqual([], subject.manual_review_reasons(text, text))
        text = PREFIX + r'"中文"多个"引号"\NHi,there.'
        # A Chinese visual segment must remain byte-for-byte unchanged.
        expected = text.replace("Hi,there.", "Hi, there.")
        self.assertEqual(expected, subject.fix_dialogue_line(text)[0])

    def test_cli_custom_protection_and_manual_only_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = PREFIX + '"She\'s got a lot. "She\'ll ask?"\n' + PREFIX + "Don't ask, '\n" + PREFIX + "ACME.XYZ,hi.\n"
            source = root / "sample.ass"
            source.write_text(original, encoding="utf-8")
            script = str(Path(subject.__file__).resolve())
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            def run(*args):
                return subprocess.run([sys.executable, "-B", script, str(root), *args], capture_output=True, text=True, encoding="utf-8", env=env)
            check = run("--check", "--protect", "ACME.XYZ")
            self.assertEqual(0, check.returncode, check.stderr)
            self.assertIn("Candidate lines: 2", check.stdout)
            self.assertFalse((root / "punctuation_fixed").exists())
            fixed = run("--protect", "ACME.XYZ", "--protect", "Hooli.Chat")
            self.assertEqual(0, fixed.returncode, fixed.stderr)
            report = (root / "punctuation_fixed" / "punctuation_manual_review.txt").read_text(encoding="utf-8")
            self.assertIn("SOURCE_QUOTE_STRUCTURE", report)
            self.assertIn("SOURCE_DANGLING_APOSTROPHE", report)
            self.assertIn("UNCHANGED:", report)
            self.assertEqual(original, source.read_text(encoding="utf-8"))
            self.assertEqual(original.replace("ACME.XYZ,hi.", "ACME.XYZ, hi."), (root / "punctuation_fixed" / "sample.ass").read_text(encoding="utf-8"))
            self.assertNotEqual(0, run("--check", "--protect", "").returncode)


if __name__ == "__main__":
    unittest.main()
