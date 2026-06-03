# Phase 2: Live EOS Board State Display

## Context

The eos-nl project is a FastAPI + React (no build step, CDN Babel) web app that translates natural language to EOS lighting console commands via OSC/TCP. Phase 1 delivered one-way command dispatch: the user types natural language → Ollama translates → sanitizer validates → EOS receives the OSC command.

**Problem:** The frontend status bar (cue number, next cue, Live/Blind mode, show name) is entirely simulated — seeded on startup and updated only by local regex parsing of sent commands. It does not reflect reality. If you run a cue from the physical console, the frontend never knows.

**Goal:** Subscribe to EOS's OSC push mechanism and display the live board state (active cue, next cue, console mode, show name, connection status) in the existing status bar. Keep the architecture simple: HTTP polling, no WebSocket.

---

## EOS OSC State-Querying Strategy

EOS sends real-time status messages automatically once subscribed:

| OSC Address | Data | Rate |
|---|---|---|
| `/eos/out/active/cue/text` | `"1/5 Intro 3.00 75%"` | ~1/sec |
| `/eos/out/pending/cue/text` | `"1/6 Verse 5.00"` | on change |
| `/eos/out/event/state` | int: 0=Blind, 1=Live | on change |
| `/eos/out/show/name` | string: show title | on load |

Subscribe with `/eos/subscribe=1` (sends int arg `1`). EOS then pushes changes as OSC 1.0 TCP frames (same 4-byte big-endian length-prefix framing already used for outbound commands).

The init sequence:
1. Connect TCP to EOS
2. Send `/eos/subscribe=1`
3. Listen continuously for `/eos/out/*` messages
4. On disconnect: reconnect and re-subscribe

---

## Implementation Plan

### File 1: `backend/eos_client.py`

**What changes:** Add a `BoardState` dataclass, an inbound OSC receive loop, and subscription support. This is the largest change.

#### Move pythonosc receive imports to top level

Add alongside the existing `from pythonosc import osc_message_builder`:

```python
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message import ParseError as OscParseError
```

#### Add imports and `BoardState`

```python
import dataclasses
import re
from typing import Optional

@dataclasses.dataclass
class BoardState:
    show_name:        Optional[str]   = None
    active_cue:       Optional[str]   = None
    active_cue_list:  Optional[str]   = None
    active_cue_label: Optional[str]   = None
    next_cue:         Optional[str]   = None
    next_cue_list:    Optional[str]   = None
    mode:             str             = "unknown"   # "Live" | "Blind" | "unknown"
    connected:        bool            = False
    last_updated:     Optional[float] = None        # time.time() wall-clock
```

`last_updated` uses `time.time()` (wall-clock), not `time.monotonic()`, so the frontend can compare it to `Date.now() / 1000` to detect staleness.

#### Update `__init__`

```python
def __init__(self):
    self._reader: asyncio.StreamReader | None = None
    self._writer: asyncio.StreamWriter | None = None
    self._last_sent: float = 0.0
    self._lock = asyncio.Lock()
    self._connect_lock = asyncio.Lock()   # prevents concurrent reconnects
    self._listen_task: asyncio.Task | None = None
    self.board_state = BoardState()
```

#### Update `connect()` — set `board_state.connected = True`

After the `logger.info("Connected…")` line, add:

```python
self.board_state.connected = True
```

#### Update `_close_writer()` — set `board_state.connected = False`

After setting `self._writer = None` and `self._reader = None`, add:

```python
self.board_state.connected = False
```

#### Refactor `_build_packet` → `_build_raw_packet`

```python
def _build_raw_packet(self, address: str, *args) -> bytes:
    builder = osc_message_builder.OscMessageBuilder(address=address)
    for arg in args:
        builder.add_arg(arg)
    msg = builder.build()
    return struct.pack(">I", len(msg.dgram)) + msg.dgram
```

Rewrite `_build_packet(cmd)` to call `_build_raw_packet("/eos/cmd", cmd)`.  
Rewrite `ping()` to call `_build_raw_packet("/eos/ping")`.

#### Update `_reconnect()` — add `_connect_lock`

```python
async def _reconnect(self) -> None:
    async with self._connect_lock:
        if self.connected:
            return   # another coroutine already reconnected
        for attempt in range(1, _RECONNECT_ATTEMPTS + 1):
            await self._close_writer()
            try:
                await self.connect()
                return
            except Exception as exc:
                logger.warning("Reconnect attempt %d/%d failed: %s", attempt, _RECONNECT_ATTEMPTS, exc)
                if attempt < _RECONNECT_ATTEMPTS:
                    await asyncio.sleep(_RECONNECT_DELAY_S)
        raise EosUnreachableError(f"Could not reconnect after {_RECONNECT_ATTEMPTS} attempts")
```

**Locking order:** `_lock` (send rate-limiter) → `_connect_lock`. `_listen_loop` uses only `_connect_lock`. No deadlock risk.

#### Add `_send_subscribe()`

```python
async def _send_subscribe(self) -> None:
    packet = self._build_raw_packet("/eos/subscribe", 1)
    self._writer.write(packet)
    await self._writer.drain()
    logger.info("Sent /eos/subscribe 1")
```

**Call only from `connect()`** — after `board_state.connected = True`. Do NOT call again from `_listen_loop` to avoid duplicate subscribe packets.

#### Add `_parse_cue_text()` static helper

EOS format for active cue: `"1/5 Intro 3.00 75%"` (list/cue, label, time, percent)  
EOS format for pending cue: `"1/6 Verse 5.00"` (list/cue, label, time — no percent)

```python
@staticmethod
def _parse_cue_text(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (cue_list, cue_number, label) from EOS active/pending cue text."""
    parts = text.strip().split()
    if not parts:
        return None, None, None

    cue_part = parts[0]
    slash = cue_part.find("/")
    if slash < 0:
        return None, None, None
    cue_list = cue_part[:slash]
    cue_num  = cue_part[slash + 1:]

    if len(parts) < 2:
        return cue_list, cue_num, None

    remaining = parts[1:]
    if remaining and remaining[-1].endswith("%"):
        remaining = remaining[:-1]
    if remaining and re.fullmatch(r"\d+\.\d+", remaining[-1]):
        remaining = remaining[:-1]

    label = " ".join(remaining).strip() or None
    return cue_list, cue_num, label
```

Handles: multi-word labels, unlabeled cues, active vs pending format.

#### Add `_handle_osc_message()`

```python
def _handle_osc_message(self, msg: OscMessage) -> None:
    addr = msg.address
    params = msg.params

    if addr == "/eos/out/show/name" and params:
        self.board_state.show_name = str(params[0])
    elif addr == "/eos/out/active/cue/text" and params:
        cl, cq, label = self._parse_cue_text(str(params[0]))
        self.board_state.active_cue_list  = cl
        self.board_state.active_cue       = cq
        self.board_state.active_cue_label = label
    elif addr == "/eos/out/pending/cue/text" and params:
        cl, cq, _ = self._parse_cue_text(str(params[0]))
        self.board_state.next_cue_list = cl
        self.board_state.next_cue      = cq
    elif addr == "/eos/out/event/state" and params:
        self.board_state.mode = "Live" if params[0] == 1 else "Blind"

    self.board_state.last_updated = time.time()
```

#### Add `_listen_loop()`

```python
async def _listen_loop(self) -> None:
    logger.info("OSC receive loop started")
    while True:
        try:
            if not settings.eos_host:
                await asyncio.sleep(10)
                continue

            if not self.connected:
                await asyncio.sleep(_RECONNECT_DELAY_S)
                try:
                    await self._reconnect()
                except EosUnreachableError:
                    continue

            header = await self._reader.readexactly(4)
            length = struct.unpack(">I", header)[0]
            if length == 0:
                continue

            body = await self._reader.readexactly(length)
            try:
                msg = OscMessage(body)
                self._handle_osc_message(msg)
            except (OscParseError, Exception) as exc:
                logger.warning("OSC message error (ignored): %s", exc)
                continue

        except asyncio.IncompleteReadError:
            logger.warning("EOS connection closed (EOF). Will reconnect.")
            await self._close_writer()
        except (ConnectionError, ConnectionResetError, BrokenPipeError) as exc:
            logger.warning("EOS connection error: %s", exc)
            await self._close_writer()
        except asyncio.CancelledError:
            logger.info("OSC receive loop cancelled")
            raise
```

#### Add `start_listening()` / `stop_listening()`

```python
async def start_listening(self) -> None:
    if self._listen_task and not self._listen_task.done():
        return
    self._listen_task = asyncio.create_task(
        self._listen_loop(), name="eos-receive-loop"
    )

async def stop_listening(self) -> None:
    if self._listen_task:
        self._listen_task.cancel()
        try:
            await self._listen_task
        except asyncio.CancelledError:
            pass
        self._listen_task = None
```

---

### File 2: `backend/routes/board_state.py` (new file)

```python
from fastapi import APIRouter
import dataclasses
from pydantic import BaseModel
from typing import Optional
from eos_client import eos_client

router = APIRouter()


class BoardStateResponse(BaseModel):
    show_name:        Optional[str]
    active_cue:       Optional[str]
    active_cue_list:  Optional[str]
    active_cue_label: Optional[str]
    next_cue:         Optional[str]
    next_cue_list:    Optional[str]
    mode:             str
    connected:        bool
    last_updated:     Optional[float]


@router.get("/api/board-state", response_model=BoardStateResponse)
async def board_state() -> BoardStateResponse:
    return BoardStateResponse(**dataclasses.asdict(eos_client.board_state))
```

---

### File 3: `backend/main.py`

Add lifespan context manager and register the new router:

```python
from contextlib import asynccontextmanager
from eos_client import eos_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.eos_host:
        try:
            await eos_client.connect()
        except Exception as exc:
            logger.warning("EOS not reachable at startup: %s. Listener will retry.", exc)
    await eos_client.start_listening()
    yield
    await eos_client.stop_listening()
    await eos_client._close_writer()

app = FastAPI(title="EOS NL Bridge", version="0.2.0", lifespan=lifespan)
```

---

### File 4: `frontend/app.jsx`

Add board-state polling effect:

```jsx
useEffect(() => {
  const STALE_S = 5;
  const id = setInterval(async () => {
    try {
      const res = await fetch("/api/board-state");
      if (!res.ok) return;
      const data = await res.json();
      const now = Date.now() / 1000;
      const isStale = !data.last_updated || (now - data.last_updated) > STALE_S;
      setStatus((st) => ({
        ...st,
        showName:   data.show_name    ?? st.showName,
        cueList:    data.active_cue_list ?? "—",
        activeCue:  data.active_cue      ?? "—",
        nextCue:    data.next_cue        ?? "—",
        cueTotal:   "—",
        mode:       data.mode !== "unknown" ? data.mode : st.mode,
        connection: data.connected && !isStale ? "Online" : "Offline",
      }));
    } catch (_err) {
      setStatus((st) => ({ ...st, connection: "Offline" }));
    }
  }, 1000);
  return () => clearInterval(id);
}, []);
```

Preserve `seedChannels()` and `interpretSyntax()`.

---

### File 5: `frontend/status-bar.jsx`

Fix `Pill` tone for unknown/offline mode:

```jsx
<Pill tone={state.mode === "Live" ? "live" : state.mode === "Blind" ? "blind" : "neutral"}>
  {state.mode}
</Pill>
```

Add `dotNeutral: { background: "var(--ink-3)" }` to `sbStyles` and handle `"neutral"` tone in `Pill`.

---

## Edge Cases

| Scenario | Handling |
|---|---|
| EOS_HOST not configured | `_listen_loop` detects empty host, sleeps 10s, retries — never spins tight |
| EOS offline at startup | `connect()` fails gracefully; listener retries every 1s |
| EOS disconnect mid-session | `IncompleteReadError` → `_close_writer()` sets `connected=False` → frontend shows "Offline" within 1s |
| Concurrent reconnect (send + listen) | `_connect_lock` with `if self.connected: return` guard prevents double-connect |
| Malformed OSC frame | `(OscParseError, Exception)` caught broadly, loop continues |
| Zero-length OSC frame | `if length == 0: continue` before `readexactly` |
| Fetch fails (backend down) | Sets `connection: "Offline"`, preserves displayed cue data |

---

## Tests

### `backend/requirements-dev.txt`

```
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27.0
```

### `backend/tests/test_eos_client.py`

Unit tests (no live EOS required):
- `_parse_cue_text` — 6 parametrized cases covering multi-word labels, decimal cues, unlabeled, malformed, empty
- `_build_raw_packet` — verifies 4-byte length prefix, address in body, int arg
- `_handle_osc_message` — verifies `BoardState` updates for all 4 message types, unknown address, empty params
- `BoardState` defaults

### `backend/tests/test_board_state_route.py`

Route tests (no live EOS required):
- `GET /api/board-state` returns 200
- Offline state: `connected=false`, all fields null, `mode="unknown"`
- Online state: all fields populated correctly, `last_updated` value preserved

### Running

```powershell
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## What is NOT in Phase 2

- **Per-channel intensity levels** — requires full patch enumeration. Channel strip remains seeded.
- **Total cue count** — `cueTotal` shows `"—"`.
- **WebSocket** — HTTP polling at 1s is sufficient for EOS's ~1Hz update rate.

---

## Implementation Order

1. `backend/eos_client.py`
2. `backend/routes/board_state.py`
3. `backend/main.py`
4. `backend/requirements-dev.txt` + `backend/tests/__init__.py`
5. `backend/tests/test_eos_client.py`
6. `backend/tests/test_board_state_route.py`
7. `frontend/app.jsx`
8. `frontend/status-bar.jsx`

---

## Verification

```powershell
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

Manual: start server, check logs for "OSC receive loop started", fire cue on console, verify status bar updates within ~1 second.
