"""TV report regressions; fixtures are local strings/temporary files only."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fix_english_punctuation_spacing as subject

PREFIX = 'Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,'


class TVSpacingTests(unittest.TestCase):
    def check_cases(self, cases, no_manual=True):
        for before, expected in cases:
            with self.subTest(before=before):
                actual = subject.normalize_english_segment(before)
                self.assertEqual(expected, actual)
                self.assertEqual(actual, subject.normalize_english_segment(actual))
                if no_manual:
                    self.assertEqual([], subject.manual_review_reasons(PREFIX + before, PREFIX + actual))

    def test_two_dot_continuations_and_speaker_gaps(self):
        self.check_cases([
            ('..And she ended up with his brother,', '..And she ended up with his brother,'),
            ('.. and then.', '..and then.'),
            ('- ..Word. -Next.', '- ..Word.  - Next.'),
            ('-Yes? - ..Has just...', '- Yes?  - ..Has just...'),
            ('- "..Evil." - "..Dust."', '- "..Evil."  - "..Dust."'),
            ('.."footloose and fancy-free" -', '.."footloose and fancy-free" -'),
            ("'..which was discovered...18 months ago.", "'..which was discovered... 18 months ago."),
            (r'-{\i1}.. hello. -{\i0}..there.', r'- {\i1}..hello.  - {\i0}..there.'),
            ('Wait..Next.', 'Wait.. Next.'),
            ('..5 minutes.', '..5 minutes.'),
            ('Value .28mm,please.', 'Value .28mm, please.'),
        ])

    def test_separate_two_dot_groups_are_not_merged(self):
        self.check_cases([
            ('Well... ..That is not what I...', 'Well... ..That is not what I...'),
            ('Well...  ..That.', 'Well...  ..That.'),
            ('Atal... ..Hurun.', 'Atal... ..Hurun.'),
            ('Toby all right? ..Good.', 'Toby all right? ..Good.'),
            ('Hi. .. -Next.', 'Hi. ..  - Next.'),
            ('Yeah. ..', 'Yeah. ..'),
            (r'Well... {\i1}..That.', r'Well...{\i1} ..That.'),
            ('Hi. . . Next.', 'Hi... Next.'),
        ])

    def test_ambiguous_single_dots_are_preserved(self):
        for before in ['Ooh! .which is BBC money.', '- Take it. - Mm? .', 'and then you. .']:
            with self.subTest(before=before):
                self.assertEqual(before, subject.normalize_english_segment(before))
                self.assertIn('SOURCE_SEPARATE_DOT', subject.manual_review_reasons(PREFIX + before, PREFIX + before))

    def test_lyric_closing_wrappers_keep_their_original_style(self):
        self.check_cases([
            ('*Sherlock is dying.*', '*Sherlock is dying.*'),
            ('*Hello ,world!*', '*Hello, world!*'),
            ('*My little master...*', '*My little master...*'),
            ('♪Hello...♪', '♪Hello...♪'),
            ('♪ Hello ,world!  ♪', '♪ Hello, world!  ♪'),
            ('♫Hello.♫', '♫Hello.♫'),
            ('*"Get yourself a job!"*', '*"Get yourself a job!"*'),
            ('*Ph.D.,hello.*', '*Ph.D., hello.*'),
            ('*Hello.*  ', '*Hello.*'),
            (r'*Hello.{\i0}*', r'*Hello.{\i0}*'),
            (r'*Hello! {\i0} *', r'*Hello! {\i0} *'),
            ('What the f***,now?', 'What the f***, now?'),
            ('Use 2*3,then 4*5.', 'Use 2*3, then 4*5.'),
        ])

    def test_lyric_openers_and_new_speakers(self):
        self.check_cases([
            ('*..Brother, and under we go.*', '*..Brother, and under we go.*'),
            ('♪..And the moment♪', '♪..And the moment♪'),
            ('* ... hello.*', '* ...hello.*'),
            ('- *Not me!* -Next.', '- *Not me!*  - Next.'),
            ('- *Not me!* - *You too!*', '- *Not me!*  - *You too!*'),
            ('-Hi. -*.. hello!*', '- Hi.  - *..hello!*'),
            ('*-Hi. -Hello.*', '*- Hi.  - Hello.*'),
            (r'-*Hi!{\i0}* -{\i1}There.', r'- *Hi!{\i0}*  - {\i1}There.'),
        ])

    def test_new_opening_quote_is_not_a_cross_event_closer(self):
        self.check_cases([
            ('What do real people have, then, in their..."real lives"?',
             'What do real people have, then, in their... "real lives"?'),
            ('Nothing, just..."Welcome to London."', 'Nothing, just... "Welcome to London."'),
            ('Like real..."I\'m not messing around"-type guns?',
             'Like real... "I\'m not messing around"-type guns?'),
            (r'their...{\i1}"real lives"?', r'their...{\i1} "real lives"?'),
            ('He said,"Hello."', 'He said, "Hello."'),
            ('fine." And then "Goodbye."', 'fine." And then "Goodbye."'),
            ('fine."Then he left.', 'fine." Then he left.'),
            ('weather..." Right.', 'weather..." Right.'),
            ('flesh". "Merchant of Venice."', 'flesh". "Merchant of Venice."'),
        ])

    def test_cross_event_comma_closing_quote(self):
        self.check_cases([
            ('Our government is now the cream of the crop," and so on.',
             'Our government is now the cream of the crop," and so on.'),
            ('it\'s reality, but enough from me," yadda, yadda, yadda, then it\'s...',
             'it\'s reality, but enough from me," yadda, yadda, yadda, then it\'s...'),
            (r'crop,{\i0}" and so on.', r'crop,{\i0}" and so on.'),
            ('He said, "Hello."', 'He said, "Hello."'),
            ('He said,"Hello."', 'He said, "Hello."'),
            ('"Yes,"she said.', '"Yes," she said.'),
        ])

    def test_compound_suffixes_are_not_speaker_dashes(self):
        self.check_cases([
            ('A "do it yourself"-type plan.', 'A "do it yourself"-type plan.'),
            ('A "wow!"-type plan.', 'A "wow!"-type plan.'),
            (r'A "wow!"{\i1}-type plan.', r'A "wow!"{\i1}-type plan.'),
            ('A "story"-based game.', 'A "story"-based game.'),
            ('"Go."-Next.', '"Go."  - Next.'),
            ('"Go." -Next.', '"Go."  - Next.'),
            ('"Go." -type this.', '"Go."  - type this.'),
            ('"Go."-Type this.', '"Go."  - Type this.'),
        ])

    def test_elisions_and_repeated_fragments(self):
        self.check_cases([
            ("'Ello, 'ello, 'ello, what's going on 'ere then?", "'Ello, 'ello, 'ello, what's going on 'ere then?"),
            ("'Ello,'ello!", "'Ello, 'ello!"),
            ("- 'ru... 'ru... - And get a version of you", "- 'ru... 'ru...  - And get a version of you"),
            ("- ’ru... ’ru... -Next.", "- ’ru... ’ru...  - Next."),
            (r"'r{\i1}u... 'ru... -Next.", r"'r{\i1}u... 'ru...  - Next."),
            ("'It is a tale.' Next.", "'It is a tale.' Next."),
            ("He said,'Hello.'", "He said, 'Hello.'"),
        ])

    def test_dirty_thousands_and_tags(self):
        self.check_cases([
            ('over 1 ,000 metres per second.', 'over 1,000 metres per second.'),
            ('Over 1 ,000 years old', 'Over 1,000 years old'),
            ('Pay 12 ,345 ,678.90,now.', 'Pay 12,345,678.90, now.'),
            ('It is -1 ,000km,yes.', 'It is -1,000km, yes.'),
            (r'1 {\fnTimes New Roman},000km,yes.', r'1{\fnTimes New Roman},000km, yes.'),
            ('Pick 1, 2, 3.', 'Pick 1, 2, 3.'),
            ('It is 1,234.56,not 3.14.', 'It is 1,234.56, not 3.14.'),
        ])
        for before in ['Pick 1 , 2.', 'Value 3 . 14.', 'Value 1000 ,000.']:
            self.assertEqual(before, subject.normalize_english_segment(before))
            self.assertIn('SOURCE_NUMBER_SPACING', subject.manual_review_reasons(PREFIX + before, PREFIX + before))

    def test_ambiguous_repeated_openers_are_not_repaired_by_parity(self):
        for before in ["'They built the platforms, 'even the staircases,", "'It is a tale. 'Told by an idiot,"]:
            self.assertEqual(before, subject.normalize_english_segment(before))
            self.assertIn('SOURCE_REPEATED_OPENING_QUOTE', subject.manual_review_reasons(PREFIX + before, PREFIX + before))

    def test_normal_closing_quote_gap_is_not_an_elision_split(self):
        self.check_cases([
            ("'Who Do You Think You Are?'tonight", "'Who Do You Think You Are?' tonight"),
            ("'Yes,'she said.", "'Yes,' she said."),
            ("fine.'Then he left.", "fine.' Then he left."),
        ])
        self.assertIn('APOSTROPHE_SPLIT', subject.manual_review_reasons(PREFIX + "I.D.'d him.", PREFIX + "I.D.' d him."))

    def test_independent_audit_catches_old_bad_outputs(self):
        cases = [
            ('..And she left.', '.. And she left.'),
            ('Well... ..That.', 'Well..... That.'),
            ('*Hello.*', '*Hello. *'),
            ('♪Hello...♪', '♪Hello... ♪'),
            ('their..."real lives"?', 'their..." real lives"?'),
            ('crop," and so on.', 'crop, " and so on.'),
            ('A "word"-type plan.', 'A "word"- type plan.'),
            ("'Ello, 'ello!", "'Ello,' ello!"),
            ("'ru... 'ru...", "'ru...' ru..."),
            ('over 1 ,000 metres.', 'over 1, 000 metres.'),
        ]
        for before, bad in cases:
            with self.subTest(before=before):
                self.assertTrue(subject.manual_review_reasons(PREFIX + before, PREFIX + bad))

    def test_safety_veto_and_manual_reason_survive_preserving_original(self):
        subject._normalize_segment_result.cache_clear()
        try:
            with patch.object(subject, '_normalize_english_segment_unchecked', return_value='*Hello. *'):
                self.assertEqual('*Hello.*', subject.normalize_english_segment('*Hello.*'))
                codes = subject.manual_review_reasons(PREFIX + '*Hello.*', PREFIX + '*Hello.*')
                self.assertIn('AUTO_CHANGE_BLOCKED', codes)
                self.assertIn('LYRIC_BOUNDARY_CHANGED', codes)
        finally:
            subject._normalize_segment_result.cache_clear()

    def test_safety_veto_rejects_text_or_tag_corruption(self):
        for before, bad, reason in [
            ('Hello.', 'Goodbye.', 'NON_WHITESPACE_CHANGE'),
            (r'{\fnTimes New Roman}Hello.', r'{\fnTimesNewRoman}Hello.', 'ASS_TAG_CHANGE'),
        ]:
            with self.subTest(before=before):
                subject._normalize_segment_result.cache_clear()
                try:
                    with patch.object(subject, '_normalize_english_segment_unchecked', return_value=bad):
                        self.assertEqual(before, subject.normalize_english_segment(before))
                        codes = subject.manual_review_reasons(PREFIX + before, PREFIX + before)
                        self.assertIn('AUTO_CHANGE_BLOCKED', codes)
                        self.assertIn(reason, codes)
                finally:
                    subject._normalize_segment_result.cache_clear()

    def test_ambiguous_english_segment_does_not_block_other_visual_lines(self):
        before = PREFIX + r'中文,不改.\N' + "'They built, 'even more," + r'\NHi,there.'
        after = before.replace('Hi,there.', 'Hi, there.')
        self.assertEqual(after, subject.fix_dialogue_line(before)[0])
        self.assertIn('SOURCE_REPEATED_OPENING_QUOTE', subject.manual_review_reasons(before, after))

    def test_recursive_cli_copies_reports_and_check_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / 'season'
            nested.mkdir()
            source = nested / 'sample.ass'
            text = (PREFIX + '*Hello.*\r\n' + PREFIX + '..Next,please.\r\n' +
                    PREFIX + "'They built, 'even more,\r\n" + PREFIX + 'over 1 ,000 years.\r\n')
            raw = text.encode('utf-8-sig')
            source.write_bytes(raw)
            script = str(Path(subject.__file__).resolve())
            env = dict(os.environ, PYTHONIOENCODING='utf-8')
            def run(*args):
                return subprocess.run([sys.executable, '-B', script, str(root), '--recursive', *args],
                                      capture_output=True, text=True, encoding='utf-8', check=True, env=env).stdout
            checked = run('--check', '--details')
            self.assertIn('Candidate lines: 1', checked)
            self.assertFalse((root / 'punctuation_fixed').exists())
            run()
            output = root / 'punctuation_fixed'
            expected = text.replace('..Next,please.', '..Next, please.').replace('1 ,000', '1,000')
            self.assertEqual(expected.encode('utf-8-sig'), (output / 'season' / 'sample.ass').read_bytes())
            self.assertEqual(raw, source.read_bytes())
            report = (output / 'punctuation_fix_report.txt').read_bytes()
            manual = (output / 'punctuation_manual_review.txt').read_bytes()
            self.assertIn(b'SOURCE_REPEATED_OPENING_QUOTE', manual)
            self.assertIn(b'UNCHANGED:', manual)
            self.assertIn('ASS files scanned: 1', run('--check'))
            self.assertEqual(report, (output / 'punctuation_fix_report.txt').read_bytes())
            self.assertEqual(manual, (output / 'punctuation_manual_review.txt').read_bytes())


if __name__ == '__main__':
    unittest.main()
