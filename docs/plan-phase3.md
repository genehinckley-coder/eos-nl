# Phase 3: Per-Channel Intensity Levels & Cue Count

## Context

Phases 1–2 delivered one-way command dispatch and live board state (show name, active/next cue, mode, connection). The frontend status bar has two fields that remain fake:

- **`cueTotal`** — hardcoded `"—"` in `app.jsx:252`. No backend support.
- **`channels`** — seeded random mock data. The `ChannelStrip` in `status-bar.jsx` renders visual intensity bars but they're not connected to the console.

This plan delivers real data for both fields using the EOS OSC pull+notify pattern documented in `EOS_OSC_REFERENCE.md`.

> **Key architectural finding (from OSC reference + community research):**
> EOS does **not** push per-channel intensity via subscription alone. It uses a **request/notify/re-request** pattern: query on startup, receive change notification, re-query on change. Both cue count and channel intensity use this model.

---

## EOS OSC Strategy

### Cue Count (Pull + Notify)

| Step | OSC address | Direction | Notes |
|------|-------------|-----------|-------|
| Query | `/eos/get/cue/<list>/count` | → EOS | Send for active cue list |
| Response | `/eos/out/get/cue/<list>/count` | ← EOS | uint32 |
| Notify | `/eos/out/notify/cue/<list>/list/<idx>/<count>` | ← EOS | Pushed when any cue is added/deleted/changed |
| Re-query | `/eos/get/cue/<list>/count` | → EOS | On notify |

Active cue list number is already parsed from `/eos/out/active/cue/text` (e.g., `"1/5 Intro …"` → list `"1"`).

### Channel Intensity (Patch Enumeration + Notify)

EOS stores live output intensity per channel in the patch table. There is no streaming address for all-channel intensities; the correct approach is patch enumeration.

| Step | OSC address | Direction | Notes |
|------|-------------|-----------|-------|
| Patch count | `/eos/get/patch/count` | → EOS | Total patched channels |
| Response | `/eos/out/get/patch/count` | ← EOS | uint32 |
| Per-channel (by index) | `/eos/get/patch/index/<n>` | → EOS | n = 0 to count–1 |
| Response | `/eos/out/get/patch/<chan>/<part>/list/<idx>/<count>` | ← EOS | arg[4]=chan, arg[7]=current_level (uint32, 0–100) |
| Notify | `/eos/out/notify/patch/list/<idx>/<count>` | ← EOS | Pushed when any patch changes |
| Re-query | `/eos/get/patch/index/<n>` for changed indices | → EOS | On notify |

**Important:** `current_level` is uint32 (0–100 scale, not 0.0–1.0). No multiplication needed.

### Grand Master — Deferred

The OSC reference does not expose a push-subscription address for the Grand Master level. The only GM feedback path requires constructing a fader bank and monitoring fader position, which is disproportionately complex for a status display. `gm` remains hardcoded at `100` and is deferred to a future phase.

---

## What Phase 3 Does NOT Include

- Grand Master live value (deferred)
- Multiple cue list tracking (only the active cue list's count is shown)
- Sub-1-second channel updates (patch enumeration has latency; this is acceptable for a status strip)
- Test coverage for sanitizer or translate route (Phase 4)
- Pending cue label (Phase 4)

---

## Implementation Plan

### Step 1: Backend — Extend `BoardState` and add get/notify handlers

**File: `backend/eos_client.py`**

#### 1a. Extend `BoardState`

Add two fields with defaults (so existing test fixtures don't break):

```python
@dataclasses.dataclass
class BoardState:
    # ... existing fields unchanged ...
    cue_count:  Optional[int]       = None
    channels:   dict[int, int]      = dataclasses.field(default_factory=dict)
    # keys = channel numbers (int), values = 0–100 intensity (int)
```

`channels` is a sparse dict — only channels with a non-zero level or a recently-queried patch entry are stored. Channels not in the dict are treated as 0 in the API response.

#### 1b. Add staging dict for channel batch writes

To avoid O(n) dict copy on every patch response (one per channel), accumulate updates in a mutable staging dict and commit to `board_state` in a single `dataclasses.replace()` call after the enumeration batch completes:

```python
def __init__(self):
    # ... existing init ...
    self._channel_staging: dict[int, int] = {}     # accumulated during enumeration
    self._patch_count: int = 0                      # total patched channels
    self._enumerating: bool = False                 # guard against concurrent enumerations
```

#### 1c. Extend `_handle_osc_message()`

Add handlers for the new incoming addresses:

```python
# Patch count response → start enumeration
elif addr == "/eos/out/get/patch/count" and params:
    self._patch_count = int(params[0])
    if self._patch_count > 0 and not self._enumerating:
        asyncio.ensure_future(self._enumerate_patch())

# Per-channel patch response
elif addr.startswith("/eos/out/get/patch/") and "/list/" in addr and params:
    parts = addr.split("/")
    # address: /eos/out/get/patch/<chan>/<part>/list/<idx>/<count>
    # index:       0   1   2    3     4     5    6     7     8
    try:
        chan = int(parts[5])      # channel number
        level = int(params[7])   # current_level, uint32, 0–100
        self._channel_staging[chan] = level
    except (IndexError, ValueError):
        pass

# Cue count response — update board state
elif addr.startswith("/eos/out/get/cue/") and addr.endswith("/count") and params:
    self.board_state = dataclasses.replace(
        self.board_state, cue_count=int(params[0])
    )

# Patch notify → re-enumerate
elif addr.startswith("/eos/out/notify/patch/"):
    if not self._enumerating:
        asyncio.ensure_future(self._request_patch_count())

# Cue notify → re-query count for active list
elif addr.startswith("/eos/out/notify/cue/"):
    parts = addr.split("/")
    # address: /eos/out/notify/cue/<list>/list/...
    if len(parts) >= 6:
        cue_list = parts[5]
        asyncio.ensure_future(self._request_cue_count(cue_list))
```

#### 1d. Add helper coroutines

```python
async def _request_patch_count(self) -> None:
    """Send patch count query — triggers enumeration via _handle_osc_message."""
    try:
        packet = self._build_raw_packet("/eos/get/patch/count")
        self._writer.write(packet)
        await self._writer.drain()
    except Exception as exc:
        logger.warning("patch count request failed: %s", exc)

async def _enumerate_patch(self) -> None:
    """Iterate all patch indexes, collect into _channel_staging, commit to board_state."""
    if self._enumerating:
        return
    self._enumerating = True
    try:
        self._channel_staging.clear()
        for n in range(self._patch_count):
            try:
                packet = self._build_raw_packet(f"/eos/get/patch/index/{n}")
                self._writer.write(packet)
                await self._writer.drain()
                await asyncio.sleep(0.02)   # 20ms pacing — EOS rate limit is 50ms minimum
            except Exception as exc:
                logger.warning("patch index %d request failed: %s", n, exc)
                break
        # Commit only non-zero channels (active channels only, per design decision)
        active = {k: v for k, v in self._channel_staging.items() if v > 0}
        self.board_state = dataclasses.replace(
            self.board_state, channels=active
        )
        self._channel_staging.clear()
    finally:
        self._enumerating = False

async def _request_cue_count(self, cue_list: str) -> None:
    """Query cue count for the given cue list number."""
    try:
        packet = self._build_raw_packet(f"/eos/get/cue/{cue_list}/count")
        self._writer.write(packet)
        await self._writer.drain()
    except Exception as exc:
        logger.warning("cue count request failed for list %s: %s", cue_list, exc)
```

#### 1e. Call initial queries after subscribe

In the existing `_send_subscribe()` method (or immediately after it succeeds in `connect()`), add:

```python
# After subscribe — request initial cue count and patch data
await self._request_cue_count("1")          # default to cue list 1
await self._request_patch_count()           # triggers enumeration via response handler
```

Also, when `active_cue_list` changes in `_handle_osc_message`, trigger a fresh cue count query:

```python
elif addr == "/eos/out/active/cue/text" and params:
    cl, cq, label = self._parse_cue_text(str(params[0]))
    old_list = self.board_state.active_cue_list
    self.board_state.active_cue_list  = cl
    self.board_state.active_cue       = cq
    self.board_state.active_cue_label = label
    if cl and cl != old_list:   # cue list changed — refresh count
        asyncio.ensure_future(self._request_cue_count(cl))
```

---

### Step 2: Backend — Update `BoardStateResponse`

**File: `backend/routes/board_state.py`**

Add `ChannelLevel` model and new fields. Replace the `dataclasses.asdict()` shortcut with an explicit factory to handle the dict→list conversion:

```python
from pydantic import BaseModel
from typing import Optional
import dataclasses
from eos_client import eos_client, BoardState


class ChannelLevel(BaseModel):
    id: int
    level: int   # 0–100


class BoardStateResponse(BaseModel):
    # existing fields unchanged
    show_name:        Optional[str]
    active_cue:       Optional[str]
    active_cue_list:  Optional[str]
    active_cue_label: Optional[str]
    next_cue:         Optional[str]
    next_cue_list:    Optional[str]
    mode:             str
    connected:        bool
    last_updated:     Optional[float]
    # new fields
    cue_count:        Optional[int]
    channels:         list[ChannelLevel]


def _board_state_to_response(bs: BoardState) -> BoardStateResponse:
    """Convert BoardState to API response, expanding sparse channels dict to sorted list."""
    ch_list = sorted(
        [ChannelLevel(id=k, level=v) for k, v in bs.channels.items()],
        key=lambda c: c.id,
    )
    return BoardStateResponse(
        show_name=bs.show_name,
        active_cue=bs.active_cue,
        active_cue_list=bs.active_cue_list,
        active_cue_label=bs.active_cue_label,
        next_cue=bs.next_cue,
        next_cue_list=bs.next_cue_list,
        mode=bs.mode,
        connected=bs.connected,
        last_updated=bs.last_updated,
        cue_count=bs.cue_count,
        channels=ch_list,
    )


@router.get("/api/board-state", response_model=BoardStateResponse)
async def board_state() -> BoardStateResponse:
    return _board_state_to_response(eos_client.board_state)
```

Note: `channels` is a **sparse sorted list of active channels only** — channels with level 0 are excluded. The frontend `ChannelStrip` renders whatever it receives; the ResizeObserver caps visible count to viewport width. This was a confirmed design decision: show only what's lit, not dark channels.

---

### Step 3: Frontend — Wire Real Data

**File: `frontend/app.jsx`**

#### 3a. Remove all mock channel code

Remove the `useMemo` block that seeds random channel distribution (approximately lines 30–41).

#### 3b. Remove the `channelCount` seed effect

Remove (or replace) the `useEffect` at approximately lines 207–216 that calls `seedChannels(tweaks.channelCount)`. This effect overwrites live EOS data whenever the tweak changes. Replace with a no-op, or change `channelCount` to a "how many to display" slice that operates on the rendered strip, not the source data.

#### 3c. Update state initialization

```js
const [status, setStatus] = useState({
  // existing fields ...
  cueTotal: "—",
  channels: [],    // start empty — no mock data
});
```

#### 3d. Update poll handler

In the `setStatus` updater inside the poll `fetch` callback (approximately lines 243–255), add:

```js
cueTotal: data.cue_count != null ? String(data.cue_count) : st.cueTotal,
channels: data.connected
  ? (data.channels ?? st.channels)    // ?? preserves last-known if field absent
  : st.channels,                       // freeze on disconnect
```

The `??` (nullish coalescing) ensures the first poll before EOS sends channel data doesn't wipe out the empty initial state with `undefined`.

#### 3e. Verify `interpretSyntax()` mutators

The blackout, range, and channel-level mutators in `interpretSyntax()` call `.map()` on `st.channels`. With a sparse list (not a zero-padded full array), commands like "Chan 1 Thru 50 @ Full" will only update channels already in the array. For optimistic updates this is acceptable — the next poll will bring ground truth. Add a note in a code comment if this limitation matters for the UX.

---

### Step 4: Update Tests

**File: `backend/tests/test_board_state_route.py`**

Update `_ONLINE_STATE` fixture to include new fields (must be done atomically with Step 2):

```python
_ONLINE_STATE = BoardState(
    # existing fields ...
    cue_count=12,
    channels={1: 100, 2: 75, 5: 50},
)
```

Add assertions that the response includes:
- `cue_count: 12`
- `channels` containing `[{id:1, level:100}, {id:2, level:75}, {id:5, level:50}]` in id order

**File: `backend/tests/test_eos_client.py`**

Add unit tests for new `_handle_osc_message` branches (call the method directly — no network needed):

- `/eos/out/get/patch/count` with valid count, zero, missing params (no crash)
- `/eos/out/get/patch/<chan>/<part>/list/<idx>/<count>` — channel number extracted correctly, level stored in `_channel_staging`
- `/eos/out/get/cue/1/count` → `board_state.cue_count` updated
- `/eos/out/notify/patch/...` — `_request_patch_count` called (mock the coroutine)
- `/eos/out/notify/cue/1/...` — `_request_cue_count("1")` called
- Patch response address with malformed parts → silently ignored (no crash)

---

## Implementation Order

1. `backend/eos_client.py` — BoardState fields, staging dict, handlers, helper coroutines, initial queries after subscribe
2. `backend/routes/board_state.py` — ChannelLevel model, `_board_state_to_response()`, updated route
3. `backend/tests/test_board_state_route.py` — update fixture (same commit as step 2)
4. `backend/tests/test_eos_client.py` — new handler tests
5. `frontend/app.jsx` — remove mock seed, remove channelCount effect, update poll handler, initialize channels as `[]`

---

## Edge Cases

| Scenario | Handling |
|---|---|
| EOS has 0 patched channels | `patch_count=0` → no enumeration → `channels=[]` → `ChannelStrip` renders empty (blank, no crash) |
| Enumeration interrupted (disconnect mid-loop) | `_enumerating=False` in `finally` block; `_writer.write()` raises, loop breaks, commit is skipped |
| Concurrent notify during enumeration | `if self._enumerating: return` guard drops the concurrent trigger; re-enumerate fires again on the next notify |
| `active_cue_list` is None on startup | `_request_cue_count` guards on empty string; initial query uses `"1"` as default |
| Large show (500+ channels) | Enumeration at 20ms pacing takes ~10s; `channels` updates only after full batch. Acceptable for a status strip. |
| `cue_count` before first response | `None` in `BoardState` → `"—"` in frontend (existing `?? st.cueTotal` pattern) |
| Disconnect while `channels` is populated | `board_state.connected=False` but `channels` unchanged → frontend freezes strip at last-known values |

---

## Verification

```powershell
cd backend
pytest tests/ -v     # all existing + new tests pass
python main.py
```

Manual verification against live EOS console:
1. Open UI — channel strip is empty (no mock data), `cueTotal` shows `"—"`
2. Wait ~2–10s after connect — channel strip populates with real levels, `cueTotal` shows count (e.g., `"14"`)
3. Move a fader in EOS — channel strip updates after the next patch notify + re-enumeration cycle (~5–15s latency)
4. Fire a cue that changes intensities — same latency window
5. Add or delete a cue in EOS — `cueTotal` updates within ~2s
6. Disconnect EOS — channel strip freezes at last values, connection pill goes Offline
7. Reconnect — channel strip refreshes after new enumeration

---

## Confirmed Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Channel update latency | ~5–15s acceptable | Patch enumeration via OSC; no sACN/Art-Net needed |
| Channel strip content | Active channels only (level > 0) | Sparse list; dark channels excluded from strip |
| Phase 4 timing | After Phase 3 ships | Test coverage and pending cue label are independent cleanup |

## What is NOT in Phase 3

- **Grand Master live value** — no direct subscribe-push OSC address; deferred
- **Sub-5s channel update latency** — patch enumeration is inherently slow; sub-second updates would require sACN/Art-Net DMX monitoring, which is a different connection type
- **Multiple cue list total counts** — only the currently active list is tracked
- **Test coverage for sanitizer and translate route** — Phase 4
- **Pending cue label** — Phase 4
