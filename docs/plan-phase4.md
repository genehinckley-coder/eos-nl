# Phase 4: Test Coverage & Pending Cue Label

## Context

Phases 1–3 shipped the full backend/frontend pipeline: natural-language → Ollama → sanitizer →
OSC dispatch, live board state subscription, per-channel selected intensity display, and cue count.
Two backend modules — `sanitizer.py` and `routes/translate.py` — have zero test coverage. One
display field — the pending cue's label — is parsed but silently dropped. Phase 4 closes both gaps.

> This phase contains no new OSC or Ollama work. It is entirely test coverage + a small feature.

---

## What Phase 4 Does NOT Include

- Grand Master live value (no EOS OSC mechanism; deferred indefinitely)
- Frontend component tests (no test runner for CDN + Babel Standalone; deferred)
- Rate limiting or authentication (out of original project scope)
- sACN/Art-Net monitoring (significant scope; separate phase if needed)
- `ollama_client.py` tests (simple wrapper, covered indirectly by translate route tests)

---

## Implementation Plan

### Step 1 — `backend/tests/test_sanitizer.py` (new file)

**What to test:** every branch in the 9-step pipeline in `sanitizer.py`.

**Patching strategy:** `sanitizer.py` reads `settings.block_destructive` from its own import, not from
the test module. Override per-test with `patch.object(sanitizer.settings, "block_destructive", True/False)`.
Do **not** use the string form `patch("sanitizer.settings.block_destructive")` — `settings` is a
pydantic-settings instance, not a submodule, so the dotted string path will raise `AttributeError`.

#### Happy-path parametrized table

```python
@pytest.mark.parametrize("raw, expected", [
    # step 2: markdown fence stripped
    ("```eos\nChan 1 @ Full Enter\n```", "Chan 1 @ Full Enter"),
    # step 3: surrounding quotes stripped
    ('"Chan 1 @ Full Enter"',            "Chan 1 @ Full Enter"),
    # step 4: first non-empty line taken
    ("Chan 1 @ Full Enter\nChan 2 @ 50", "Chan 1 @ Full Enter"),
    # step 8: "At" normalized → "@"
    ("Chan 1 At Full Enter",             "Chan 1 @ Full Enter"),
    # step 8: case-insensitive normalization
    ("Chan 1 at Full Enter",             "Chan 1 @ Full Enter"),
    # step 9: missing Enter appended
    ("Chan 1 @ Full",                    "Chan 1 @ Full Enter"),
    # step 9: already ends with "#" — no Enter added
    ("Go #",                             "Go #"),
    # step 9: already ends with "Enter" — no duplicate
    ("Chan 1 @ Full Enter",              "Chan 1 @ Full Enter"),
    # step 2+4+8+9: full chain
    ("```\nChan 5 At 75\n```",           "Chan 5 @ 75 Enter"),
])
def test_clean_happy_path(raw, expected):
    assert sanitizer.clean(raw) == expected
```

#### Error-path tests

```python
# Step 5: "??" prefix → TranslationError
def test_clean_parse_failure_prefix():
    with pytest.raises(sanitizer.TranslationError, match="model could not parse"):
        sanitizer.clean("?? unrecognised")

def test_clean_parse_failure_empty_suffix():
    with pytest.raises(sanitizer.TranslationError):
        sanitizer.clean("??")

# Step 6: empty → TranslationError
def test_clean_empty_string():
    with pytest.raises(sanitizer.TranslationError, match="empty response"):
        sanitizer.clean("")

def test_clean_whitespace_only():
    with pytest.raises(sanitizer.TranslationError, match="empty response"):
        sanitizer.clean("   \n  ")

# Step 7: destructive block (BLOCK_DESTRUCTIVE=True, the default)
@pytest.mark.parametrize("cmd", [
    "Record Cue 5 Enter",
    "Delete Cue 10 Enter",
    "Update Enter",
    "Label Cue 5 \"scene\" Enter",
    "record cue 5 enter",           # case-insensitive
])
def test_clean_destructive_blocked(cmd):
    with patch.object(sanitizer.settings, "block_destructive", True):
        with pytest.raises(sanitizer.DestructiveCommandError) as exc_info:
            sanitizer.clean(cmd)
        assert exc_info.value.syntax  # syntax attribute is set on the exception

# Step 7: destructive allowed when BLOCK_DESTRUCTIVE=False
def test_clean_destructive_allowed_when_flag_false():
    with patch.object(sanitizer.settings, "block_destructive", False):
        result = sanitizer.clean("Record Cue 5 Enter")
    assert result == "Record Cue 5 Enter"  # no exception; At normalization leaves it unchanged

# Step 7 ordering: destructive check runs AFTER At normalization (step 8 runs after step 7 in the pipeline)
# "Record" block must fire even if the raw text contains "At"
def test_clean_destructive_block_fires_before_at_normalization():
    # The pattern matches before At→@ runs; this is intentional (steps 7 then 8)
    with patch.object(sanitizer.settings, "block_destructive", True):
        with pytest.raises(sanitizer.DestructiveCommandError):
            sanitizer.clean("Record Cue 5 At 100 Enter")
```

**Edge cases to cover in additional tests:**
- Code fence wrapping whitespace-only content (e.g., `"```\n   \n```"`) → raises `TranslationError("model returned an empty response")`. Note: the fence is stripped by Step 2, leaving whitespace which Step 4 reduces to `""`, then Step 6 raises — NOT Step 2. The match string should be `"empty response"`, not anything about fences.
- Multi-word `Label Cue` variant → blocked by `label\s+cue` pattern in `_DESTRUCTIVE_PATTERN`
- Multi-line model output (e.g., `"Chan 1 @ Full Enter\nChan 2 @ 50"`) → only the first non-empty line is taken; the second is silently dropped (Step 4 behavior)

---

### Step 2 — `backend/tests/test_translate_route.py` (new file)

**Pattern:** FastAPI `TestClient` + `patch` on the two callables the route imports.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from routes.translate import router

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)
```

**Patch targets (always use the import path inside the module under test):**
- `routes.translate.ollama_client.translate` → `AsyncMock`
- `routes.translate.eos_client.send_cmd` → `AsyncMock`
- `patch.object(routes.translate.settings, "eos_host", ...)` → string (use `patch.object`, not string path — `settings` is a pydantic instance, not a submodule)

**`block_destructive` caveat:** `sanitizer.clean()` reads `settings` from **sanitizer's own import**, not from `routes.translate`. To trigger `DestructiveCommandError` in route tests, patch `sanitizer.settings.block_destructive` (same as in Step 1), OR — simpler — patch `sanitizer.clean` directly to raise `DestructiveCommandError`. The latter keeps route tests independent of sanitizer internals:

```python
from sanitizer import DestructiveCommandError

def test_destructive_blocked():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.sanitizer.clean", side_effect=DestructiveCommandError("blocked", syntax="Record Cue 5 Enter")), \
         patch.object(routes.translate.settings, "eos_host", "127.0.0.1"):
        mock_tr.return_value = "Record Cue 5 Enter"
        r = _client.post("/api/translate", json={"input": "record cue 5"})
    data = r.json()
    assert data["ok"] is False
    assert data["syntax"] == "Record Cue 5 Enter"
    assert data["sent"] is False
```

#### Test matrix

| Test | ollama mock | sanitizer.clean mock | eos_host | send_cmd | Expected response |
|------|-------------|---------------------|----------|----------|-------------------|
| `test_empty_input` | — | — | any | — | `ok=False, error="empty input", source="bridge"` |
| `test_valid_command_dispatched` | returns syntax | passthrough (real) | set | succeeds | `ok=True, sent=True` (assert both) |
| `test_ollama_error` | raises `OllamaError` | — | set | — | `ok=False, source=model_name` |
| `test_translation_error` | returns `"?? …"` | raises `TranslationError` | set | — | `ok=False, sent=False, syntax=None` |
| `test_destructive_blocked` | returns raw syntax | raises `DestructiveCommandError` | set | — | `ok=False, syntax≠None, sent=False` |
| `test_eos_host_unconfigured` | returns syntax | passthrough (real) | `""` | — | `ok=False, sent=False, error∋"EOS_HOST"` |
| `test_eos_unreachable` | returns syntax | passthrough (real) | set | raises `EosUnreachableError` | `ok=False, sent=False, error∋"unreachable"` |
| `test_whitespace_only_input` | — | — | any | — | `ok=False, error="empty input"` |

**Snippet — valid command flow:**

```python
def test_valid_command_dispatched():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.eos_client.send_cmd", new_callable=AsyncMock) as mock_send, \
         patch.object(routes.translate.settings, "eos_host", "127.0.0.1"):
        mock_tr.return_value = "Chan 1 @ Full Enter"
        r = _client.post("/api/translate", json={"input": "set channel 1 to full"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["sent"] is True          # invariant: ok=True implies sent=True (per CLAUDE.md)
    assert data["syntax"] == "Chan 1 @ Full Enter"
    mock_send.assert_awaited_once_with("Chan 1 @ Full Enter")
```

> **Invariant lock-in:** every test where `ok=False` must also assert `sent=False`. The CLAUDE.md spec states "`sent=False` with `ok=True` should not happen" — the success-path test is the only place to assert the positive direction (`ok=True → sent=True`).

**Snippet — destructive block (verifies syntax field is populated even on ok=False):**

```python
def test_destructive_blocked():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.sanitizer.clean",
               side_effect=DestructiveCommandError("blocked", syntax="Record Cue 5 Enter")), \
         patch.object(routes.translate.settings, "eos_host", "127.0.0.1"):
        mock_tr.return_value = "Record Cue 5 Enter"
        r = _client.post("/api/translate", json={"input": "record cue 5"})
    data = r.json()
    assert data["ok"] is False
    assert data["syntax"] == "Record Cue 5 Enter"  # syntax echoed for UI display
    assert data["sent"] is False
```

**Note on `source` field:** The translate route always returns `source=settings.model_name` except for
empty input where it returns `source="bridge"`. Tests should assert `source` explicitly to lock in this
contract.

---

### Step 3 — `next_cue_label` feature

Currently `_parse_cue_text()` extracts a label for pending cues but the handler discards it:
```python
# existing (eos_client.py ~line 179)
cl, cq, _ = self._parse_cue_text(str(params[0]))   # label silently dropped
```

#### 3a. `backend/eos_client.py`

Add `next_cue_label: Optional[str] = None` to `BoardState`:

```python
@dataclasses.dataclass
class BoardState:
    # ... existing fields ...
    next_cue_label:   Optional[str]        = None   # add after next_cue_list
```

Change the pending cue handler to capture the label:

```python
elif addr == "/eos/out/pending/cue/text" and params:
    cl, cq, label = self._parse_cue_text(str(params[0]))
    self.board_state = dataclasses.replace(
        self.board_state, next_cue_list=cl, next_cue=cq, next_cue_label=label, last_updated=now
    )
```

#### 3b. `backend/routes/board_state.py`

Add to `BoardStateResponse`:
```python
next_cue_label:   Optional[str]
```

Add to `_to_response()`:
```python
next_cue_label=bs.next_cue_label,
```

#### 3c. `frontend/app.jsx`

Add `nextCueLabel: null` to initial status state and cache load:

```js
const [status, setStatus] = useState(() => {
  const c = loadStatusCache();
  return {
    // ... existing fields ...
    nextCueLabel: null,   // add
  };
});
```

Wire in poll handler (inside `setStatus`):
```js
nextCueLabel: data.connected ? (data.next_cue_label ?? st.nextCueLabel) : st.nextCueLabel,
```

#### 3d. `frontend/status-bar.jsx`

Update the `Next` metric to display the label as a dim sub-line when present:

```jsx
// Replace the existing <Metric label="Next" value={state.nextCue} />
<div style={sbStyles.metric}>
  <div style={sbStyles.metricLabel}>Next</div>
  <div>
    <span style={sbStyles.metricValue}>{state.nextCue}</span>
    {state.nextCueLabel && (
      <span style={{ ...sbStyles.metricSub, display: "block", fontSize: 9 }}>
        {state.nextCueLabel}
      </span>
    )}
  </div>
</div>
```

Or extract to a `MetricWithSub` variant if cleaner, reusing existing `sbStyles.metricSub` style token.

#### 3e. Update tests (must be atomic with 3a–3b)

**`test_board_state_route.py`:**
- Add `next_cue_label="Verse"` to `_ONLINE_STATE` fixture
- Add `test_online_next_cue_label()` asserting `data["next_cue_label"] == "Verse"`
- Add `test_offline_next_cue_label_null()` to `test_offline_fields_null`

**`test_eos_client.py`:**
- Update `test_handle_osc_pending_cue_text()` to assert `board_state.next_cue_label` is set from parsed label
- Add `test_handle_osc_pending_cue_text_no_label()` for unlabeled cue (`"1/3 3.00 50%"` → `next_cue_label=None`)

---

## Implementation Order

1. `backend/tests/test_sanitizer.py` — independent, no code changes required
2. `backend/tests/test_translate_route.py` — independent, only patches
3. `backend/eos_client.py` — add `next_cue_label` to `BoardState`, update pending cue handler
4. `backend/routes/board_state.py` + `tests/test_board_state_route.py` — update together (same step)
5. `backend/tests/test_eos_client.py` — update pending cue tests
6. `frontend/app.jsx` + `frontend/status-bar.jsx` — wire and display `nextCueLabel`

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Pending cue has no label (e.g., `"1/3 3.00 50%"`) | `_parse_cue_text` returns `None` for label → `next_cue_label=None` → UI shows nothing under cue number |
| `next_cue_label` is very long string | No truncation in backend; frontend `metricSub` uses `overflow: hidden` via parent flex box |
| `BLOCK_DESTRUCTIVE=False` test isolation | Each test patches `sanitizer.settings.block_destructive` — never reads actual `.env` |
| Translate route with whitespace-only input | `raw_input.strip()` → empty → early return `ok=False, source="bridge"` |
| `send_cmd` awaited with exactly the sanitized syntax | `mock_send.assert_awaited_once_with(syntax)` locks the contract |

---

## Verification

```powershell
cd backend
pytest tests/ -v     # all tests pass (target: ~70 tests after Phase 4)
```

Manual smoke test (no EOS required):
1. POST `{"input": ""}` → `ok=false, error="empty input"`
2. POST `{"input": "record cue 5"}` → `ok=false, syntax not null` (destructive blocked)
3. POST `{"input": "go to cue 10"}` → `ok=true` (with Ollama running and EOS connected)

Live board-state verification:
1. EOS pending cue shows a labeled cue (e.g., `"1/6 Verse 5.00"`) → `next_cue_label` shows `"Verse"` in status bar
2. EOS pending cue is unlabeled → sub-label is absent from UI

---

## Confirmed Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sanitizer test isolation for `BLOCK_DESTRUCTIVE` | `patch.object(sanitizer.settings, "block_destructive", ...)` | Avoids reading real `.env`; test is self-contained |
| Translate route patch targets | `routes.translate.ollama_client.translate`, `routes.translate.eos_client.send_cmd` | Patch at import site inside the module under test |
| `next_cue_label` nullable | `Optional[str] = None` | Unlabeled cues are common; UI hides sub-label when `None` |
| No frontend tests | Deferred | CDN + Babel Standalone has no test runner; would require full Playwright/Cypress setup |
