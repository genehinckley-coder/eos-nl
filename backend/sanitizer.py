import re
from config import settings


class TranslationError(Exception):
    pass


class DestructiveCommandError(Exception):
    def __init__(self, message: str, syntax: str):
        super().__init__(message)
        self.syntax = syntax


# Commands that mutate show data — blocked in Phase 1 by default
_DESTRUCTIVE_PATTERN = re.compile(
    r"^(record|delete|update|label\s+cue)\b",
    re.IGNORECASE,
)

# Strip markdown code fences like ```eos ... ``` or just ``` ... ```
_CODE_FENCE = re.compile(r"```[^\n]*\n?(.*?)```", re.DOTALL)

# Normalize the EOS keyword "At" → "@" for frontend interpretSyntax compatibility.
# EOS accepts both forms; the React prototype's regex engine only matches "@".
_AT_KEYWORD = re.compile(r"\bAt\b", re.IGNORECASE)


def clean(raw: str) -> str:
    """Validate and normalize model output before sending to the EOS console."""

    # Step 1: strip whitespace
    text = raw.strip()

    # Step 2: strip markdown code fences
    fence_match = _CODE_FENCE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Step 3: strip surrounding quotes (single or double)
    text = text.strip("\"'`")

    # Step 4: take only the first non-empty line
    for line in text.splitlines():
        line = line.strip()
        if line:
            text = line
            break
    else:
        text = ""

    # Step 5: ?? prefix → translation failure
    if text.startswith("??"):
        reason = text[2:].strip() or "model could not parse the command"
        raise TranslationError(reason)

    # Step 6: empty output
    if not text:
        raise TranslationError("model returned an empty response")

    # Step 7: destructive command blocklist
    if settings.block_destructive and _DESTRUCTIVE_PATTERN.match(text):
        raise DestructiveCommandError(
            "destructive command blocked in Phase 1 — set BLOCK_DESTRUCTIVE=false to enable",
            syntax=text,
        )

    # Step 8: normalize "At" → "@" so frontend interpretSyntax regexes match
    text = _AT_KEYWORD.sub("@", text)

    # Step 9: ensure command is terminated so EOS executes it
    if not (text.endswith("Enter") or text.endswith("#")):
        text = text + " Enter"

    return text
