import pytest
from unittest.mock import patch
import sanitizer


# ── happy path — parametrized across all active pipeline steps ───────────────

@pytest.mark.parametrize("raw, expected", [
    # step 2: markdown fence stripped
    ("```eos\nChan 1 @ Full Enter\n```", "Chan 1 @ Full Enter"),
    # step 3: surrounding quotes stripped
    ('"Chan 1 @ Full Enter"',            "Chan 1 @ Full Enter"),
    # step 4: first non-empty line taken; second dropped
    ("Chan 1 @ Full Enter\nChan 2 @ 50", "Chan 1 @ Full Enter"),
    # step 8: "At" normalized → "@"
    ("Chan 1 At Full Enter",             "Chan 1 @ Full Enter"),
    # step 8: case-insensitive
    ("Chan 1 at Full Enter",             "Chan 1 @ Full Enter"),
    # step 9: missing Enter appended
    ("Chan 1 @ Full",                    "Chan 1 @ Full Enter"),
    # step 9: already ends with "#" — no Enter added
    ("Go #",                             "Go #"),
    # step 9: already ends with "Enter" — no duplicate
    ("Chan 1 @ Full Enter",              "Chan 1 @ Full Enter"),
    # steps 2+4+8+9: full chain through fence, multi-word, At, missing Enter
    ("```\nChan 5 At 75\n```",           "Chan 5 @ 75 Enter"),
])
def test_clean_happy_path(raw, expected):
    assert sanitizer.clean(raw) == expected


# ── step 5: ?? prefix → TranslationError ─────────────────────────────────────

def test_clean_parse_failure_with_reason():
    with pytest.raises(sanitizer.TranslationError, match="unrecognised"):
        sanitizer.clean("?? unrecognised")


def test_clean_parse_failure_no_reason():
    # bare "??" with no suffix → fallback message
    with pytest.raises(sanitizer.TranslationError, match="model could not parse"):
        sanitizer.clean("??")


# ── step 6: empty → TranslationError ─────────────────────────────────────────

def test_clean_empty_string():
    with pytest.raises(sanitizer.TranslationError, match="empty response"):
        sanitizer.clean("")


def test_clean_whitespace_only():
    with pytest.raises(sanitizer.TranslationError, match="empty response"):
        sanitizer.clean("   \n  ")


def test_clean_fence_whitespace_only():
    # fence stripped by step 2; whitespace collapses to "" at step 4; step 6 raises
    with pytest.raises(sanitizer.TranslationError, match="empty response"):
        sanitizer.clean("```\n   \n```")


# ── step 7: destructive block ─────────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "Record Cue 5 Enter",
    "Delete Cue 10 Enter",
    "Update Enter",
    'Label Cue 5 "scene" Enter',
    "record cue 5 enter",           # case-insensitive
])
def test_clean_destructive_blocked(cmd):
    with patch.object(sanitizer.settings, "block_destructive", True):
        with pytest.raises(sanitizer.DestructiveCommandError) as exc_info:
            sanitizer.clean(cmd)
        assert exc_info.value.syntax   # syntax attribute populated on the exception


def test_clean_destructive_allowed_when_flag_false():
    with patch.object(sanitizer.settings, "block_destructive", False):
        result = sanitizer.clean("Record Cue 5 Enter")
    assert result == "Record Cue 5 Enter"


def test_clean_destructive_blocked_when_command_contains_at_keyword():
    # Destructive check matches on the command verb alone; the "At" keyword elsewhere
    # in the string does not affect whether the command is blocked.
    with patch.object(sanitizer.settings, "block_destructive", True):
        with pytest.raises(sanitizer.DestructiveCommandError):
            sanitizer.clean("Record Cue 5 At 100 Enter")


# ── multi-line edge case ──────────────────────────────────────────────────────

def test_clean_multiline_skips_leading_blank_lines():
    # Step 4: "first non-empty line" — blank leading lines are skipped, not treated as content.
    result = sanitizer.clean("  \nChan 1 @ Full Enter\nChan 2 @ 50")
    assert result == "Chan 1 @ Full Enter"
