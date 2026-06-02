# Handoff: EOS ION Natural Language Interface

## Overview
A single-page web application that lets a lighting designer or programmer drive an
ETC EOS ION lighting console using natural-language commands. The user types something
conversational ("bring channels 1 through 10 to full"), the system translates it to
the console's native syntax (`Chan 1 Thru 10 @ Full Enter`), executes it against the
console, and shows the natural utterance + translated syntax + execution result in a
scrolling transcript. The app shows live console status (active cue, GM, channel
intensities, mode, connection) along the top.

## About the Design Files
The files in this bundle are **design references created in HTML** — interactive
prototypes that demonstrate the intended look, layout, and behavior of the app.
They are **not** production code to ship as-is.

Your task is to **recreate these designs in the target codebase's existing
environment** (React/Vue/SwiftUI/native/etc.) using its established patterns,
component library, design tokens, and conventions. If no environment exists yet,
pick the most appropriate framework for the project — a React + TypeScript SPA
with a small backend (or direct EOSnet OSC bridge) is a reasonable default — and
implement the designs there.

The HTML prototype uses inline React via Babel (`<script type="text/babel">`),
inline `style` objects, and CSS custom properties. Treat that structure as a
visual reference — translate to your codebase's idioms (CSS modules, Tailwind,
styled-components, design-system primitives, etc.).

## Fidelity
**High-fidelity.** The mockup represents the intended final look — colors,
typography, spacing, and interaction states are deliberate and should be
matched closely. Recreate pixel-perfectly using the target codebase's existing
component primitives (Button, Input, Pill, etc.) wherever they exist; only build
new primitives where the design demands something the kit doesn't have.

## Visual References
PNG screenshots of the running prototype live in `screenshots/`:

| File | Shows |
|---|---|
| `screenshots/01-default.png` | Initial state — seeded transcript, live status bar, full composer |
| `screenshots/02-with-commands.png` | Composer populated from a suggestion chip |
| `screenshots/03-tweaks-open.png` | Tweaks panel open (design-time only — strip in production) |
| `screenshots/04-error-state.png` | Command in flight, showing pending/translating UI |

Use these to sanity-check colors, spacing, and component layout against your
implementation.

## Real-World Integration Notes
The prototype simulates the console — translated commands mutate local React
state. In production you will need:

- **Transport to EOS:** ETC consoles speak OSC (Open Sound Control). The standard
  pattern is to open a UDP/TCP OSC connection to the console (default port 3032
  for OSC over TCP-SLIP, 3037 for UDP) and send `/eos/cmd` or `/eos/key/*`
  messages. For a web app you will need a small backend bridge (Node.js with the
  `osc` package is straightforward) since browsers cannot open raw UDP sockets.
- **Status feed:** EOS publishes show data over OSC at `/eos/out/*`. Subscribe
  to active-cue, pending-cue, GM, and channel-output messages to drive the
  live status bar instead of the simulated state in the prototype.
- **Translation backend:** The prototype calls `window.claude.complete` with
  a system prompt that maps natural language to EOS keywords. In production
  this should be a server-side call to your LLM of choice (Anthropic Claude,
  OpenAI, etc.) so the API key isn't exposed. The `translator.jsx` system
  prompt is a good starting point and should be preserved verbatim. Always
  keep the deterministic regex fallback for when the LLM is unavailable or
  too slow — lighting commands need sub-second response.
- **Confirmation step (recommended):** Real shows are unforgiving. Consider
  adding an opt-in "confirm before executing" mode that shows the translated
  syntax for review before sending to the console, especially for destructive
  ops (`Record`, `Delete`, `Update`, `Out`).

---

## Screens / Views

The app is a **single screen** with three stacked regions filling the viewport:

```
┌─────────────────────────────────────────────────────────────┐
│  STATUS BAR  (fixed height ~64px)                           │
│  brand · cue list · active · next · GM · channel strip · pills · clock │
├─────────────────────────────────────────────────────────────┤
│  TRANSCRIPT  (flex-grow, scrolling)                         │
│    transcript header                                        │
│    ┌─ entry ─────────────────────────────────────────────┐  │
│    │ HH:MM:SS  › natural language input                  │  │
│    │           → translated EOS syntax (mono, bordered)  │  │
│    │           ● status   result   via source            │  │
│    └─────────────────────────────────────────────────────┘  │
│    ...                                                      │
├─────────────────────────────────────────────────────────────┤
│  COMPOSER  (fixed height ~140px)                            │
│  TRY: [chip] [chip] [chip] ...                              │
│  NL ›  [text input]                              [Execute]  │
│  hint row                                                   │
└─────────────────────────────────────────────────────────────┘
```

Body has `overflow: hidden`. Only the transcript scrolls.

### 1. Status Bar (top)
**Purpose:** at-a-glance read of console state.

**Layout:** CSS grid, three columns: `auto | 1fr | auto`. Bordered cells
separated by 1px lines in `--line` color. Height drives off content (~64px).

**Cells, left → right:**
- **Brand cell** — 28×28px monospace `NL` mark in a bordered tile, plus a
  two-line label: small uppercase mono `EOS ION · Natural Language` over the
  show name in sans-serif. Truncates with ellipsis at narrow widths.
- **Metric: Cue List** — label "CUE LIST", value (mono), subscript total e.g. `47 /120`.
- **Metric: Active** — label "ACTIVE", value (mono, accent color).
- **Metric: Next** — label "NEXT", value (mono).
- **Metric: GM** — label "GM", value (mono), subscript `%`.
- **Channel strip** — flexible-width row of vertical bars, one per channel,
  each 16px wide × 32px tall with an 8px-wide intensity bar inside. Bar height
  scales to channel level (0–100). Color shifts with intensity:
  `oklch(0.55 + level/100 * 0.28, hot ? 0.13 : 0.08, 75)` — dim warm-white for
  cool levels, brighter amber for hot channels. Uses a `ResizeObserver` to drop
  bars that don't fit and shows a `+N` overflow count in muted mono. Off
  channels render as a 2px-tall bar in `--bg-3`.
- **Right cell** — two pills (`Mode`, `Connection`) and a live HH:MM:SS clock.
  - Pills: 1px border, full pill radius (`999px`), 5×10 padding, mono uppercase
    label with a 7px leading dot. Dot colors:
    - Live (green): `oklch(0.78 0.13 150)` with a 3px alpha-glow ring.
    - Blind (cool blue): `oklch(0.78 0.06 230)`.
    - Alert (red): `oklch(0.7 0.18 25)`.

### 2. Transcript (middle)
**Purpose:** scrolling log of every interaction.

**Header (40px, sticky to top of region):** small uppercase mono label
"COMMAND TRANSCRIPT · N" on the left, "Clear" mini-button on the right
(transparent background, 1px `--line` border, hovers to accent).

**Body:** vertical list, each entry separated by a 1px dashed `--line-soft`
divider, 12px vertical padding. Auto-scrolls to bottom on new entry.

**Each entry** is a 2-column grid: 60px timestamp gutter | 1fr body.
- **Timestamp** (60px gutter) — mono 11px, muted, `HH:MM:SS`.
- **Body** is a 6px-gap stack of three rows:
  1. **Natural utterance** — sans-serif 14.5px in `--ink-0`, prefixed by an
     accent-colored `›` glyph.
  2. **Translated syntax** — prefixed by a muted `→`. Then a mono 13.5px code
     block in `--bg-2` with a 1px `--line` border, 5×10 padding, that contains
     the full translated EOS syntax line. While translating, shows
     `translating…` with an animated dot count.
  3. **Meta line** — small mono 10.5px row indented 22px, containing:
     - status indicator: `● executed` (green), `● pending` (amber), or
       `● rejected` (red);
     - result text from the local interpreter (e.g. `10 channels @ 100`,
       `cue 47 active`, `blackout`);
     - source attribution (`via claude` or `via fallback`).

**Error variant:** the syntax code block uses a dashed red border, no fill,
red text. The meta line shows `● rejected` and the error reason as the syntax
content.

### 3. Composer (bottom)
**Purpose:** enter a natural-language command.

**Layout:** three stacked rows in a `--bg-1` panel with a 1px top border:

1. **Suggestions** — 10px top padding, 8px gap, flex-wrap. Starts with the
   muted mono `TRY:` label. Each chip is 12px sans, `--bg-2` background, 1px
   `--line` border, 5×10 padding, 2px radius. Hover bumps text to accent and
   border to accent line. Click pre-fills the input.

   Default chip set: `Bring channels 1 through 10 to full`, `Channel 5 at 75`,
   `Go to cue 12`, `Next cue`, `Record cue 5`, `Blackout`, `Group 3 at half`,
   `Channels 1 plus 5 plus 9 to full`.

2. **Input row** — three-column grid `auto | 1fr | auto`, 12px gap, 12×20 padding:
   - **Prompt** — mono 13px accent: `NL ›`.
   - **Input** — 100% width, `--bg-2` background, 1px `--line` border (separate
     longhand props — do not combine with shorthand), 12×14 padding, 15px
     sans, `--ink-0` text. Focus state lifts the border to `--amber-line`.
     Placeholder: `Speak naturally — e.g. "bring up channels 1 through 10 to full"`.
   - **Execute button** — accent fill, dark text (`#1b1408`), mono 11.5px
     uppercase letter-spaced label, 0×18 padding. Right-side mini-kbd hint
     (`↵`) in a translucent inset chip. Disabled state: `--bg-3` fill,
     `--line` border, `--ink-3` text.

3. **Hint row** — small mono 10px uppercase, 0×20 padding, 10px bottom padding.
   Left: `NL → EOS Syntax · ready` (or `· translating…`). Right:
   `↑/↓ recall · ⏎ send · Shift+⏎ newline`.

---

## Interactions & Behavior

### Submit
- `Enter` on the input or click `Execute` submits.
- Shift+Enter inserts a newline (input is single-line in the prototype but the
  handler is set up — switch to a textarea if you want multi-line).
- On submit:
  1. Add a transcript entry with `status: pending` and an animated `translating…`
     placeholder for the syntax.
  2. Call the translator (LLM with regex fallback).
  3. On success, replace the entry's syntax with the translated line and set
     `status: ok`. Run the syntax through the local interpreter to update the
     simulated console state and store its result string on the entry.
  4. On failure, set `status: error`, replace syntax with the error reason,
     leave console state unchanged.

### Recall
- `↑` walks back through prior natural utterances; `↓` walks forward. The
  pre-recall input value is snapshotted so `↓` past the newest entry restores
  the user's typed-but-unsent text.
- Pressing `Enter` resets the recall index.

### Auto-scroll
- The transcript scrolls to the bottom whenever entries change.

### Auto-focus
- The input is focused on mount.

### Animations
- `translating…` dot animation: 1 → 2 → 3 dots on a 350ms interval.
- Channel-strip bar height & color: 220ms ease transitions on both `height`
  and `background` so updates ripple in smoothly.
- Live pill dot uses a static 3px alpha glow (no animation in current spec).
- Clock updates once per second.

### State management (target codebase)
You will want hooks/services for:
- `useStatus()` — { showName, cueList, cueTotal, activeCue, nextCue, gm, mode,
  connection, clock, channels[] }. In production, populated by an OSC
  subscription, not seeded locally.
- `useTranscript()` — append-only entry list with `{ id, ts, natural, syntax,
  status: 'pending'|'ok'|'error', source, result }`.
- `useTranslator()` — wraps the LLM call + fallback. Returns
  `{ syntax, ok, source, error? }`.
- `useEosBridge()` — sends translated syntax to the console and listens for
  state updates.

---

## Design Tokens

All declared as CSS custom properties on `:root` in `index.html`. Translate
to your design-token system.

### Colors
| Token | Value | Use |
|---|---|---|
| `--bg-0` | `#0b0c0e` | App background |
| `--bg-1` | `#111316` | Status bar, composer panel |
| `--bg-2` | `#16191d` | Code blocks, input, chips |
| `--bg-3` | `#1c2026` | Disabled/empty channel bars, brand mark |
| `--line` | `#232830` | All 1px dividers and borders |
| `--line-soft` | `#1a1e23` | Dashed transcript dividers |
| `--ink-0` | `#f1efeb` | Primary text |
| `--ink-1` | `#cfcbc3` | Secondary text |
| `--ink-2` | `#a8a49a` | Muted labels |
| `--ink-3` | `#9a958b` | Timestamps, hint row, "TRY:" label |
| `--amber` | `oklch(0.78 0.13 75)` | Primary accent (warm stage-incandescent) |
| `--amber-soft` | `oklch(0.78 0.13 75 / 0.18)` | Selection bg |
| `--amber-line` | `oklch(0.78 0.13 75 / 0.35)` | Hover/focus borders |
| `--cool` | `oklch(0.78 0.06 230)` | Blind-mode pill dot |
| `--green` | `oklch(0.78 0.13 150)` | Live/executed status |
| `--red` | `oklch(0.7 0.18 25)` | Alert/rejected status |
| `--magenta` | `oklch(0.72 0.18 340)` | (reserved) |

Accent presets (in `app.jsx`, exposed via Tweaks):
- `amber` — `oklch(0.78 0.13 75)` *(default)*
- `rose` — `oklch(0.74 0.15 18)`
- `cyan` — `oklch(0.78 0.10 215)`
- `lime` — `oklch(0.83 0.15 130)`
- `violet` — `oklch(0.74 0.13 295)`

In production you may want to expose accent as a user setting; it has no
functional meaning, just visual preference.

### Typography
- **Sans** (`--sans`): `Inter, system-ui, -apple-system, "Segoe UI", sans-serif`.
  Used for natural-language text, show name, button labels, chips.
- **Mono** (`--mono`): `"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo,
  monospace`. Used for translated syntax, timestamps, metric values, all small
  uppercase labels, hint row.
- Sizes used: 9.5, 10, 10.5, 11, 11.5, 12, 13, 13.5, 14, 14.5, 15.
- Weights: 400, 500, 600, 700.
- Letter-spacing on small uppercase labels: 1.1–1.6 (0.0688–0.1em-ish at 10px).

### Spacing scale
Loosely 2/4/6/8/10/12/14/16/18/20/22/24 px. Use the codebase's existing
spacing scale and round to nearest.

### Borders / radii
- 1px lines everywhere; never thicker.
- Radii: `2px` for chips and brand mark; `4px` for cards (rare); `999px` for
  pills. No large rounded corners.

### Shadows
None. The design relies entirely on hairline borders and value contrast.
Avoid the urge to add glassmorphism or drop-shadows.

---

## Translator Prompt
Reuse the system prompt in `translator.jsx` verbatim. It documents the EOS
keyword vocabulary, formatting rules, and ambiguity handling (the model
returns `?? <reason>` for non-lighting input, which the UI surfaces as a
rejected entry). When the LLM is unavailable or returns an ambiguity marker,
the regex fallback in the same file handles common phrasings deterministically.

The fallback recognizes:
- Blackout: `blackout`, `kill all`, `all out`, `lights out` → `Out Enter`
- Cue movement: `go`, `next`, `back`, `previous` → `Go Enter` / `Back Enter`
- `go to cue N` → `Go To Cue N Enter`
- `record cue N` → `Record Cue N Enter`
- `update` → `Update Enter`
- `group N` → `Group N Enter`
- `sub N at V` → `Sub N @ V Enter`
- Channel ranges: `channels A through B at V` → `Chan A Thru B @ V Enter`
- Channel unions: `channels 1 plus 5 plus 9 at V` → `Chan 1 + 5 + 9 @ V Enter`
- Single channel: `channel N at V` → `Chan N @ V Enter`
- `bring up N to V` → `Chan N @ V Enter`

`V` accepts numbers, `full`, `out`, `half`, and small number-words.

---

## Local Interpreter
`app.jsx` contains an `interpretSyntax` function that parses the translated
EOS syntax and returns `{ result, mutator }` — `result` is a short
human-readable confirmation shown in the transcript meta line, and `mutator`
is a state-update function applied to the simulated console state. Replace
this with calls to your real OSC bridge in production. Keep the result-string
generation, though — it's nice UX to echo back what the console did.

---

## Files in This Bundle
- `README.md` — this document.
- `screenshots/` — visual references of the running prototype:
  - `01-default.png` — initial state with seeded transcript and live status bar.
  - `02-with-commands.png` — input populated, suggestion chips visible.
  - `03-tweaks-open.png` — Tweaks panel open showing accent/density/show controls.
  - `04-error-state.png` — command in-flight, showing the pending/translating state.
- `index.html` — entry point, CSS custom properties, font imports, script tags.
- `app.jsx` — top-level wiring: state, submit handler, recall, Tweaks, local
  interpreter. Contains the simulated console state.
- `status-bar.jsx` — top status bar component (`StatusBar`, `Pill`, `Metric`,
  `ChannelStrip`).
- `history.jsx` — transcript component (`History`, `Entry`, `PendingDots`).
- `composer.jsx` — bottom input region (`Composer`, suggestion chips).
- `translator.jsx` — `window.translateCommand`, system prompt, fallback rules.
- `tweaks-panel.jsx` — design-time tweaks shell (NOT needed in production —
  it's a prototyping tool for swapping accent color, density, show name, and
  channel count without recompiling).

To run the prototype locally, serve the folder over any static HTTP server
(e.g. `python -m http.server`) and open `index.html`. The `window.claude`
global is provided only by the prototype host — when running standalone the
translator falls back to the regex engine.

---

## Assets
None. The prototype uses no external images, icons, or media. The "NL"
brand mark is rendered as text in a bordered box. The channel-strip bars
are CSS divs. No SVG or icon library is required.

---

## Open Questions for the Implementer
1. **Transport choice** — OSC over UDP vs. TCP-SLIP, and whether to bridge
   via a local daemon or a server you host.
2. **Confirmation step** — should destructive commands (`Record`, `Delete`,
   `Update`, `Out`) require an explicit confirm tap before sending?
3. **Voice input** — speech-to-text in front of the translator is a natural
   extension and could be added behind a mic button in the composer.
4. **Multi-console support** — if you need to target multiple consoles or
   sessions, the connection pill should become a switcher.
5. **Persistence** — should transcript survive reloads? Local-storage keyed
   by show name is a low-friction default.
