#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check and normalize English punctuation spacing in ASS subtitles.

Rules applied to English visual lines in Dialogue events:
  - no literal space before commas, periods, question marks, or exclamation
    marks;
  - exactly one literal space after punctuation when more visible text follows
    on the same visual line;
  - exactly TWO spaces before the next speaker's single hyphen, e.g.
    "- Hi.  - Hello."; ordinary word-internal hyphens are not affected;
  - exactly ONE space after each speaker's single hyphen, including the
    first speaker, later speakers, and continuation ellipses;
  - no trailing literal space after punctuation at the end of a visual line;
  - high-confidence split contractions are rejoined using whitespace-only
    edits (``we 're`` -> ``we're``, ``I ' m`` -> ``I'm``,
    ``do n't`` -> ``don't``); ambiguous name/quote cases are left for review;
  - high-confidence accidental punctuation pairs are reduced (``word.?`` ->
    ``word?``, ``word!.`` -> ``word!``, ``word., next`` -> ``word, next``);
    ambiguous comma-dot cases are left unchanged for manual review; legitimate
    ellipses, ``?!``/``!?``, and punctuation after abbreviations are protected;
  - consecutive punctuation ("...", "?!", "!!", and similar) is otherwise one unit;
  - continuation ellipses stay attached to the following word, including
    after a speaker prefix: "- ...hello" and "- Hi.  - ...hello";
  - closing quotes stay attached, even if their opening quote was in an
    earlier subtitle event;
  - separated ellipses ("wait... ...please") retain their existing spacing;
  - inverted opening marks (¿/¡) and inflected initialisms (I.D.'d) are
    protected; suspected ordinary ?/! opening marks are left for review.

ASS override blocks and punctuation inside numbers, URLs, email addresses,
domains, and initialisms are protected. A visual line is treated as English
when it contains Latin letters and no CJK characters. This covers both common
bilingual ``Chinese\\N{\\rEng}English`` events and pure-English Dialogue events.

The input may be one .ass file or a folder. Originals are never overwritten.
Normal runs write fixed ASS copies only for files with automatic changes;
unchanged and manual-review-only ASS files are not copied. If a file produced
by an earlier run now needs no changes, that stale output copy is removed.
With one input file, the terminal report contains every problem line and its
proposed replacement. With multiple input files, the terminal lists only files
that contain problems; pass --details to expand it. The saved report ALWAYS
contains every BEFORE/AFTER pair, regardless of --details. Every normal run
also saves punctuation_manual_review.txt, including suspicious unchanged
source lines. --check prints both reports but writes nothing; redirect its
--details output to a text file when needed.

Examples:
    python fix_english_punctuation_spacing.py "movie.ass"
    python fix_english_punctuation_spacing.py "path/to/folder"
    python fix_english_punctuation_spacing.py "path/to/folder" --check
    python fix_english_punctuation_spacing.py "path/to/folder" --recursive
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple


ASS_TAG_RE = re.compile(r"\{[^}]*\}")
HARD_BREAK_RE = re.compile(r"(\\[Nn])")
LATIN_RE = re.compile(r"[A-Za-z]")
CJK_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    r"\uf900-\ufaff\uac00-\ud7af]"
)
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s{}<>\"]+")
EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,24}\b"
)
DOMAIN_RE = re.compile(
    r"(?i)\b(?:[A-Z0-9-]+\.)+"
    r"(?:com|org|net|edu|gov|io|co|uk|cn|tv|me|app|dev|ai|vc|biz|info)\b"
)
# A unit may immediately follow a number (100,000km, 3.14mm). Also protect
# leading-dot decimals (.28), but do not mistake the end of ...5 for one.
NUMBER_RE = re.compile(
    r"(?<!\w)[-+]?\d+(?:[.,]\d+)+|(?<![\w.])[-+]?\.\d+"
)
ELISION_RE = re.compile(
    r"(?i)(?<!\w)['’](?:cause|cos|coz|cuz|em|til|till|tis|twas|twere|"
    r"twill|twould|bout|round|cept|nuff|sup|kay|ello|ere|im|ave|alf|appy|\d{2}s?)(?!\w)"
)
# Only a space BEFORE a compact three-digit group is repaired automatically.
# '1, 000' or '1 , 2' may be lists; never join arbitrary comma-separated numbers.
DIRTY_THOUSANDS_RE = re.compile(
    r"(?<![\w.,])[-+]?\d{1,3}(?:[ \t]+,\d{3}|,\d{3})+(?:\.\d+)?(?!\d)"
)
QUOTED_COMPOUND_RE = re.compile(
    r'''(?<=["'”’)\]])-(?:type|like|based|style|sized|shaped|related|free)\b'''
)
ELLIPSIS_RE = re.compile(r"\.{2,}|…+")
LYRIC_MARKERS = "*♪♫"
INITIALISM_RE = re.compile(
    r"\b(?:[A-Za-z]\.){2,}(?:[A-Za-z])?|\b[A-Za-z]\.[A-Za-z]\b"
)
# Recognized multi-letter abbreviation components, not arbitrary 'word.Next'.
# Each entry omits its final period so that a sentence-ending period stays live.
DOTTED_ABBREVIATIONS = (
    "Ph.D", "Ph.Ds", "D.Phil", "Ed.D", "Psy.D", "Sc.D", "D.Sc", "D.Litt",
    "B.Tech", "M.Tech", "B.Sc", "M.Sc", "B.Eng", "M.Eng", "B.Ed", "M.Ed",
    "B.Phil", "M.Phil", "B.Arch", "M.Arch", "B.Com", "M.Com", "LL.B", "LL.M",
)
ABBREVIATION_BODY = "(?:" + "|".join(
    re.escape(value) for value in sorted(DOTTED_ABBREVIATIONS, key=len, reverse=True)
) + ")"
MULTILETTER_ABBREVIATION_RE = re.compile(r"(?i)\b" + ABBREVIATION_BODY + r"(?:\.|(?!\w))")
INFLECTED_INITIALISM_RE = re.compile(
    r"(?i)\b(?:(?:[A-Z]\.){2,}(?:[A-Z])?|" + ABBREVIATION_BODY
    + r"\.|(?:Jr|Sr|Dr|Mr|Mrs|Ms|Prof|Rev|St)\.)['’](?:d|s|ed|ing)(?!\w)"
)
DEFAULT_PROTECTED_TERMS = ("Wall.e",)
SUSPECT_DOTTED_TOKEN_RE = re.compile(
    r"\b(?:[A-Z]{2,}\.[A-Z]{2,}|[A-Z][a-z]+\.[a-z])\b"
)
# Do not merge separate already-formed ellipses, such as '... ...word'.
SPACED_ELLIPSIS_RE = re.compile(r"(?<![.\d])\.(?:[ \t]+\.){2,}(?![.\d])")
# Ambiguous source text: '?Qué' may mean '¿Qué', not a closing question mark.
# Preserve that visual segment and ask a human instead of guessing the language.
SUSPECT_OPENING_MARK_RE = re.compile(
    r'''(?:^|[ \t])(?:-[ \t]*)?["'“‘]*[?!](?=[^\W\d_])'''
)
# A period belonging to an abbreviation is not redundant before a question,
# exclamation, or comma: ``A.M.?``, ``Jr.?``, and ``S.H.I.E.L.D.,`` are valid.
# Initialisms are already protected, but their final period intentionally stays
# live so ordinary sentence spacing can still be normalized.
ABBREVIATION_PERIOD_RE = re.compile(
    r"(?i)(?:\b(?:[A-Za-z]\.[ \t]*)+[A-Za-z]|\b" + ABBREVIATION_BODY
    + r"|\b(?:Mr|Mrs|Ms|Dr|Jr|Sr|Prof|Rev|St|Mt|"
    r"vs|etc|Inc|lnc|Ltd|Co|Corp|Dept|Est|approx|Jan|Feb|Mar|Apr|Jun|Jul|Aug|"
    r"Sep|Sept|Oct|Nov|Dec))\.$"
)

# Only unambiguous contraction subjects are repaired automatically. In
# particular, arbitrary ``word 's`` is not joined because the apostrophe can
# be the opening quote of a phrase whose quotation spans subtitle events.
CONTRACTION_SUFFIXES = {
    "i": frozenset(("m", "d", "ll", "ve")),
    "you": frozenset(("d", "ll", "re", "ve")),
    "he": frozenset(("d", "ll", "s")),
    "she": frozenset(("d", "ll", "s")),
    "it": frozenset(("d", "ll", "s")),
    "we": frozenset(("d", "ll", "re", "ve")),
    "they": frozenset(("d", "ll", "re", "ve")),
    "who": frozenset(("d", "ll", "re", "s", "ve")),
    "what": frozenset(("d", "ll", "re", "s")),
    "where": frozenset(("d", "re", "s")),
    "when": frozenset(("s",)),
    "why": frozenset(("s",)),
    "how": frozenset(("d", "s")),
    "that": frozenset(("d", "ll", "s")),
    "there": frozenset(("d", "ll", "re", "s")),
    "here": frozenset(("s",)),
    "let": frozenset(("s",)),
}
TAG_OR_HSPACE = r"(?:[ \t]|\{[^}]*\})*"
TAG_OR_HSPACE_ONE_OR_MORE = r"(?:[ \t]|\{[^}]*\})+"
SUBJECT_CONTRACTION_RE = re.compile(
    r"(?i)\b(?P<word>" + "|".join(CONTRACTION_SUFFIXES) + r")"
    r"(?P<before>" + TAG_OR_HSPACE + r")(?P<apostrophe>['’])"
    r"(?P<after>" + TAG_OR_HSPACE + r")(?P<suffix>re|ve|ll|m|d|s)\b(?!['’])"
)
NEGATIVE_BASE_RE = re.compile(
    r"(?i)\b(?P<stem>are|could|dare|did|do|does|had|has|have|is|may|might|"
    r"must|need|ought|sha|should|was|were|wo|would|ca)"
    r"(?P<gap>" + TAG_OR_HSPACE_ONE_OR_MORE + r")(?P<n>n)"
    r"(?P<before>" + TAG_OR_HSPACE + r")(?P<apostrophe>['’])"
    r"(?P<after>" + TAG_OR_HSPACE + r")(?P<t>t)\b(?!['’])"
)
NEGATIVE_APOSTROPHE_RE = re.compile(
    r"(?i)\b(?P<stem>aren|couldn|daren|didn|doesn|don|hadn|hasn|haven|isn|"
    r"mayn|mightn|mustn|needn|oughtn|shan|shouldn|wasn|weren|won|wouldn|can)"
    r"(?P<before>" + TAG_OR_HSPACE + r")(?P<apostrophe>['’])"
    r"(?P<after>" + TAG_OR_HSPACE + r")(?P<t>t)\b(?!['’])"
)
SPLIT_APOSTROPHE_CANDIDATE_RE = re.compile(
    r"(?i)\b[A-Za-z]+[ \t]+(?:n[ \t]*)?['’][ \t]*(?:re|ve|ll|m|d|s|t)\b(?!['’])"
)

PUNCTUATION = ",.?!…"
INVERTED_OPENING = "¿¡"
ALWAYS_CLOSING = "”’»)]}"
ASCII_QUOTES = "\"'"
SCRIPT_VERSION = "2026-09-05.2"

MANUAL_REASON_LABELS = {
    "SUSPECT_OPENING_MARK": "普通问叹号疑似应为倒标点；该分行保留原文，请核对",
    "SOURCE_DIGIT_FOR_DASH": "原文疑似把说话人横线写成数字 1",
    "SOURCE_WORDS_JOINED": "原文疑似英文单词粘连（也可能是专名）",
    "SOURCE_QUOTE_AMBIGUOUS": "原文引号结构可疑，请结合前后字幕核对",
    "SOURCE_QUOTE_STRUCTURE": "原文双引号结构不明确；该分行保留原文，请核对引用范围",
    "SOURCE_DANGLING_APOSTROPHE": "行末孤立撇号归属不明，可能是跨字幕引用或省音；该分行保留原文",
    "SOURCE_SPLIT_APOSTROPHE_AMBIGUOUS": "疑似拆开的缩写或单引号开头；为保护跨字幕引用，该分行保留原文，请核对",
    "SOURCE_REPEATED_OPENING_QUOTE": "重复开单引号/分段引用不明确；该分行保留原文，请核对引用范围",
    "SOURCE_NUMBER_SPACING": "数字内部空格不明确；该分行保留原文，请核对数字或列表",
    "SOURCE_SEPARATE_DOT": "独立单点与前句标点关系不明确；该分行保留原文",
    "SOURCE_REDUNDANT_PUNCTUATION_AMBIGUOUS": "逗号后单点可能是误打，也可能是小数点；该分行保留原文，请结合画面核对",
    "DOTTED_TOKEN_REVIEW": "带点字符串可能是专名或缩写；该分行保留原文，可用 --protect 明确保留",
    "PROTECTED_TOKEN_CHANGED": "已识别的缩写、名称或数字内部发生空格变化，请勿直接覆盖",
    "APOSTROPHE_PREFIX_SPLIT": "缩写与撇号词尾之间新增空格，请核对",
    "CLOSING_QUOTE_DETACHED": "闭引号与前面的标点被拆开，请核对跨字幕引用",
    "OPENING_QUOTE_MOVED": "新引用开引号前的空格被移到引号内部，请核对",
    "OPENING_QUOTE_GAP_ADDED": "新开引号内部被插入空格，请核对",
    "CONTINUATION_ELLIPSIS_SPLIT": "承接省略号后新增空格，请核对",
    "SEPARATE_ELLIPSES_JOINED": "原本分开的点号组被合并，请核对",
    "LYRIC_BOUNDARY_CHANGED": "歌词包围标记附近的原有间距被改变，请核对",
    "AUTO_CHANGE_BLOCKED": "安全检查拦截了高风险修改；该英文分行保留原文",
    "NUMBER_SPLIT": "数字内部新增空格，请核对",
    "APOSTROPHE_SPLIT": "撇号与后续字母被拆开，请核对缩写或引用",
    "QUOTE_GAP_ADDED": "标点与双引号间新增空格，请核对开闭引号",
    "NON_WHITESPACE_CHANGE": "检测到非空格内容变化，请勿直接覆盖原字幕",
    "ASS_TAG_CHANGE": "检测到 ASS 标签变化，请勿直接覆盖原字幕",
    "NOT_IDEMPOTENT": "再次处理仍会变化，需人工核对",
    "DRAWING_EVENT_CHANGED": "含 ASS 绘图指令的事件发生修改，请核对",
}


@dataclass
class Issue:
    line_number: int
    before: str
    after: str


@dataclass
class ManualIssue:
    line_number: int
    reasons: List[str]
    before: str
    after: str


@dataclass
class FileResult:
    source_path: str
    relative_path: str
    encoding: str
    fixed_text: str
    english_lines: int
    issues: List[Issue]
    manual_issues: List[ManualIssue] = field(default_factory=list)


class _Protector:
    """Temporarily replace text that punctuation normalization must not edit."""

    def __init__(self, original: str) -> None:
        self.original = original
        self.mapping: Dict[int, str] = {}
        self.tag_placeholders: set[str] = set()
        self.opening_placeholders: set[str] = set()
        self.closing_placeholders: set[str] = set()
        self.attached_placeholders: set[str] = set()
        self._next_codepoint = 0xE000

    def token(self, value: str, *, is_tag: bool = False, boundary: str = "") -> str:
        while True:
            char = chr(self._next_codepoint)
            self._next_codepoint += 1
            if char not in self.original and ord(char) not in self.mapping:
                break
        self.mapping[ord(char)] = value
        if is_tag:
            self.tag_placeholders.add(char)
        if boundary:
            getattr(self, boundary + "_placeholders").add(char)
        return char

    def restore(self, value: str) -> str:
        return value.translate(self.mapping)


def read_text(path: str) -> Tuple[str, str]:
    with open(path, "rb") as handle:
        raw = handle.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    raise UnicodeError(f"Cannot decode subtitle file: {path}")


def write_text(path: str, text: str, encoding: str) -> None:
    with open(path, "w", encoding=encoding, newline="") as handle:
        handle.write(text)


@lru_cache(maxsize=128)
def _term_pattern(terms: Tuple[str, ...]) -> re.Pattern[str]:
    values = sorted(set(DEFAULT_PROTECTED_TERMS + terms), key=len, reverse=True)
    return re.compile(r"(?i)(?<!\w)(?:" + "|".join(map(re.escape, values)) + r")(?!\w)")


def _protect_visible_pattern(
    text: str, protector: _Protector, pattern: re.Pattern[str], *, final_period: bool = False,
    compact_spaces: bool = False, boundary: str = "",
) -> str:
    """Protect a visible token even when ASS styling changes inside it."""
    indices = [i for i, char in enumerate(text) if char not in protector.tag_placeholders]
    visible = "".join(text[i] for i in indices)
    for match in reversed(list(pattern.finditer(visible))):
        match_end = match.end()
        if final_period and visible[match_end - 1] == ".":
            match_end -= 1
        start, end = indices[match.start()], indices[match_end - 1] + 1
        value = text[start:end]
        if compact_spaces:
            # Tags are still placeholders: never remove spaces INSIDE tags.
            value = re.sub(r"[ \t]", "", value)
        token = protector.token(protector.restore(value), boundary=boundary)
        text = text[:start] + token + text[end:]
    return text


def _protected_patterns(terms: Sequence[str] = ()) -> Tuple[re.Pattern[str], ...]:
    return (
        _term_pattern(tuple(terms)), INFLECTED_INITIALISM_RE, MULTILETTER_ABBREVIATION_RE,
        INITIALISM_RE, DOMAIN_RE, EMAIL_RE, NUMBER_RE, ELISION_RE, QUOTED_COMPOUND_RE,
    )


def _repeated_elision_pattern(visible: str) -> re.Pattern[str]:
    fragments = re.findall(r"(?i)(?<!\w)['’]([a-z]{1,4})(?=\.{2,}|…)", visible)
    repeated = sorted({word.lower() for word in fragments
                       if sum(other.lower() == word.lower() for other in fragments) >= 2})
    return re.compile(r"(?i)(?<!\w)['’](?:" + "|".join(repeated) + r")(?=\.{2,}|…)" if repeated else r"(?!)")


def _mask_elisions(visible: str) -> str:
    # Same-length mask used for source quote analysis; contractions are handled
    # by _is_standalone_quote. Do not mistake 'ru... 'ru... for a paired quote.
    repeated = _repeated_elision_pattern(visible)
    for pattern in (ELISION_RE, repeated):
        visible = pattern.sub(lambda m: "x" * len(m.group()), visible)
    return visible


def _remove_horizontal_space(value: str) -> str:
    """Remove visible horizontal space while retaining any intervening tags."""
    return re.sub(r"[ \t]", "", value)


def _normalize_split_contractions(text: str) -> str:
    """Join high-confidence English contractions without changing characters.

    ASS override tags may sit at either side of the apostrophe. They remain in
    their original order; only literal spaces and tabs are removed. Arbitrary
    ``word 's`` forms are deliberately excluded because they can be opening
    single quotes whose closing quote occurs in a later subtitle event.
    """
    def join_negative_base(match: re.Match[str]) -> str:
        return (
            match.group("stem")
            + _remove_horizontal_space(match.group("gap"))
            + match.group("n")
            + _remove_horizontal_space(match.group("before"))
            + match.group("apostrophe")
            + _remove_horizontal_space(match.group("after"))
            + match.group("t")
        )

    def join_negative_apostrophe(match: re.Match[str]) -> str:
        return (
            match.group("stem")
            + _remove_horizontal_space(match.group("before"))
            + match.group("apostrophe")
            + _remove_horizontal_space(match.group("after"))
            + match.group("t")
        )

    def join_subject_contraction(match: re.Match[str]) -> str:
        word, suffix = match.group("word"), match.group("suffix")
        if suffix.lower() not in CONTRACTION_SUFFIXES[word.lower()]:
            return match.group(0)
        return (
            word
            + _remove_horizontal_space(match.group("before"))
            + match.group("apostrophe")
            + _remove_horizontal_space(match.group("after"))
            + suffix
        )

    text = NEGATIVE_BASE_RE.sub(join_negative_base, text)
    text = NEGATIVE_APOSTROPHE_RE.sub(join_negative_apostrophe, text)
    return SUBJECT_CONTRACTION_RE.sub(join_subject_contraction, text)


def _lyric_boundaries(visible: str) -> Dict[int, str]:
    """Find single lyric wrappers, not censored words or multiplication signs."""
    boundaries: Dict[int, str] = {}
    pattern = re.compile(r"(?<![*♪♫])([*♪♫])(?![*♪♫])([^*♪♫]+)\1(?![*♪♫])")
    for match in pattern.finditer(visible):
        previous = visible[match.start() - 1] if match.start() else ""
        if previous and previous.isalnum():
            continue
        if any(ch.isalnum() or 0xE000 <= ord(ch) <= 0xF8FF for ch in match[2]):
            boundaries[match.start()] = "opening"
            boundaries[match.end() - 1] = "closing"
    # A lyric can span events, just like a quotation. Restrict unpaired
    # wrappers to the visual-line edges; do not reinterpret stars in words.
    for match in re.finditer(r"(?<![*♪♫])[*♪♫](?![*♪♫])", visible):
        index = match.start()
        if index in boundaries:
            continue
        prefix, tail = visible[:index], visible[index + 1:]
        if not prefix.strip(" \t-\"'“‘") and any(c.isalnum() for c in tail):
            boundaries[index] = "opening"
        elif not tail.strip(" \t\"'”’") and any(c.isalnum() for c in prefix):
            boundaries[index] = "closing"
    return boundaries


def _source_review_risks(segment: str, terms: Sequence[str] = ()) -> List[str]:
    """Conservative source ambiguities: preserve the segment, never guess text."""
    visible = ASS_TAG_RE.sub("", segment)
    stripped = visible.strip(" \t")
    reasons = []
    if SUSPECT_OPENING_MARK_RE.search(visible):
        reasons.append("SUSPECT_OPENING_MARK")
    if (
        SPLIT_APOSTROPHE_CANDIDATE_RE.search(visible)
        and _normalize_split_contractions(visible) == visible
    ):
        reasons.append("SOURCE_SPLIT_APOSTROPHE_AMBIGUOUS")
    quoted = stripped.lstrip("- \t")
    if quoted.startswith('"') and quoted.endswith('"') and quoted.count('"') >= 3 and quoted.count('"') % 2:
        reasons.append("SOURCE_QUOTE_STRUCTURE")
    masked = _mask_elisions(visible).strip(" \t-" + LYRIC_MARKERS)
    if masked.startswith("'"):
        for match in re.finditer(r"[,.?!…][ \t]+'(?=[A-Za-z])", masked):
            tail = masked[match.end():]
            if not any(tail[i] == "'" and _is_standalone_quote(tail, i, "'") for i in range(len(tail))):
                reasons.append("SOURCE_REPEATED_OPENING_QUOTE")
                break
    numeric_spans = [m.span() for m in DIRTY_THOUSANDS_RE.finditer(visible)]
    for match in re.finditer(r"\d[ \t]+[.,][ \t]*\d", visible):
        if not any(a <= match.start() and match.end() <= b for a, b in numeric_spans):
            reasons.append("SOURCE_NUMBER_SPACING")
            break
    for match in re.finditer(r"[.?!…]+(?:[ \t]+[.?!…]+)+", visible):
        groups = re.split(r"[ \t]+", match.group())
        if len(groups) == 2 and groups[-1] == "." and (groups[0] == "." or any(c in "?!" for c in groups[0])):
            reasons.append("SOURCE_SEPARATE_DOT")
            break
    # ``,.50`` is a missing space before a leading-dot decimal, not redundant
    # punctuation. NUMBER_RE protects ``.50`` and the normal comma rule then
    # produces ``, .50``. Once whitespace separates dot from digit, intent is
    # ambiguous and the source remains a manual-review candidate.
    if re.search(r",\.(?![.\d])", visible):
        reasons.append("SOURCE_REDUNDANT_PUNCTUATION_AMBIGUOUS")
    # Don't count contractions (don't) or terminal elisions (fuckin') as openers.
    # An attached terminal quote may legitimately close an earlier event.
    # Only the separated, empty trailing fragment is ambiguous locally.
    if re.search(r"[,.?!…][ \t]+['’][ \t]*$", visible) and not re.search(
        r'''(?:^|[\s"(\[,.?!…])['‘](?=[^\s,.?!…"'])''', visible
    ):
        reasons.append("SOURCE_DANGLING_APOSTROPHE")
    dotted = list(SUSPECT_DOTTED_TOKEN_RE.finditer(visible))
    if dotted:
        protected_spans = [
            match.span() for pattern in _protected_patterns(terms) + (URL_RE,)
            for match in pattern.finditer(visible)
        ]
        if any(not any(a <= match.start() and match.end() <= b for a, b in protected_spans) for match in dotted):
            reasons.append("DOTTED_TOKEN_REVIEW")
    return reasons


def _protect_special_text(segment: str, terms: Sequence[str] = ()) -> Tuple[str, _Protector]:
    protector = _Protector(segment)
    protected = ASS_TAG_RE.sub(
        lambda match: protector.token(match.group(0), is_tag=True), segment
    )

    def protect_url(match: re.Match[str]) -> str:
        value = match.group(0)
        trailing = ""
        while value and value[-1] in PUNCTUATION:
            trailing = value[-1] + trailing
            value = value[:-1]
        return protector.token(protector.restore(value)) + trailing

    protected = URL_RE.sub(protect_url, protected)
    for pattern in (_term_pattern(tuple(terms)), INFLECTED_INITIALISM_RE):
        protected = _protect_visible_pattern(protected, protector, pattern)
    protected = _protect_visible_pattern(
        protected, protector, MULTILETTER_ABBREVIATION_RE, final_period=True
    )
    protected = _protect_visible_pattern(protected, protector, DIRTY_THOUSANDS_RE, compact_spaces=True)
    protected = _protect_visible_pattern(protected, protector, QUOTED_COMPOUND_RE, boundary="attached")
    repeated = _repeated_elision_pattern(ASS_TAG_RE.sub("", segment))
    for pattern in (EMAIL_RE, DOMAIN_RE, NUMBER_RE, ELISION_RE, repeated):
        protected = _protect_visible_pattern(protected, protector, pattern)

    protected = _protect_visible_pattern(protected, protector, INITIALISM_RE, final_period=True)
    indices = [i for i, char in enumerate(protected) if char not in protector.tag_placeholders]
    visible = "".join(protected[i] for i in indices)
    for index, boundary in sorted(_lyric_boundaries(visible).items(), reverse=True):
        raw_index = indices[index]
        protected = (protected[:raw_index] + protector.token(visible[index], boundary=boundary)
                     + protected[raw_index + 1:])
    return protected, protector


def _is_standalone_quote(text: str, index: int, quote: str) -> bool:
    if quote == '"':
        return True
    previous = text[index - 1] if index else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    return not (previous.isalnum() and following.isalnum())


def _is_speaker_dash(text: str, index: int) -> bool:
    """Recognize a single speech-prefix hyphen, not -- or a negative number.

    Called at the first visible character after punctuation/closing quotes.
    Both '- Hello' and the existing subtitle convention '-Hello' are allowed.
    """
    if index >= len(text) or text[index] != "-":
        return False
    following = text[index + 1:].lstrip(" \t")
    return bool(following) and following[0] != "-" and not following[0].isdigit()


def _normalize_speaker_prefixes(text: str, protector: _Protector) -> str:
    """Normalize speech prefixes, not compound-word hyphens or minus signs.

    Candidates occur at the visual line start, after punctuation/closing
    quotes, or at a separated later speaker in an already marked dialogue.
    Tags are invisible; their order and contents must remain unchanged.
    """
    visible = "".join(char for char in text if char not in protector.tag_placeholders)
    visible_indices = {}
    for index, char in enumerate(text):
        if char not in protector.tag_placeholders:
            visible_indices[index] = len(visible_indices)

    output: List[str] = []
    index = 0
    speaker_seen = False
    while index < len(text):
        char = text[index]
        if char == "-":
            offset = visible_indices[index]
            prefix = visible[:offset]
            previous = prefix.rstrip(" \t")
            starts_line = not prefix.strip(" \t\"'“‘" + "".join(protector.opening_placeholders))
            follows_punctuation = bool(previous) and previous[-1] in (
                PUNCTUATION + ALWAYS_CLOSING + ASCII_QUOTES + "".join(protector.closing_placeholders)
            )
            later_speaker = speaker_seen and prefix.endswith((" ", "\t"))
            if (
                (starts_line or follows_punctuation or later_speaker)
                and not prefix.endswith("-")
                and _is_speaker_dash(visible, offset)
            ):
                end = index + 1
                tags: List[str] = []
                while end < len(text) and (
                    text[end] in " \t" or text[end] in protector.tag_placeholders
                ):
                    if text[end] in protector.tag_placeholders:
                        tags.append(text[end])
                    end += 1
                output.append("- ")
                output.extend(tags)
                index = end
                speaker_seen = True
                continue
        output.append(char)
        index += 1
    return "".join(output)


def _is_closing_ascii_quote(
    text: str, index: int, quote: str, tag_placeholders: set[str]
) -> bool:
    # An attached ." / ..." / ?" / !" can close a quote begun in a
    # previous event, even when another sentence follows in this event.
    # Require preceding word content and attachment: a bare '."Word' is
    # ambiguous, and 'Hi. "Hello"' can begin a NEW quotation.
    prefix = "".join(char for char in text[:index] if char not in tag_placeholders)
    tail = "".join(char for char in text[index + 1:] if char not in tag_placeholders)
    # A previous quote has already closed: flesh". "Merchant of Venice."
    # The new quote is an opener, irrespective of LOCAL quote-count parity.
    if re.search(re.escape(quote) + r"[,.?!…]+[ \t]*$", prefix) and re.match(r"[^\W\d_]|\.{2,}|…", tail):
        return False
    # Prefer an explicit LOCAL opening/closing pair over the cross-event
    # fallback. In their..."real lives" the first quote starts a new phrase.
    # An attached closing quote followed by a space (fine." And...) retains
    # its old interpretation even if there are other quotes later in the line.
    previous_quotes = sum(prefix[i] == quote and _is_standalone_quote(prefix, i, quote)
                          for i in range(len(prefix)))
    following_quotes = [i for i, ch in enumerate(tail)
                        if ch == quote and _is_standalone_quote(tail, i, quote)]
    if previous_quotes % 2 == 0 and following_quotes and re.match(r"[^\W_]|\.{2,}|…|[¿¡]", tail):
        closing_index = following_quotes[0]
        if closing_index and not tail[closing_index - 1].isspace():
            return False
    # A single closing quote can also come from an earlier event. Known
    # elisions have already been protected, so Harvard,' he says stays intact,
    # while He said,'Hello.' is still an opening quotation.
    if quote == "'" and prefix.endswith(tuple(PUNCTUATION)) and (
        tail.startswith((" ", "\t"))
        or re.match(r"(?i)(?:he|she|they|we|I|you|it)\s+(?:says?|said|asks?|asked|replied)\b", tail)
    ):
        return True
    if (
        prefix.endswith(tuple(".?!…" + ("," if quote == '"' and tail.startswith((" ", "\t")) else "")))
        and any(char.isalnum() or 0xE000 <= ord(char) <= 0xF8FF for char in prefix)
    ):
        return True
    # Subtitle quotations commonly span multiple Dialogue events. A quote
    # at the visible line end must not require an opener in this same event.
    tail = "".join(char for char in text[index + 1:] if char not in tag_placeholders)
    if not tail.strip(" \t" + ALWAYS_CLOSING + ASCII_QUOTES + PUNCTUATION):
        return True
    # A closing quote may itself be followed by sentence punctuation.
    # Do not treat an opening quote in 'He said,"...hello"' as closing.
    if tail.startswith((",", "?", "!")):
        return True
    tail = tail.lstrip(ALWAYS_CLOSING + ASCII_QUOTES)
    if _is_speaker_dash(tail.lstrip(" \t"), 0):
        return True
    count = 0
    for candidate in range(index):
        if text[candidate] == quote and _is_standalone_quote(text, candidate, quote):
            count += 1
    return count % 2 == 1


def _has_visible_content(
    text: str, start: int, tag_placeholders: set[str]
) -> bool:
    for char in text[start:]:
        if char in " \t" or char in tag_placeholders:
            continue
        return True
    return False


def _ellipsis_context(text: str, end: int, protector: _Protector) -> Tuple[bool, bool]:
    """Return (continuation, follows speaker prefix).

    A later speaker begins a new context even within the same visual line.
    Restore protected numbers/initialisms before testing for word content.
    """
    prefix = ASS_TAG_RE.sub("", protector.restore(text[:end]))
    after_speaker = bool(re.search(r'''(?:^|[\s,.?!…"'”’*)\]])-[ \t"'“‘*♪♫]*$''', prefix))
    return after_speaker or not any(char.isalnum() for char in prefix), after_speaker


def _visible_ends_with_punctuation(value: str) -> bool:
    visible = ASS_TAG_RE.sub("", value).rstrip(" \t")
    visible = visible.rstrip(ALWAYS_CLOSING + ASCII_QUOTES)
    return bool(visible) and visible[-1] in PUNCTUATION


def _ends_with_abbreviation_period(prefix: str, protector: _Protector) -> bool:
    visible = ASS_TAG_RE.sub("", protector.restore(prefix))
    return bool(ABBREVIATION_PERIOD_RE.search(visible))


def _normalize_redundant_punctuation_protected(text: str, protector: _Protector) -> str:
    """Remove only high-confidence accidental punctuation characters.

    Run after URLs, numbers, initialisms, and user terms have been replaced by
    placeholders. This deliberately leaves expressive ``?!``/``!?`` and real
    three-dot ellipses alone.
    """

    def drop_period_after_quoted_terminal(match: re.Match[str]) -> str:
        quote = match.group("quote")
        quote_index = match.start("quote")
        closing = quote in "”’" or _is_closing_ascii_quote(
            match.string, quote_index, quote, protector.tag_placeholders
        )
        return match.group("mark") + quote if closing else match.group(0)

    # ``"Hiya!".`` -> ``"Hiya!"``. An ASCII quote is changed only when the
    # existing quote classifier identifies it as closing.
    text = re.sub(
        r'(?P<mark>[?!])(?P<quote>["\'”’])\.(?!\.)',
        drop_period_after_quoted_terminal,
        text,
    )

    def reduce_dots_before_terminal(match: re.Match[str]) -> str:
        dots, mark = match.group("dots"), match.group("mark")
        # Keep the abbreviation's own period. With a doubled dot, discard only
        # the accidental extra one: ``A.I..?`` -> ``A.I.?``.
        if _ends_with_abbreviation_period(match.string[:match.start()] + ".", protector):
            return "." + mark
        return mark

    # One/two dots followed by ?/! are typos; exactly three dots remain an
    # ellipsis (``Wait...?``). Negative lookbehind prevents matching its tail.
    text = re.sub(
        r'(?<!\.)(?P<dots>\.{1,2})(?P<mark>[?!])',
        reduce_dots_before_terminal,
        text,
    )
    text = re.sub(r'(?P<mark>[?!])\.(?!\.)', r'\g<mark>', text)
    def reduce_dot_comma(match: re.Match[str]) -> str:
        if _ends_with_abbreviation_period(match.string[:match.start()] + ".", protector):
            return match.group(0)
        tail = ASS_TAG_RE.sub("", protector.restore(match.string[match.end():]))
        following = tail.lstrip(" \t" + ALWAYS_CLOSING + ASCII_QUOTES)
        # At visual-line end, or before a clearly new capitalized sentence,
        # retain the period. Before a continuing lowercase word, retain comma.
        if not following or following[:1].isupper() or following.startswith("-"):
            return "."
        return ","

    # Do not consume the final two characters of an ellipsis-plus-comma.
    # This also fixes quote-boundary typos such as ``".,`` -> ``",``.
    return re.sub(r'(?<!\.)\.,(?!\.)', reduce_dot_comma, text)


def _normalize_redundant_punctuation_only(
    segment: str, protected_terms: Sequence[str] = ()
) -> str:
    """Return the approved non-whitespace baseline used by safety checks."""
    protected, protector = _protect_special_text(segment, protected_terms)
    protected = _normalize_redundant_punctuation_protected(protected, protector)
    return protector.restore(protected)


def _normalize_english_segment_unchecked(segment: str, protected_terms: Sequence[str] = ()) -> str:
    segment = _normalize_split_contractions(segment)
    protected, protector = _protect_special_text(segment, protected_terms)
    protected = _normalize_redundant_punctuation_protected(protected, protector)
    # Form a leading spaced-dot ellipsis before determining continuation
    # context, so '. . . word' reaches its final form in one pass.
    protected = SPACED_ELLIPSIS_RE.sub(
        lambda match: re.sub(r"[ \t]", "", match.group(0)), protected
    )
    protected = _normalize_speaker_prefixes(protected, protector)
    output: List[str] = []
    index = 0

    while index < len(protected):
        char = protected[index]
        if char in INVERTED_OPENING:
            # Opening marks stay opening marks; never translate ?/! to ¿/¡.
            # Keep them attached to their text even across invisible tags.
            output.append(char)
            index += 1
            while index < len(protected) and (
                protected[index] in " \t"
                or protected[index] in protector.tag_placeholders
            ):
                if protected[index] in protector.tag_placeholders:
                    output.append(protected[index])
                index += 1
            continue
        if char not in PUNCTUATION:
            output.append(char)
            index += 1
            continue

        end = index + 1
        while end < len(protected) and protected[end] in PUNCTUATION:
            end += 1
        punctuation_group = protected[index:end]
        is_ellipsis = (
            (len(punctuation_group) >= 2 and set(punctuation_group) == {"."})
            or set(punctuation_group) == {"…"}
        )
        visible_prefix = "".join(
            char for char in protected[:index] if char not in protector.tag_placeholders
        )
        separated_ellipsis = is_ellipsis and bool(
            re.search(r"[,.?!…][ \t]+$", visible_prefix)
        )
        continuation, after_speaker = (
            _ellipsis_context(protected, index, protector) if is_ellipsis else (False, False)
        )
        leading_continuation_ellipsis = is_ellipsis and continuation
        # Preserve the speaker-prefix spacing in '- ...word'. It is not
        # whitespace between a word and its punctuation.
        after_lyric_open = bool(visible_prefix.rstrip(" \t")) and visible_prefix.rstrip(" \t")[-1] in protector.opening_placeholders
        if not (separated_ellipsis or (leading_continuation_ellipsis and (after_speaker or after_lyric_open))):
            while output and output[-1] in " \t":
                output.pop()
        output.append(punctuation_group)

        while end < len(protected):
            look = end
            tags: List[str] = []
            while look < len(protected) and (
                protected[look] in " \t" or protected[look] in protector.tag_placeholders
            ):
                if protected[look] in protector.tag_placeholders:
                    tags.append(protected[look])
                look += 1
            if look == len(protected):
                break
            following = protected[look]
            if following in protector.closing_placeholders:
                # Preserve the source's lyric-wrapper spacing, including a
                # deliberately spaced musical note. Tags retain their order.
                output.append(protected[end:look])
                output.append(following)
                end = look + 1
                continue
            if following in ALWAYS_CLOSING or (
                following in ASCII_QUOTES and _is_closing_ascii_quote(
                    protected, look, following, protector.tag_placeholders
                )
            ):
                output.extend(tags)
                output.append(following)
                end = look + 1
                continue
            break

        # ASS tags have no visible width. Count spacing across them and keep
        # their bytes/order intact, with normalized whitespace after the tags.
        original_gap: List[str] = []
        while end < len(protected) and (
            protected[end] in " \t" or protected[end] in protector.tag_placeholders
        ):
            if protected[end] in protector.tag_placeholders:
                output.append(protected[end])
            else:
                original_gap.append(protected[end])
            end += 1
        if _has_visible_content(protected, end, protector.tag_placeholders):
            visible_tail = "".join(
                char for char in protected[end:] if char not in protector.tag_placeholders
            )
            if _is_speaker_dash(visible_tail, 0):
                output.append("  ")
            elif visible_tail[0] in protector.attached_placeholders:
                pass
            elif separated_ellipsis or (
                original_gap and ELLIPSIS_RE.match(visible_tail)
            ):
                # Never join two separate pauses, or move a continuation
                # ellipsis from the next phrase onto the previous phrase.
                output.extend(original_gap)
            elif not leading_continuation_ellipsis:
                output.append(" ")
        index = end

    fixed = protector.restore("".join(output))
    if _visible_ends_with_punctuation(fixed):
        fixed = fixed.rstrip(" \t")
    return fixed


@lru_cache(maxsize=2048)
def _normalize_segment_result(segment: str, protected_terms: Tuple[str, ...]) -> Tuple[str, Tuple[str, ...]]:
    if _source_review_risks(segment, protected_terms):
        return segment, ()
    proposed = _normalize_english_segment_unchecked(segment, protected_terms)
    if proposed != segment:
        approved_source = _normalize_redundant_punctuation_only(segment, protected_terms)
        risks = _change_review_risks(approved_source, proposed, protected_terms)
        if risks:
            return segment, tuple(sorted(risks | {"AUTO_CHANGE_BLOCKED"}))
    return proposed, ()


def normalize_english_segment(segment: str, protected_terms: Sequence[str] = ()) -> str:
    return _normalize_segment_result(segment, tuple(protected_terms))[0]


def _is_english_visual_line(segment: str) -> bool:
    visible = ASS_TAG_RE.sub("", segment)
    return bool(LATIN_RE.search(visible)) and not bool(CJK_RE.search(visible))


def normalize_text_field(text: str, protected_terms: Sequence[str] = ()) -> Tuple[str, bool]:
    parts = HARD_BREAK_RE.split(text)
    processed = False
    for index in range(0, len(parts), 2):
        if _is_english_visual_line(parts[index]):
            processed = True
            parts[index] = normalize_english_segment(parts[index], protected_terms)
    return "".join(parts), processed


def fix_dialogue_line(line: str, protected_terms: Sequence[str] = ()) -> Tuple[str, bool, bool]:
    """Return (fixed line, changed, contains an English visual line)."""
    if not line.startswith("Dialogue:"):
        return line, False, False
    fields = line.split(",", 9)
    if len(fields) != 10:
        return line, False, False
    fixed_text, is_english = normalize_text_field(fields[9], protected_terms)
    if not is_english or fixed_text == fields[9]:
        return line, False, is_english
    fields[9] = fixed_text
    return ",".join(fields), True, True


def _approved_line_baseline(line: str, protected_terms: Sequence[str] = ()) -> str:
    """Apply only approved punctuation deletion to English visual segments."""
    if not line.startswith("Dialogue:"):
        return line
    fields = line.split(",", 9)
    if len(fields) != 10:
        return line
    parts = HARD_BREAK_RE.split(fields[9])
    for index in range(0, len(parts), 2):
        if _is_english_visual_line(parts[index]):
            parts[index] = _normalize_redundant_punctuation_only(
                parts[index], protected_terms
            )
    fields[9] = "".join(parts)
    return ",".join(fields)


def _whitespace_gaps(text: str) -> Dict[int, str]:
    """Index horizontal whitespace by its position among non-space characters."""
    gaps: Dict[int, str] = {}
    offset = 0
    for match in re.finditer(r"[ \t]+", text):
        gaps[match.start() - offset] = match.group(0)
        offset += len(match.group(0))
    return gaps


def _change_review_risks(before: str, after: str, terms: Sequence[str] = ()) -> set[str]:
    """Check both sides of quotes and protected tokens, separately from fixing."""
    invariants: set[str] = set()
    if ASS_TAG_RE.findall(before) != ASS_TAG_RE.findall(after):
        invariants.add("ASS_TAG_CHANGE")
    if re.sub(r"[ \t]", "", before) != re.sub(r"[ \t]", "", after):
        invariants.add("NON_WHITESPACE_CHANGE")
    if invariants:
        return invariants
    b, a = ASS_TAG_RE.sub("", before), ASS_TAG_RE.sub("", after)
    compact = re.sub(r"[ \t]", "", b)
    if compact != re.sub(r"[ \t]", "", a):
        return {"NON_WHITESPACE_CHANGE"}
    old_gaps, new_gaps = _whitespace_gaps(b), _whitespace_gaps(a)
    indices = [i for i, char in enumerate(b) if char not in " \t"]
    protected_spans = [
        (len(re.sub(r"[ \t]", "", b[:match.start()])), len(re.sub(r"[ \t]", "", b[:match.end()])))
        for pattern in _protected_patterns(terms) + (SUSPECT_DOTTED_TOKEN_RE, _repeated_elision_pattern(b))
        for match in pattern.finditer(b)
    ]
    quote_text = _mask_elisions(b)
    lyric_boundaries = _lyric_boundaries(b)
    reasons: set[str] = set()
    for pos in old_gaps.keys() | new_gaps.keys():
        old, new = old_gaps.get(pos, ""), new_gaps.get(pos, "")
        if old == new:
            continue
        left, right = compact[:pos], compact[pos:]
        if any(start < pos < end for start, end in protected_spans):
            reasons.add("PROTECTED_TOKEN_CHANGED")
        if new and not old:
            if re.search(r"\d[.,]$", left) and re.match(r"\d", right):
                reasons.add("NUMBER_SPLIT")
            if left.endswith(".") and re.match(r"['’](?:s|d|ed|ing)\b", right, re.I):
                reasons.add("APOSTROPHE_PREFIX_SPLIT")
            if left.endswith(tuple(PUNCTUATION)) and right.startswith(tuple(ASCII_QUOTES + "”’")):
                closing = right[0] in "”’" or _is_closing_ascii_quote(quote_text, indices[pos], right[0], set())
                if closing:
                    reasons.add("CLOSING_QUOTE_DETACHED")
                    if right[0] in '"”':
                        reasons.add("QUOTE_GAP_ADDED")
            if left.endswith(tuple(ASCII_QUOTES)) and right[:1].isalpha():
                quote_index = indices[pos - 1]
                quote = left[-1]
                is_standalone = _is_standalone_quote(quote_text, quote_index, quote)
                is_closing = is_standalone and _is_closing_ascii_quote(quote_text, quote_index, quote, set())
                if not is_closing or any(start < pos < end for start, end in protected_spans):
                    reasons.add("OPENING_QUOTE_GAP_ADDED" if quote == '"' else "APOSTROPHE_SPLIT")
            if left.endswith("’") and right[:1].isalpha():
                quote_index = indices[pos - 1]
                if not _is_standalone_quote(quote_text, quote_index, "’"):
                    reasons.add("APOSTROPHE_SPLIT")
        if (
            old and not new and right.startswith(tuple(ASCII_QUOTES))
            and not old_gaps.get(pos + 1) and new_gaps.get(pos + 1)
            and not _is_closing_ascii_quote(quote_text, indices[pos], right[0], set())
        ):
            reasons.add("OPENING_QUOTE_MOVED")
        if pos < len(indices) and lyric_boundaries.get(indices[pos]) == "closing":
            reasons.add("LYRIC_BOUNDARY_CHANGED")
        if pos and lyric_boundaries.get(indices[pos - 1]) == "opening":
            reasons.add("LYRIC_BOUNDARY_CHANGED")
    # These checks deliberately inspect the ORIGINAL gap positions rather than
    # accepting an output just because a second normalization is stable.
    for match in ELLIPSIS_RE.finditer(b):
        prefix = b[:match.start()]
        continuation = not any(c.isalnum() for c in prefix) or re.search(
            r'''(?:^|[\s,.?!…"'”’*)\]])-[ \t"'“‘*♪♫]*$''', prefix)
        pos = len(re.sub(r"[ \t]", "", b[:match.end()]))
        if continuation and not old_gaps.get(pos) and new_gaps.get(pos):
            # A quote can legitimately CLOSE a cross-event continuation:
            # ..." Right. Only the gap immediately after the dots is guarded.
            reasons.add("CONTINUATION_ELLIPSIS_SPLIT")
    for match in re.finditer(r"[,.?!…]([ \t]+)(?=\.{2,}|…)", b):
        pos = len(re.sub(r"[ \t]", "", b[:match.start(1)]))
        if old_gaps.get(pos) and not new_gaps.get(pos):
            reasons.add("SEPARATE_ELLIPSES_JOINED")
    return reasons


def manual_review_reasons(before: str, after: str, protected_terms: Sequence[str] = ()) -> List[str]:
    """Heuristic candidates, including suspicious source lines left unchanged.

    This is not a spelling/translation checker or a proof of subtitle quality.
    Quotes may span events, so quote-count parity alone is not an error.
    """
    if not before.startswith("Dialogue:") or len(before.split(",", 9)) != 10:
        return []
    reasons: set[str] = set()
    parts = HARD_BREAK_RE.split(before.split(",", 9)[9])
    for segment in parts[::2]:
        if not _is_english_visual_line(segment):
            continue
        visible = ASS_TAG_RE.sub("", segment)
        reasons.update(_source_review_risks(segment, protected_terms))
        reasons.update(_normalize_segment_result(segment, tuple(protected_terms))[1])
        if re.search(r"(?<!\w)1(?:No|Now|Yes|Yeah|Okay)\b", visible):
            reasons.add("SOURCE_DIGIT_FOR_DASH")
        if re.search(r"\b(?:film|the|a|an|to|of|in|and|for|with)[A-Z][a-z]+", visible):
            reasons.add("SOURCE_WORDS_JOINED")
        if (
            re.match(r'''^[ \t]*\.[ \t]*"[^\W\d_]''', visible)
            or re.search(r'''[?!][ \t]+['’](?:Yes|No|Yeah)\b''', visible)
        ):
            reasons.add("SOURCE_QUOTE_AMBIGUOUS")

    if before != after:
        approved_before = _approved_line_baseline(before, protected_terms)
        if re.sub(r"[ \t]", "", approved_before) != re.sub(r"[ \t]", "", after):
            reasons.add("NON_WHITESPACE_CHANGE")
        if ASS_TAG_RE.findall(before) != ASS_TAG_RE.findall(after):
            reasons.add("ASS_TAG_CHANGE")
        if re.search(r"\\p[1-9]\d*\b", before):
            reasons.add("DRAWING_EVENT_CHANGED")
        after_parts = HARD_BREAK_RE.split(after.split(",", 9)[9])
        for source_part, fixed_part in zip(parts[::2], after_parts[::2]):
            if source_part != fixed_part and _is_english_visual_line(source_part):
                approved_source = _normalize_redundant_punctuation_only(
                    source_part, protected_terms
                )
                reasons.update(_change_review_risks(approved_source, fixed_part, protected_terms))
        b, a = (
            ASS_TAG_RE.sub("", value.split(",", 9)[9])
            for value in (approved_before, after)
        )
        compact = re.sub(r"[ \t]", "", b)
        if compact == re.sub(r"[ \t]", "", a):
            old_gaps, new_gaps = _whitespace_gaps(b), _whitespace_gaps(a)
            for position, gap in new_gaps.items():
                if not gap or old_gaps.get(position):
                    continue
                left, right = compact[:position], compact[position:]
                if re.search(r"\d[.,]$", left) and re.match(r"\d", right):
                    reasons.add("NUMBER_SPLIT")
    if fix_dialogue_line(after, protected_terms)[0] != after:
        reasons.add("NOT_IDEMPOTENT")
    return sorted(reasons)


def analyze_file(src_path: str, relative_path: str, protected_terms: Sequence[str] = ()) -> FileResult:
    text, encoding = read_text(src_path)
    lines = text.splitlines(keepends=True)
    issues: List[Issue] = []
    manual_issues: List[ManualIssue] = []
    english_lines = 0

    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        ending = line[len(stripped):]
        fixed, changed, is_english = fix_dialogue_line(stripped, protected_terms)
        reasons = manual_review_reasons(stripped, fixed, protected_terms)
        if reasons:
            manual_issues.append(ManualIssue(index + 1, reasons, stripped, fixed))
        if is_english:
            english_lines += 1
        if changed:
            issues.append(Issue(index + 1, stripped, fixed))
            lines[index] = fixed + ending

    return FileResult(
        source_path=src_path,
        relative_path=relative_path,
        encoding=encoding,
        fixed_text="".join(lines),
        english_lines=english_lines,
        issues=issues,
        manual_issues=manual_issues,
    )


def _is_same_or_child(path: str, parent: str) -> bool:
    path = os.path.normcase(os.path.abspath(path))
    parent = os.path.normcase(os.path.abspath(parent))
    try:
        return os.path.commonpath((path, parent)) == parent
    except ValueError:
        return False


def _remove_empty_output_parents(path: str, out_dir: str) -> None:
    """Remove empty generated subfolders, stopping strictly at out_dir."""
    current = os.path.dirname(path)
    boundary = os.path.abspath(out_dir)
    while os.path.abspath(current) != boundary and _is_same_or_child(current, boundary):
        try:
            os.rmdir(current)
        except OSError:
            break
        current = os.path.dirname(current)


def find_ass_files(
    input_path: str, recursive: bool, out_dir: str
) -> Tuple[str, List[Tuple[str, str]]]:
    absolute_input = os.path.abspath(input_path)
    if os.path.isfile(absolute_input):
        if not absolute_input.lower().endswith(".ass"):
            raise ValueError(f"Input file is not an .ass file: {absolute_input}")
        root = os.path.dirname(absolute_input)
        return root, [(absolute_input, os.path.basename(absolute_input))]
    if not os.path.isdir(absolute_input):
        raise ValueError(f"Input path does not exist: {absolute_input}")

    root = absolute_input
    found: List[Tuple[str, str]] = []
    if recursive:
        for current, directories, filenames in os.walk(root):
            directories[:] = [
                name
                for name in directories
                if not _is_same_or_child(os.path.join(current, name), out_dir)
            ]
            for name in filenames:
                if name.lower().endswith(".ass"):
                    path = os.path.join(current, name)
                    found.append((path, os.path.relpath(path, root)))
    else:
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isfile(path) and name.lower().endswith(".ass"):
                found.append((path, name))
    return root, sorted(found, key=lambda item: item[1].lower())


def format_report(results: Sequence[FileResult], details: bool) -> str:
    bad_results = [result for result in results if result.issues]
    lines = ["English punctuation-spacing report", f"Script version: {SCRIPT_VERSION}", ""]
    lines.append(f"ASS files scanned: {len(results)}")
    lines.append(f"Files with problems: {len(bad_results)}")
    lines.append(f"Problem lines: {sum(len(result.issues) for result in results)}")
    lines.append("")

    if not bad_results:
        lines.append("No automatic spacing changes needed. See manual-review candidates below/separately.")
        return "\n".join(lines) + "\n"

    if len(results) > 1:
        lines.append("Files with problems:")
        for result in bad_results:
            lines.append(f"  {result.relative_path}: {len(result.issues)} problem line(s)")
        if not details:
            return "\n".join(lines) + "\n"
        lines.append("")

    for result in bad_results:
        lines.append(f"File: {result.relative_path}")
        lines.append(
            f"English Dialogue lines scanned: {result.english_lines}; "
            f"problem lines: {len(result.issues)}"
        )
        for issue in result.issues:
            lines.append(f"  Line {issue.line_number}")
            lines.append(f"    BEFORE: {issue.before}")
            lines.append(f"    AFTER : {issue.after}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_manual_report(results: Sequence[FileResult], details: bool) -> str:
    candidates = [result for result in results if result.manual_issues]
    lines = [
        "Manual-review candidates / 人工复核候选名单",
        f"Script version: {SCRIPT_VERSION}",
        f"ASS files scanned: {len(results)}",
        f"Candidate files: {len(candidates)}",
        f"Candidate lines: {sum(len(result.manual_issues) for result in candidates)}",
        "以下是启发式疑点，不代表未列出的字幕一定没有问题。",
        "行号对应原 ASS 文件，内容对应本次运行，不是历史报告。",
        "",
    ]
    if not candidates:
        lines.append("本次未发现人工复核候选；不代表已完成人工校对。")
    for result in candidates:
        lines.append(f"File: {os.path.abspath(result.source_path)}")
        for issue in result.manual_issues:
            descriptions = "；".join(MANUAL_REASON_LABELS[code] for code in issue.reasons)
            lines.append(f"  Line {issue.line_number}: {descriptions}")
            if details:
                lines.append(f"    Codes: {', '.join(issue.reasons)}")
                if issue.before == issue.after:
                    lines.append(f"    UNCHANGED: {issue.before}")
                else:
                    lines.append(f"    BEFORE: {issue.before}")
                    lines.append(f"    AFTER : {issue.after}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    # Legacy Windows pipes can use GBK, which cannot encode ¿ and many other
    # subtitle characters. Keep the caller's encoding but escape unsupported
    # console characters instead of aborting before reports are saved. Disk
    # reports below always use UTF-8 and retain the actual characters.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input", help="One .ass file or a folder containing .ass files")
    parser.add_argument(
        "--out-dir",
        default="punctuation_fixed",
        help="Output folder, relative to the input folder unless absolute",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check and print the report without writing fixed copies",
    )
    parser.add_argument(
        "--recursive", action="store_true", help="Scan subfolders recursively"
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Expand terminal output; the saved report always includes every problem line",
    )
    parser.add_argument(
        "--protect", action="append", default=[], metavar="TOKEN",
        help="Protect a literal name/abbreviation (case-insensitive); repeat for multiple tokens",
    )
    args = parser.parse_args()
    if any(not value or re.search(r"[\s{}\\]", value) for value in args.protect):
        parser.error("--protect requires a nonempty literal token without whitespace or ASS tags/breaks")

    input_path = os.path.abspath(args.input)
    input_root = (
        os.path.dirname(input_path) if os.path.isfile(input_path) else input_path
    )
    out_dir = (
        os.path.abspath(args.out_dir)
        if os.path.isabs(args.out_dir)
        else os.path.abspath(os.path.join(input_root, args.out_dir))
    )

    try:
        root, ass_files = find_ass_files(input_path, args.recursive, out_dir)
    except ValueError as error:
        parser.error(str(error))
    if not ass_files:
        parser.error(f"No .ass files found in {input_path}")
    if not args.check and os.path.abspath(out_dir) == os.path.abspath(root):
        parser.error("--out-dir must not be the source folder")

    results = [analyze_file(path, relative, args.protect) for path, relative in ass_files]
    show_details = args.details or len(results) == 1
    report = format_report(results, show_details)
    print(report, end="")
    print(format_manual_report(results, show_details), end="")

    if args.check:
        print("Check only: no files were written.")
        return

    os.makedirs(out_dir, exist_ok=True)
    written_copies = 0
    removed_stale_copies = 0
    for result in results:
        destination = os.path.join(out_dir, result.relative_path)
        if result.issues:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            write_text(destination, result.fixed_text, result.encoding)
            written_copies += 1
        elif os.path.isfile(destination):
            os.remove(destination)
            _remove_empty_output_parents(destination, out_dir)
            removed_stale_copies += 1

    report_path = os.path.join(out_dir, "punctuation_fix_report.txt")
    write_text(report_path, format_report(results, details=True), "utf-8")
    manual_path = os.path.join(out_dir, "punctuation_manual_review.txt")
    write_text(manual_path, format_manual_report(results, details=True), "utf-8")
    print(f"Originals unchanged. Changed ASS copies and reports: {out_dir}")
    print(f"Changed ASS copies written: {written_copies}")
    print(f"Stale unchanged ASS copies removed: {removed_stale_copies}")
    print(f"Full BEFORE/AFTER report: {report_path}")
    print(f"Manual-review report: {manual_path}")


if __name__ == "__main__":
    main()
