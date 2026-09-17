"""Regression tests. Run: python -m unittest -v test_punctuation_spacing.py"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import fix_english_punctuation_spacing as subject


class SpacingTests(unittest.TestCase):
    def check_cases(self, cases):
        for before, expected in cases:
            with self.subTest(before=before):
                actual = subject.normalize_english_segment(before)
                self.assertEqual(expected, actual)
                self.assertEqual(actual, subject.normalize_english_segment(actual))

    def test_two_speakers_all_marks_and_gaps(self):
        for mark in (",", ".", "...", "?", "!", "?!", "…"):
            for gap in ("", " ", "  ", "    ", "\t"):
                self.check_cases([(f"- Hi{mark}{gap}- Hello.", f"- Hi{mark}  - Hello.")])

    def test_single_speaker_and_non_speech_hyphens(self):
        self.check_cases([
            ("Hi,there.  How are you?", "Hi, there. How are you?"),
            ("Hi , there!  ", "Hi, there!"),
            ("It's a well-known fact.", "It's a well-known fact."),
            ("The reading is. -5 degrees.", "The reading is. -5 degrees."),
            ("I...--wait.", "I... --wait."),
            ("-Hi.-Hello.", "- Hi.  - Hello."),
        ])

    def test_high_confidence_redundant_punctuation(self):
        self.check_cases([
            ("What.?", "What?"),
            ("Where..?", "Where?"),
            ("Stop.!", "Stop!"),
            ("Stop!.", "Stop!"),
            ("Really?. Next.", "Really? Next."),
            ("word., next.", "word, next."),
            ("word., Next.", "word. Next."),
            ("word.,", "word."),
            ('It was like, "Hiya!".', 'It was like, "Hiya!"'),
            ('It was like, "Hiya!". Next.', 'It was like, "Hiya!" Next.'),
            ('He wrote "word"., then left.', 'He wrote "word", then left.'),
        ])

    def test_legitimate_multiple_punctuation_and_abbreviations_are_protected(self):
        self.check_cases([
            ("Wait...?", "Wait...?"),
            ("What?!", "What?!"),
            ("Really!?", "Really!?"),
            ("No!... Next.", "No!... Next."),
            ("Is it 2:00 A.M.?", "Is it 2:00 A.M.?"),
            ("What about Mr. Dawes, Jr.?", "What about Mr. Dawes, Jr.?"),
            ("It's not S.H.I.E.L.D., it's HYDRA.", "It's not S.H.I.E.L.D., it's HYDRA."),
            ("R. F., you're cute.", "R. F., you're cute."),
            ("I say K. S. M., you answer.", "I say K. S. M., you answer."),
            ("Lamont Pictures, lnc.?", "Lamont Pictures, lnc.?"),
            ('"Who are we?", "How did we get here?",',
             '"Who are we?", "How did we get here?",'),
        ])

        prefix = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
        before = prefix + "What.?"
        after = subject.fix_dialogue_line(before)[0]
        self.assertEqual(prefix + "What?", after)
        self.assertNotIn("NON_WHITESPACE_CHANGE",
                         subject.manual_review_reasons(before, after))

        ambiguous = prefix + "gold-plated,. 50 caliber"
        self.assertEqual(ambiguous, subject.fix_dialogue_line(ambiguous)[0])
        self.assertIn("SOURCE_REDUNDANT_PUNCTUATION_AMBIGUOUS",
                      subject.manual_review_reasons(ambiguous, ambiguous))

        self.check_cases([
            ("two gold-plated,.50 caliber pistols.",
             "two gold-plated, .50 caliber pistols."),
            ("two gold-plated, .50 caliber pistols.",
             "two gold-plated, .50 caliber pistols."),
        ])

    def test_split_contractions_and_apostrophe_safety(self):
        self.check_cases([
            ("I'm not sure if we 're on the air.",
             "I'm not sure if we're on the air."),
            ("I ' m ready; you ' ve been warned.",
             "I'm ready; you've been warned."),
            ("They ' ll know, and she ' d agree.",
             "They'll know, and she'd agree."),
            ("We ’ re ready and it ’ s time.",
             "We’re ready and it’s time."),
            ("We do n't know and ca n't wait.",
             "We don't know and can't wait."),
            ("You do n ' t know and wo n ’ t ask.",
             "You don't know and won’t ask."),
            (r"we {\i1}' re{\i0} ready.", r"we{\i1}'re{\i0} ready."),
            ("He said 'really' and left.", "He said 'really' and left."),
            ("What's the 'S' stand for?", "What's the 'S' stand for?"),
            ("It's not an 'S'. On my world it means 'hope'.",
             "It's not an 'S'. On my world it means 'hope'."),
            ("They call we 're' strange.", "They call we 're' strange."),
            ("Lefferts' mother I.D.'d him.", "Lefferts' mother I.D.'d him."),
        ])

        prefix = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
        for text in ("Alex 's car.", "He said 's okay.'"):
            with self.subTest(ambiguous=text):
                before = prefix + text
                after = subject.fix_dialogue_line(before)[0]
                self.assertEqual(before, after)
                self.assertIn(
                    "SOURCE_SPLIT_APOSTROPHE_AMBIGUOUS",
                    subject.manual_review_reasons(before, after),
                )

        for text in (
            "What's the 'S' stand for?",
            "It's not an 'S'. On my world it means 'hope'.",
        ):
            with self.subTest(quoted_token=text):
                before = prefix + text
                self.assertEqual([], subject.manual_review_reasons(before, before))

    def test_continuation_ellipses_at_each_speaker(self):
        self.check_cases([
            ("...pay my respects.", "...pay my respects."),
            ("... spilling my guts...", "...spilling my guts..."),
            ("If you could...Please.", "If you could... Please."),
            ("- ...three... humped... - Please just...", "- ...three... humped...  - Please just..."),
            ("- you could run a... - ...for you...", "- you could run a...  - ...for you..."),
            ("- No! - ...you call a...", "- No!  - ...you call a..."),
            ("- Chaz, out. - ... report", "- Chaz, out.  - ...report"),
            ("- ...the right place. - We are here.", "- ...the right place.  - We are here."),
            ("-Hi. -...hello", "- Hi.  - ...hello"),
            ("-Hi.-... hello", "- Hi.  - ...hello"),
            ("- Hi.  - ...hello", "- Hi.  - ...hello"),
            ("… hello", "…hello"),
            ("Well…hello", "Well… hello"),
            ("3.14...Next", "3.14... Next"),
        ])

    def test_quotes_opened_in_current_or_previous_event(self):
        self.check_cases([
            ('will shine upon the key-hole."', 'will shine upon the key-hole."'),
            ('will shine upon the key-hole. "', 'will shine upon the key-hole."'),
            ('...benefits? "  ', '...benefits?"'),
            ('and sing \'Kumbaya."\'', 'and sing \'Kumbaya."\''),
            ('He said,"Hello."', 'He said, "Hello."'),
            ('"Yes,"she said.', '"Yes," she said.'),
            ('The key-hole." - Next.', 'The key-hole."  - Next.'),
            ('The key-hole."-...next.', 'The key-hole."  - ...next.'),
            ('"Hi." - "Hello."', '"Hi."  - "Hello."'),
            ('He said,"...hello."', 'He said, "... hello."'),
            ('- ...you... - Thank you. "2-9-T-H-D-0-3."',
             '- ...you...  - Thank you. "2-9-T-H-D-0-3."'),
        ])

    def test_ass_tags_numbers_and_initialisms(self):
        self.check_cases([
            (r'{\pos(640,65)}Hi. {\i0}- Hello.', r'{\pos(640,65)}Hi.{\i0}  - Hello.'),
            (r'Hi.{\i0} - Hello.', r'Hi.{\i0}  - Hello.'),
            (r'Hi. {\i0}  ', r'Hi.{\i0}'),
            (r'Hi.{\i0}"', r'Hi.{\i0}"'),
            (r'- Hi. - {\i1}... hello', r'- Hi.  - {\i1}...hello'),
            (r'{\i1}... hello', r'{\i1}...hello'),
            ("It's 3.14, 1,000 and U.S.A. territory.", "It's 3.14, 1,000 and U.S.A. territory."),
            ("Mr.Saito,please.", "Mr. Saito, please."),
            ("Visit example.com.Now", "Visit example.com. Now"),
        ])

    def test_one_space_after_each_speaker_prefix(self):
        for first_gap in ("", " ", "  ", "   ", "\t"):
            for second_gap in ("", " ", "  ", "   ", "\t"):
                self.check_cases([
                    (f"-{first_gap}Hi. -{second_gap}Hello.", "- Hi.  - Hello."),
                    (f"-{first_gap}Hi. -{second_gap}...hello", "- Hi.  - ...hello"),
                ])
        self.check_cases([
            ("- Is it possible?  -  Of course not.", "- Is it possible?  - Of course not."),
            ("-  I know this is hard, but it's imperative... -   Not now, Uncle Peter.",
             "- I know this is hard, but it's imperative...  - Not now, Uncle Peter."),
            ("- Hi -Hello", "- Hi - Hello"),
            ('{\\rEng}-\tHi.', r'{\rEng}- Hi.'),
            (r'-{\i1}Hi. -  {\i0}  Hello.', r'- {\i1}Hi.  - {\i0}Hello.'),
            (r'{\i1}-  ... hi', r'{\i1}- ...hi'),
            ('"-Hi."', '"- Hi."'),
            ("- A well-known re-entry plan.", "- A well-known re-entry plan."),
            ("-5 degrees, then -3.14 degrees.", "-5 degrees, then -3.14 degrees."),
            ("--wait", "--wait"),
            ("The option is --check.", "The option is --check."),
        ])

    def test_dialogue_fields_chinese_and_line_breaks(self):
        prefix = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,NTP,0,0,0,!Effect,"
        before = prefix + r'中文,不变.  - 中文\N{\rEng}- Hi. - Hello. \N... next.'
        expected = prefix + r'中文,不变.  - 中文\N{\rEng}- Hi.  - Hello.\N...next.'
        self.assertEqual((expected, True, True), subject.fix_dialogue_line(before))
        self.assertFalse(subject.fix_dialogue_line(expected)[1])

    def test_numbers_with_units_and_leading_dot_decimals(self):
        self.check_cases([
            ("with a relative position of 100,000km to Earth.",
             "with a relative position of 100,000km to Earth."),
            ("is over 70,000km.", "is over 70,000km."),
            ("8,000km.5,000km.", "8,000km. 5,000km."),
            ("Carbon fiber, .28 caliber, made in China.",
             "Carbon fiber, .28 caliber, made in China."),
            ("It is .28mm,3.14mm or 1,234.56kg.",
             "It is .28mm, 3.14mm or 1,234.56kg."),
            ("At -.28 degrees. -5 degrees.", "At -.28 degrees. -5 degrees."),
            ("Count...5...4...3.", "Count... 5... 4... 3."),
            ("Pay 1,000!Next.", "Pay 1,000! Next."),
        ])

    def test_elisions_are_not_quotation_marks(self):
        self.check_cases([
            ("You know, 'cause... 'cause I could get used to that.",
             "You know, 'cause... 'cause I could get used to that."),
            ("You know, ’cause... ’cause I could get used to that.",
             "You know, ’cause... ’cause I could get used to that."),
            ("Get 'em, 'em all!", "Get 'em, 'em all!"),
            ("Wait,'til tomorrow.", "Wait, 'til tomorrow."),
            ("Back in the '90s, 'cause we could.", "Back in the '90s, 'cause we could."),
            ("He said,'Hello.'", "He said, 'Hello.'"),
            ("'Yes,'she said.", "'Yes,' she said."),
        ])

    def test_closing_quote_with_following_punctuation(self):
        self.check_cases([
            ('we did not want him to act."?', 'we did not want him to act."?'),
            ('we did not want him to act. "?  ', 'we did not want him to act."?'),
            ('end."?Next.', 'end."? Next.'),
            ('end."? -Next.', 'end."?  - Next.'),
            ('He said,"...hello."', 'He said, "... hello."'),
            (r'end.{\i0}"? ', r'end.{\i0}"?'),
        ])

    def test_separated_ellipses_remain_separate(self):
        self.check_cases([
            ("I just... ...didn't know...", "I just... ...didn't know..."),
            ("Okay, well... ...good night.", "Okay, well... ...good night."),
            ("Well, you know... ...most of him.", "Well, you know... ...most of him."),
            ("Oh, and, um… …as regards to the union,", "Oh, and, um… …as regards to the union,"),
            ("Digital cable brings you... ...Columbia Broadcasting System...",
             "Digital cable brings you... ...Columbia Broadcasting System..."),
            ("Hiccup! ...double-barreled.", "Hiccup! ...double-barreled."),
            ("Hi. ... Next.", "Hi. ... Next."),
            ("Hi...  ...next.", "Hi...  ...next."),
            ("Hi...\t...next.", "Hi...\t...next."),
            ("Hi... ... next. ", "Hi... ... next."),
            ("Hi... ... -Next.", "Hi... ...  - Next."),
            (r'Hi... {\i1}...next.', r'Hi...{\i1} ...next.'),
            ("Hi. . .", "Hi..."),
            ("-... hi. -... next", "- ...hi.  - ...next"),
        ])

    def test_inverted_marks_and_ambiguous_source_marks(self):
        self.check_cases([
            ("Miles? ¿Qué te pasa?", "Miles? ¿Qué te pasa?"),
            ("¡Ah! ¿De dónde eres?", "¡Ah! ¿De dónde eres?"),
            ("-¡Hola! -¿Qué pasa?", "- ¡Hola!  - ¿Qué pasa?"),
            ("¿Qué pasa?¡No!", "¿Qué pasa? ¡No!"),
            ("¿ Qué pasa ? ¡ Hola ! ", "¿Qué pasa? ¡Hola!"),
            (r'¿ {\i1} Qué pasa? ¡{\i0} Hola!', r'¿{\i1}Qué pasa? ¡{\i0}Hola!'),
            ("¿¡Qué!?", "¿¡Qué!?"),
            ("- ¿Vámanos! - It's \"Andiamo.\"", "- ¿Vámanos!  - It's \"Andiamo.\""),
            # A possible missing inverted mark is not a safe spacing fix.
            ("Miles? ?Qué te pasa?", "Miles? ?Qué te pasa?"),
            ("- ?Vámanos! - It's Andiamo.", "- ?Vámanos! - It's Andiamo."),
            ("!Ah! De dónde eres?", "!Ah! De dónde eres?"),
            (r'{\rEng}-?{\i1}Qué?', r'{\rEng}-?{\i1}Qué?'),
        ])

    def test_cross_event_closing_quotes_with_following_sentence(self):
        self.check_cases([
            ('Like crazy-stupid fine." And he', 'Like crazy-stupid fine." And he'),
            ('and that\'s final." Those were his words.', 'and that\'s final." Those were his words.'),
            ('with the weather..." Right.', 'with the weather..." Right.'),
            ('have this wish..." Huh?   -Señor Horner!', 'have this wish..." Huh?  - Señor Horner!'),
            ('key-hole?" Yes.', 'key-hole?" Yes.'),
            ('key-hole!" Yes.', 'key-hole!" Yes.'),
            ('the weather…" Right.', 'the weather…" Right.'),
            ('..." Right.', '..." Right.'),
            ('…" Right.', '…" Right.'),
            ('fine."And he,said.', 'fine." And he, said.'),
            (r'fine.{\i0}" And he', r'fine.{\i0}" And he'),
            ('end. "New quotation."', 'end. "New quotation."'),
            ('U.S.A." Then he left.', 'U.S.A." Then he left.'),
        ])

    def test_inflected_initialisms(self):
        self.check_cases([
            ("Lefferts' mother I.D.'d Stensland as Lefferts' boyfriend.",
             "Lefferts' mother I.D.'d Stensland as Lefferts' boyfriend."),
            ("He I.D.’d him,and left.", "He I.D.’d him, and left."),
            ("The U.S.'s plan is O.K.'d.", "The U.S.'s plan is O.K.'d."),
            ("He I.D.'d. -Hello.", "He I.D.'d.  - Hello."),
            (r"{\i1}I.D.'d{\i0},yes.", r"{\i1}I.D.'d{\i0}, yes."),
            (r"I.D.{\i0}'d him.", r"I.D.{\i0}'d him."),
            (r"I.{\i1}D.'d him.", r"I.{\i1}D.'d him."),
            (r"I.D.'{\i1}d him.", r"I.D.'{\i1}d him."),
            (r"I.{\i1}D.{\i0}'d him,I.D.'d her.", r"I.{\i1}D.{\i0}'d him, I.D.'d her."),
            ("I'm I.D.'ing them.", "I'm I.D.'ing them."),
            ("I.D. Next.", "I.D. Next."),
        ])

    def test_spaced_leading_ellipsis_is_stable(self):
        self.check_cases([
            (". . . let him go.", "...let him go."),
            (". . . minutes by myself.", "...minutes by myself."),
            ("- . . . hello. -Next.", "- ...hello.  - Next."),
            (r'{\rEng}. . . let me go.', r'{\rEng}...let me go.'),
            ("Hi. . . Next.", "Hi... Next."),
            ("Hi... ...next.", "Hi... ...next."),
        ])

    def test_manual_review_includes_unchanged_source_and_excludes_protected_forms(self):
        prefix = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
        for text, expected in [
            ("1No.", "SOURCE_DIGIT_FOR_DASH"),
            ("the 1998 filmShakespeare in love.", "SOURCE_WORDS_JOINED"),
            ("?Qué pasa?", "SUSPECT_OPENING_MARK"),
            ('Miles? ?Qué te pasa?', 'SUSPECT_OPENING_MARK'),
            ("'Yes! 'Yes!", "SOURCE_QUOTE_AMBIGUOUS"),
            ('."Sep tu a centennial"', "SOURCE_QUOTE_AMBIGUOUS"),
        ]:
            with self.subTest(text=text):
                before = prefix + text
                after = subject.fix_dialogue_line(before)[0]
                self.assertIn(expected, subject.manual_review_reasons(before, after))
        for text in [
            "¿Qué pasa? ¡Hola!", "I.D.'d him.", 'fine." And he left.',
            'weather..." Right.', 'He said,"Hello."', '"Yes,"she said.',
            r'中文1No,filmShakespeare?什么\N{\rEng}Hello.',
        ]:
            with self.subTest(text=text):
                before = prefix + text
                after = subject.fix_dialogue_line(before)[0]
                self.assertEqual([], subject.manual_review_reasons(before, after))
        before = prefix + "I.D.'d him."
        self.assertIn("APOSTROPHE_SPLIT", subject.manual_review_reasons(before, prefix + "I.D.' d him."))
        self.assertIn("QUOTE_GAP_ADDED", subject.manual_review_reasons(prefix + 'fine." And', prefix + 'fine. " And'))

    def test_cli_always_saves_manual_review_and_check_does_not_write(self):
        script = Path(subject.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            prefix = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
            suspect = nested / "suspect.ass"
            source = (prefix + "1No.\r\n" + prefix + "?Qué pasa?\r\n").encode("utf-8-sig")
            suspect.write_bytes(source)
            good = root / "good.ass"
            good.write_text(prefix + "¿Qué pasa?\n", encoding="utf-8")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            def run(*args):
                return subprocess.run([sys.executable, "-B", str(script), str(root), "--recursive", *args],
                                      capture_output=True, text=True, encoding="utf-8",
                                      check=True, env=env).stdout
            console = run("--check")
            self.assertIn("Files with problems: 0", console)
            self.assertIn("Candidate files: 1", console)
            self.assertIn(str(suspect), console)
            self.assertNotIn("All scanned ASS files passed", console)
            self.assertFalse((root / "punctuation_fixed").exists())
            console = run()
            self.assertNotIn("UNCHANGED:", console)
            report_path = root / "punctuation_fixed" / "punctuation_manual_review.txt"
            report = report_path.read_bytes()
            self.assertIn("UNCHANGED: " + prefix + "1No.", report.decode("utf-8"))
            self.assertIn("Candidate lines: 2", report.decode("utf-8"))
            self.assertEqual(source, suspect.read_bytes())
            self.assertFalse((root / "punctuation_fixed" / "nested" / "suspect.ass").exists())
            self.assertIn("UNCHANGED:", run("--check", "--details"))
            self.assertEqual(report, report_path.read_bytes())
            # A new run replaces the old list even when every candidate is resolved.
            suspect.write_text(prefix + "¿Qué pasa?\n", encoding="utf-8")
            run()
            self.assertIn("Candidate files: 0", report_path.read_text(encoding="utf-8"))
            self.assertNotIn("SOURCE_DIGIT_FOR_DASH", report_path.read_text(encoding="utf-8"))

    def test_legacy_windows_pipe_encoding_does_not_abort_reports(self):
        script = Path(subject.__file__).resolve()
        env = dict(os.environ, PYTHONIOENCODING="gbk:strict")
        help_result = subprocess.run([sys.executable, "-B", str(script), "--help"],
                                     capture_output=True, check=True, env=env)
        self.assertIn(b"--recursive", help_result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spanish.ass"
            prefix = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
            source.write_text(prefix + "¿ Qué? !Ah!\n" + prefix + "¡ Hola !\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(script), str(source)],
                                    capture_output=True, check=True, env=env)
            self.assertIn(b"Manual-review report:", result.stdout)
            out_dir = Path(directory) / "punctuation_fixed"
            self.assertIn("¿ Qué? !Ah!", (out_dir / "punctuation_manual_review.txt").read_text(encoding="utf-8"))
            self.assertIn("¡Hola!", (out_dir / "punctuation_fix_report.txt").read_text(encoding="utf-8"))

    def test_cli_check_and_fix_preserve_source(self):
        script = Path(subject.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            line = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
            bad = root / "bad.ass"
            bad.write_bytes(("[Events]\r\n" + line + "- Hi. - Hello.\r\n").encode("utf-8-sig"))
            good = root / "good.ass"
            good.write_bytes(("[Events]\r\n" + line + "- Hi.  - Hello.\r\n").encode("utf-8-sig"))
            original = bad.read_bytes()
            env = dict(os.environ, PYTHONIOENCODING="utf-8")

            def run(*args):
                return subprocess.run([sys.executable, str(script), *map(str, args)],
                                      capture_output=True, text=True, encoding="utf-8",
                                      check=True, env=env).stdout

            single = run(bad, "--check")
            self.assertIn("Line 2", single)
            self.assertIn("AFTER", single)
            multi = run(root, "--check")
            self.assertIn("bad.ass", multi)
            self.assertNotIn("good.ass", multi)
            self.assertNotIn("BEFORE", multi)
            self.assertFalse((root / "punctuation_fixed").exists())
            console = run(root)
            self.assertNotIn("BEFORE", console.replace("Full BEFORE/AFTER report:", ""))
            full_report = (root / "punctuation_fixed" / "punctuation_fix_report.txt").read_text(encoding="utf-8")
            self.assertIn("Files with problems:", full_report)
            self.assertIn("File: bad.ass", full_report)
            self.assertIn("Line 2", full_report)
            self.assertEqual(1, full_report.count("    BEFORE:"))
            self.assertEqual(1, full_report.count("    AFTER :"))
            self.assertIn(subject.SCRIPT_VERSION, full_report)
            self.assertEqual(original, bad.read_bytes())
            fixed = root / "punctuation_fixed" / "bad.ass"
            unchanged_copy = root / "punctuation_fixed" / "good.ass"
            self.assertFalse(unchanged_copy.exists())
            self.assertIn("Files with problems: 0", run(fixed, "--check"))
            self.assertEqual(original.replace(b"Hi. -", b"Hi.  -"), fixed.read_bytes())
            self.assertIn("ASS files scanned: 2", run(root, "--recursive", "--check"))

            # Once the source is corrected, a copy from the previous run must
            # not remain and masquerade as a newly changed file.
            bad.write_bytes(fixed.read_bytes())
            console = run(root)
            self.assertIn("Changed ASS copies written: 0", console)
            self.assertIn("Stale unchanged ASS copies removed: 1", console)
            self.assertFalse(fixed.exists())
            self.assertTrue((root / "punctuation_fixed" / "punctuation_fix_report.txt").exists())

    def test_cli_full_report_is_not_truncated_and_recursive_is_opt_in(self):
        script = Path(subject.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
            long_text = "word " * 100 + "Hi,there."
            original = (prefix + long_text + "\n") * 250
            (root / "top.ass").write_bytes(original.encode("utf-8"))
            nested = root / "nested"
            nested.mkdir()
            (nested / "top.ass").write_bytes(original.encode("utf-8"))
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            def run(*args):
                return subprocess.run([sys.executable, str(script), str(root), *args],
                                      capture_output=True, text=True, encoding="utf-8",
                                      check=True, env=env).stdout
            self.assertIn("ASS files scanned: 1", run("--check"))
            self.assertFalse((root / "punctuation_fixed").exists())
            self.assertIn("ASS files scanned: 2", run("--recursive"))
            report_path = root / "punctuation_fixed" / "punctuation_fix_report.txt"
            report = report_path.read_text(encoding="utf-8")
            self.assertEqual(500, report.count("    BEFORE:"))
            self.assertEqual(500, report.count("    AFTER :"))
            self.assertIn(prefix + long_text, report)
            self.assertIn("Line 250", report)
            before_check = report_path.read_bytes()
            self.assertIn("BEFORE:", run("--recursive", "--check", "--details"))
            self.assertEqual(before_check, report_path.read_bytes())
            self.assertEqual(original.encode("utf-8"), (root / "top.ass").read_bytes())


if __name__ == "__main__":
    unittest.main()
