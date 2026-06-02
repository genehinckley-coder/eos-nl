# Plan: EOS ION Natural Language Interface — Phase 1 Backend Bridge

## Context

A fine-tuned Ollama model (`eos-nl:v4`, running in WSL) translates natural language lighting commands into ETC EOS console command-line syntax. A web frontend prototype already exists (pure React/CDN, no backend). This plan wires them together: a Python FastAPI backend accepts natural language from the frontend, calls the model, sanitizes the output, and dispatches the resulting EOS command string to the console over OSC. Phase 1 is command dispatch only — no live status subscription.

**Decisions locked in:**
- Transport: **TCP port 3032**, OSC 1.0 (4-byte big-endian length prefix) — ETC preferred, reliable delivery
- Python runs on **Windows host** — direct LAN access to EOS, Ollama accessible via `localhost:11434` (WSL2 auto-forwards)
- Model prompt: **bare natural-language text** — `eos-nl:v4` was fine-tuned to respond without a system prompt
- **Destructive commands blocked** at the backend (Record, Delete, Label Cue) with a config override flag

---

## Architecture

```
Browser → bridge.js → POST /api/translate → FastAPI
                                              ├─ ollama_client → Ollama localhost:11434 (WSL)
                                              ├─ sanitizer → validate + clean output
                                              └─ eos_client → TCP OSC → EOS Console :3032
```

FastAPI also serves the static frontend files (same origin, no CORS needed).

---

## File Structure

```
d:\code\eos-nl\
├── backend\
│   ├── main.py               # FastAPI app, mounts static files, includes routers
│   ├── config.py             # pydantic-settings: EOS_HOST, EOS_PORT, OLLAMA_URL, MODEL_NAME, BLOCK_DESTRUCTIVE
│   ├── ollama_client.py      # async httpx POST to /api/generate, stream=false
│   ├── eos_client.py         # asyncio TCP OSC client: persistent connection, 50ms rate limiter, reconnect
│   ├── sanitizer.py          # strip markdown, take first line, ensure termination, destructive blocklist
│   ├── routes\
│   │   ├── __init__.py
│   │   ├── translate.py      # POST /api/translate
│   │   └── status.py         # GET /api/status
│   └── requirements.txt
├── frontend\                  # Working copy of the design prototype
│   ├── index.html             # +1 line: <script src="bridge.js"> as final script tag
│   ├── bridge.js              # NEW: overrides window.translateCommand → fetch /api/translate
│   ├── translator.jsx         # +1 line: window._eosNlFallback = fallbackTranslate
│   └── [all other .jsx files unchanged]
└── .env.example              # EOS_HOST=, EOS_PORT=3032, OLLAMA_URL=http://localhost:11434, MODEL_NAME=eos-nl:v4
```

The originals in `EOS ION Natural Language Interface\design_handoff_eos_ion_nl\` are **preserved untouched** as the design reference. `frontend\` is the working copy.

---

## API Contracts

### POST /api/translate
Request: `{ "input": "bring channel 5 to full" }`

Response (success, sent):
```json
{ "ok": true, "syntax": "Chan 5 At Full Enter", "source": "eos-nl:v4", "sent": true, "error": null }
```

Response (model failure):
```json
{ "ok": false, "syntax": null, "source": "eos-nl:v4", "sent": false, "error": "?? could not parse" }
```

Response (OSC unreachable):
```json
{ "ok": true, "syntax": "Chan 5 At Full Enter", "source": "eos-nl:v4", "sent": false, "error": "EOS unreachable — translated but not sent" }
```

Response (destructive blocked):
```json
{ "ok": false, "syntax": "Record Cue 1 Enter", "source": "eos-nl:v4", "sent": false, "error": "destructive command blocked in Phase 1" }
```

### GET /api/status
```json
{ "ollama": "ok", "eos": "ok", "eos_host": "192.168.x.x", "model": "eos-nl:v4" }
```

The response shape `{ ok, syntax, source, error }` matches exactly what `app.jsx` expects from `window.translateCommand`. The `sent` field is bonus — the frontend ignores unknown fields.

---

## Key Implementation Details

### `config.py`
Use `pydantic-settings` to load from `.env`. Fields with defaults: `EOS_PORT=3032`, `OLLAMA_URL=http://localhost:11434`, `MODEL_NAME=eos-nl:v4`, `BLOCK_DESTRUCTIVE=True`, `SERVER_HOST=127.0.0.1`, `SERVER_PORT=8080`. `EOS_HOST` defaults to `""` — server starts without it but logs a warning; sends will return `sent: false`.

### `ollama_client.py`
```python
async def translate(text: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": settings.model_name, "prompt": text, "stream": False},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()["response"].strip()
```
Timeout at 30s (model cold-start on first call). Raise on HTTP error; caller handles.

### `sanitizer.py`
In order:
1. Strip leading/trailing whitespace
2. Strip markdown code fences (` ```...``` `) and surrounding quotes
3. Take first non-empty line only (model should output one line)
4. If result starts with `??` → raise `TranslationError` with the reason text
5. If result is empty → raise `TranslationError("empty response")`
6. If `settings.block_destructive` is True and result matches `^(record|delete|update|label cue)\b` (case-insensitive) → raise `DestructiveCommandError` — covers `Record Only` variants too since they start with `Record`
7. Normalize `At` → `@` (e.g. `Chan 5 At Full Enter` → `Chan 5 @ Full Enter`) so the frontend `interpretSyntax` regexes match — EOS accepts both forms
8. If result does not end with `Enter` → append ` Enter` (use `Enter`, not `#`, for frontend simulation compatibility with `interpretSyntax`)
9. Return sanitized string

### `eos_client.py`
- Singleton `EosClient` with `asyncio` reader/writer pair
- `connect()`: `asyncio.open_connection(host, port)` with 5s timeout
- `async def send_cmd(cmd: str)`: build OSC packet, prepend 4-byte big-endian length, call `writer.write(packet)` then `await writer.drain()`
- OSC packet: use `python-osc`'s `OscMessageBuilder` for `/eos/cmd` with one string arg
- Rate limiter: track `_last_sent` timestamp; `await asyncio.sleep(remainder)` if `< 0.05s` since last send
- Reconnect: on `ConnectionError`, `BrokenPipeError`, or `ConnectionResetError` → **first** call `writer.close(); await writer.wait_closed()` to release the socket, then attempt `connect()` up to 3 times with 1s backoff; after 3 failures, raise `EosUnreachableError`
- Health check: `async def ping()` sends `/eos/ping` (no response listener in Phase 1 — fire-and-forget)

### `routes/translate.py`
```python
@router.post("/api/translate")
async def translate(body: TranslateRequest) -> TranslateResponse:
    try:
        raw = await ollama_client.translate(body.input)
        syntax = sanitizer.clean(raw)  # raises on bad output or destructive
        sent = await eos_client.send_cmd(syntax)  # returns True or raises
        return TranslateResponse(ok=True, syntax=syntax, source=settings.model_name, sent=True)
    except TranslationError as e:
        return TranslateResponse(ok=False, error=str(e), source=settings.model_name, sent=False)
    except DestructiveCommandError as e:
        return TranslateResponse(ok=False, syntax=e.syntax, error=str(e), source=settings.model_name, sent=False)
    except EosUnreachableError:
        return TranslateResponse(ok=True, syntax=syntax, source=settings.model_name, sent=False,
                                 error="EOS unreachable — translated but not sent")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### `bridge.js`
Plain JavaScript (not Babel). Loaded as the last `<script>` tag in `index.html`.

**Critical timing:** `<script type="text/babel">` tags are processed asynchronously by Babel Standalone. A plain `<script>` executing synchronously at parse time runs *before* Babel finishes — `window.translateCommand` does not exist yet and the override fires into a void. The fix: defer the override until the `window load` event, which fires after all deferred/async scripts (including Babel output) have completed.

```js
window.addEventListener("load", function () {
  async function callBackend(input) {
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return res.json();
  }

  window.translateCommand = async function (input) {
    const trimmed = (input || "").trim();
    if (!trimmed) return { syntax: "", ok: false, error: "empty" };
    try {
      return await callBackend(trimmed);
    } catch (err) {
      console.warn("[bridge] backend unreachable:", err);
      if (typeof window._eosNlFallback === "function") {
        const fb = window._eosNlFallback(trimmed);
        if (fb.startsWith("??")) {
          return { syntax: fb, ok: false, error: fb.slice(2).trim(), source: "fallback" };
        }
        return { syntax: fb, ok: true, source: "fallback" };
      }
      return { ok: false, error: "backend unreachable", source: "bridge" };
    }
  };
});
```

### `translator.jsx` — single-line change
At the very end of the file, after `window.translateCommand = ...` is defined:
```js
window._eosNlFallback = fallbackTranslate;
```
This exposes the existing regex fallback engine to `bridge.js` without modifying any logic.

### `index.html` — single-line change
Add as the **last** `<script>` tag (after all `type="text/babel"` scripts):
```html
<script src="bridge.js"></script>
```

### `main.py`
```python
app = FastAPI()
app.include_router(translate_router)
app.include_router(status_router)
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
```
Run: `uvicorn main:app --host {settings.server_host} --port {settings.server_port} --reload`

Or via a startup helper that reads config: `python -m uvicorn main:app --reload` with host/port passed from `config.py` defaults.

---

### `/api/status` implementation spec

`GET /api/status` performs two health checks with short timeouts and returns:
```json
{ "ollama": "ok", "eos": "ok", "eos_host": "192.168.x.x", "model": "eos-nl:v4" }
```

- **Ollama check:** `GET {ollama_url}/api/tags` with 3s timeout. Returns `"ok"` on HTTP 200, `"error"` otherwise.
- **EOS check:** `asyncio.open_connection(eos_host, eos_port)` with 2s timeout; close immediately after. Returns `"ok"` on success, `"error"` on timeout/refusal. If `EOS_HOST` is not configured, returns `"unconfigured"`.
- If `EOS_HOST` is not set, server logs a warning at startup but does **not** refuse to start — translation will still work, `sent` will be `false` until the host is configured.

---

## EOS Console Prerequisites

Before the backend can connect, an operator must:
1. `Setup → System → Show Control → OSC → Enable OSC RX`
2. Confirm `OSC TCP mode = OSC 1.0` (default, 4-byte length prefix)
3. Note the console's IP address and set it in `.env` as `EOS_HOST`

---

## Dependencies

`backend/requirements.txt`:
```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0
python-osc>=1.8.3
pydantic-settings>=2.2.0
python-dotenv>=1.0.0
```

`.env.example` (all configurable vars):
```
# Required for OSC — server starts without it but sends will fail
EOS_HOST=

# Optional with defaults
EOS_PORT=3032
OLLAMA_URL=http://localhost:11434
MODEL_NAME=eos-nl:v4
BLOCK_DESTRUCTIVE=true

# Web server bind address and port
SERVER_HOST=127.0.0.1
SERVER_PORT=8080
```

---

## Known Risks

| Risk | Mitigation |
|------|-----------|
| `eos-nl:v4` output style unknown until tested | Test model manually before wiring to console; sanitizer normalizes `At`→`@` and appends `Enter` if missing |
| Model outputs `At` style; `interpretSyntax` regexes only match `@` | Sanitizer normalizes `At` → `@` before returning syntax to frontend |
| OSC TCP connection drops mid-session | Reconnect loop: `writer.close() + await writer.wait_closed()` before each retry; catches `ConnectionError`, `BrokenPipeError`, `ConnectionResetError` |
| EOS console IP not known at dev time | `EOS_HOST` optional — server starts without it (warning logged); `sent: false` until configured |
| Destructive command hallucination | Blocklist covers `Record`, `Delete`, `Update`, `Label Cue`; `BLOCK_DESTRUCTIVE=true` default |
| Windows Defender blocks outbound TCP to console | Document firewall step in README; first run will prompt |
| bridge.js overrides `window.translateCommand` before Babel finishes | Override wrapped in `window.addEventListener("load", ...)` — fires after all async Babel transpilation completes |
| asyncio `send` must be awaited; writer drain required | `eos_client.send_cmd()` is `async def` and calls `await writer.drain()` after every write |

---

## Implementation Steps

### Step 0 — Project scaffold
1. Create `d:\code\eos-nl\docs\` and copy this plan file there as `plan-phase1.md` for project reference
2. Create `d:\code\eos-nl\backend\` and `d:\code\eos-nl\backend\routes\`
3. Copy `EOS ION Natural Language Interface\design_handoff_eos_ion_nl\` → `d:\code\eos-nl\frontend\`

## Verification Steps

1. Copy `EOS ION Natural Language Interface\design_handoff_eos_ion_nl\` → `frontend\`
2. Set up `.env` with `EOS_HOST=<console-ip>`
3. `pip install -r backend/requirements.txt`
4. `uvicorn main:app --reload` from `backend\` (reads `SERVER_HOST` and `SERVER_PORT` from `.env`, defaults to `127.0.0.1:8080`)
5. Verify `GET http://127.0.0.1:8080/api/status` returns `ollama: "ok"` and `eos: "ok"`
6. Open `http://127.0.0.1:8080` in browser — frontend loads
7. Test with "channel 1 at full" → transcript shows translated syntax, EOS channel responds
8. Test with "record cue 1" → transcript shows "destructive command blocked" error
9. Test with Ollama stopped → bridge.js falls back to regex, transcript shows `source: "fallback"`
10. Test with EOS console unreachable → `sent: false` error in transcript, syntax still visible

---

## Out of Scope for Phase 1

- Live status feed from EOS (`/eos/out/*` subscription) — status bar remains simulated
- WebSocket for real-time push to frontend
- Voice input
- Confirmation step before executing commands
- Multi-console support
- Persistence (localStorage transcript)
