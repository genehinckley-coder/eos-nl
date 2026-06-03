# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the backend

The server must be started from the `backend/` directory so relative paths resolve correctly (`../frontend` for static files, `.env` for config):

```powershell
cd backend
pip install -r requirements.txt
python main.py
# Serves at http://127.0.0.1:8080 by default
```

`uvicorn --reload` is enabled via `python main.py`. Changing `.env` requires a full server restart — reload only triggers on Python file changes.

Copy `.env.example` → `backend/.env` and set `EOS_HOST` before the first run.

## Running the tests

```powershell
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

All tests pass without a live EOS connection or Ollama instance.

## Architecture

```
Browser → frontend/bridge.js → POST /api/translate → FastAPI (backend/)
                                                        ├─ ollama_client.py  → Ollama :11434 (WSL)
                                                        ├─ sanitizer.py      → clean + validate
                                                        └─ eos_client.py     → OSC TCP → EOS :3032
                                                                               ├─ send_cmd()   (outbound)
                                                                               └─ _listen_loop() (inbound OSC push)

Browser ← GET /api/board-state (1s poll) ← BoardState dataclass ← _listen_loop()
```

**Backend** (`backend/`) is a FastAPI app with three routes and a module-level `EosClient` singleton. All config comes from `backend/.env` via pydantic-settings (`config.py`).

**Frontend** (`frontend/`) is the working copy of the React CDN prototype (no build step — Babel Standalone transpiles JSX at runtime in the browser). The original unmodified design files live in `EOS ION Natural Language Interface/design_handoff_eos_ion_nl/` and are the visual reference; don't edit them.

## Key design constraints

**bridge.js timing:** `frontend/bridge.js` is a plain `<script>` that runs synchronously before Babel Standalone finishes processing the `.jsx` files. It sets `window.__bridgeTranslate` immediately. `translator.jsx`'s `window.translateCommand` checks for `window.__bridgeTranslate` at *call time* (not setup time). Do not attempt to override `window.translateCommand` directly from `bridge.js` — Babel will overwrite it after bridge.js runs.

**OSC packet framing:** EOS uses OSC 1.0 over TCP — every packet needs a 4-byte big-endian length prefix before the raw OSC bytes. `eos_client._build_raw_packet()` builds framed packets for any OSC address. `_build_packet(cmd)` is a thin wrapper that calls `_build_raw_packet("/eos/cmd", cmd)`.

**Command termination:** EOS only executes commands that end with `Enter` or `#`. The sanitizer (`sanitizer.clean()`) appends ` Enter` if neither is present. It also normalizes the EOS keyword `At` → `@` because the frontend's `interpretSyntax()` regexes only match the `@` form.

**Destructive command block:** `sanitizer.clean()` raises `DestructiveCommandError` for commands matching `^(record|delete|update|label\s+cue)\b` when `BLOCK_DESTRUCTIVE=true` (default). The translate route returns `ok=false` for these so the frontend shows "rejected."

**`ok` field semantics:** The `/api/translate` response sets `ok=false` for any failure — translation error, sanitization error, destructive block, or EOS unreachable. The frontend shows "executed" only on `ok=true`. `sent=false` with `ok=true` should not happen; if EOS is unreachable, `ok` is `false`.

**EOS OSC subscribe:** On connect, `eos_client` sends an OSC message to address `/eos/subscribe` with integer argument `1`. EOS then pushes state changes as framed OSC packets on the same TCP connection:

| OSC address | Payload | Triggers |
|---|---|---|
| `/eos/out/show/name` | string | on show load |
| `/eos/out/active/cue/text` | `"list/cue [label] time [pct%]"` | ~1/sec |
| `/eos/out/pending/cue/text` | `"list/cue [label] time"` | on change |
| `/eos/out/event/state` | int: `1`=Live, `0`=Blind | on change |

`_listen_loop()` runs as a background `asyncio.Task` (started in the FastAPI lifespan) and updates `eos_client.board_state` (a `BoardState` dataclass) via `dataclasses.replace()` atomic assignments. The `/api/board-state` route serves the current snapshot to the frontend.

**BoardState fields:**
- `connected: bool` — set `True` only after `/eos/subscribe` succeeds; set `False` by `_close_writer()`
- `mode: str` — `"Live"` | `"Blind"` | `"unknown"` — only `0` and `1` are mapped; any other value stays `"unknown"`
- `last_updated: Optional[float]` — `time.time()` wall-clock, compared to `Date.now()/1000` in the frontend for staleness detection

**Locking:** `_lock` (asyncio.Lock) rate-limits outbound sends (50ms minimum between commands). `_connect_lock` prevents concurrent reconnect attempts from `send_cmd` and `_listen_loop`. `_listen_loop` never acquires `_lock` — reads and writes use independent asyncio stream buffers, so no deadlock is possible.

**Frontend polling:** `app.jsx` calls `poll()` immediately on mount, then self-schedules via `setTimeout` after each completion to prevent overlapping in-flight requests. An `AbortController` cancels any in-flight fetch on unmount. Two separate signals drive the UI:
- **Online/Offline pill** — driven by `data.connected` alone.
- **Cue fields** (`activeCue`, `nextCue`, `cueList`) — updated whenever `data.connected` is true; `??` fallback preserves the last-displayed value when the backend field is null. When disconnected, all cue fields are left as-is.

**Status cache:** On every connected poll response, non-null display values (showName, cueList, activeCue, nextCue, mode) are merged into `localStorage` under `eos-status-v1` with a 30-minute TTL. On page load, `useState` initialises from this cache so the status bar shows last-known values immediately rather than `"—"`. This is important because `/eos/out/event/state` and `/eos/out/show/name` are only pushed on change — not on subscribe — so without caching they would show `"unknown"` / default until the operator changes console state.

**`interpretSyntax()` and optimistic updates:** `app.jsx` parses sent EOS syntax locally to update the status bar immediately (before the next poll tick). The 1-second poll then overwrites with ground-truth data from EOS.

## Configuration (`backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `EOS_HOST` | `127.0.0.1` | IP of EOS console; server warns and OSC sends fail if empty |
| `EOS_PORT` | `3032` | OSC TCP port |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama runs in WSL; localhost works via WSL2 port forwarding |
| `MODEL_NAME` | `eos-nl:v4` | Fine-tuned model — bare natural language in, EOS syntax out, no system prompt needed |
| `BLOCK_DESTRUCTIVE` | `true` | Set `false` to allow Record/Delete/Update through |
| `SERVER_HOST` | `127.0.0.1` | |
| `SERVER_PORT` | `8080` | |

## API

`POST /api/translate` — main endpoint. Accepts `{"input": "natural language"}`, runs Ollama → sanitizer → OSC dispatch, returns `{ok, syntax, source, sent, error}`.

`GET /api/status` — health check. Hits `GET /api/tags` on Ollama and attempts a TCP connect to EOS. Returns `{ollama, eos, eos_host, model}`.

`GET /api/board-state` — live EOS board state. Returns the current `BoardState` snapshot: `{connected, show_name, active_cue, active_cue_list, active_cue_label, next_cue, next_cue_list, mode, last_updated}`. Polled by the frontend every 1 second.

## EOS console prerequisites

On the EOS console: `Setup → System → Show Control → OSC → enable OSC RX`. Confirm `OSC TCP mode = OSC 1.0` (default). EOS must be reachable at `EOS_HOST:EOS_PORT`.
