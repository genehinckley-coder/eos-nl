// translator.jsx — natural language → EOS-style console syntax
// Uses window.claude.complete when available; falls back to a small rule engine.

const SYSTEM_PROMPT = `You translate natural language theatrical lighting commands into EOS-style console syntax.

Rules:
- Output ONLY the syntax line, nothing else. No quotes, no explanation, no markdown.
- Use proper EOS keywords: Chan, Thru, At, Full, Out, Plus, Minus, Group, Sub, Cue, Go, Stop, Back, Record, Update, Copy, Delete, Label, Time, Color, Intensity, Park, Unpark, Block, Mark, Follow, Hang.
- Use "@" for "at" in intensity assignments (e.g. "Chan 5 @ 75").
- End executable commands with "Enter" (e.g. "Chan 1 Thru 10 @ Full Enter").
- "Full" = 100%, "Out" = 0%. Percent values are bare numbers (no % sign).
- Multi-target: use Thru for ranges, Plus for unions, Minus for exclusions.
- "Bring up", "raise", "set", "fade to", "take to" → @ <value>.
- "Go" / "next cue" → Go Enter. "Back" / "previous cue" → Back Enter.
- "Record cue 12" → Record Cue 12 Enter. "Update cue" → Update Enter.
- If the request is ambiguous or non-lighting, respond with: ?? <short reason>

Examples:
"bring channels 1 through 10 to full" → Chan 1 Thru 10 @ Full Enter
"channel 5 at 75 percent" → Chan 5 @ 75 Enter
"go to cue 12" → Go To Cue 12 Enter
"next cue" → Go Enter
"back" → Back Enter
"record cue 5" → Record Cue 5 Enter
"blackout" → Out Enter
"channels 1 plus 5 plus 9 to half" → Chan 1 + 5 + 9 @ 50 Enter
"select group 3" → Group 3 Enter
"label cue 5 opening" → Label Cue 5 "opening" Enter`;

async function translateWithClaude(input) {
  if (!window.claude || typeof window.claude.complete !== "function") {
    return null;
  }
  try {
    const text = await window.claude.complete({
      messages: [
        { role: "user", content: `${SYSTEM_PROMPT}\n\nInput: ${input}\nOutput:` },
      ],
    });
    if (!text) return null;
    // Strip wrappers/code fences/quotes if the model added them
    return text
      .trim()
      .replace(/^```[a-z]*\n?/i, "")
      .replace(/\n?```$/g, "")
      .replace(/^["'`]|["'`]$/g, "")
      .split("\n")[0]
      .trim();
  } catch (err) {
    console.warn("[translator] claude.complete failed:", err);
    return null;
  }
}

// --- Deterministic fallback ----------------------------------------------

const NUM_WORDS = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15,
  sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20,
  half: 50, full: 100, out: 0, off: 0,
};

function n(token) {
  if (token == null) return null;
  const t = String(token).toLowerCase().trim();
  if (NUM_WORDS[t] != null) return NUM_WORDS[t];
  const m = t.match(/^(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

function fallbackTranslate(input) {
  const s = input.toLowerCase().trim();

  if (/^(black ?out|kill all|all out|lights out)\b/.test(s)) return "Out Enter";
  if (/^(go|next( cue)?|fire( the)? next)\b/.test(s) && !/back/.test(s)) return "Go Enter";
  if (/^(back|previous( cue)?|prev)\b/.test(s)) return "Back Enter";
  if (/^stop( back)?\b/.test(s)) return "Stop Enter";
  if (/^clear( command(line)?)?\b/.test(s)) return "Clear Clear Enter";

  let m;
  if ((m = s.match(/^(?:go ?to|recall|jump to)\s+cue\s+([\d\.]+)/))) {
    return `Go To Cue ${m[1]} Enter`;
  }
  if ((m = s.match(/^record(?: cue)?\s+([\d\.]+)/))) {
    return `Record Cue ${m[1]} Enter`;
  }
  if (/^update( cue)?\b/.test(s)) return "Update Enter";

  if ((m = s.match(/^(?:select |use )?group\s+(\d+)/))) {
    return `Group ${m[1]} Enter`;
  }
  if ((m = s.match(/^sub(?:master)?\s+(\d+)\s+(?:at|to|@)\s+([a-z\d]+)/))) {
    const v = n(m[2]);
    return `Sub ${m[1]} @ ${v === 100 ? "Full" : v === 0 ? "Out" : v} Enter`;
  }

  // Range: "channels A through B at V"
  if ((m = s.match(/chan(?:nels?)?\s+(\d+)\s+(?:thru|through|to|-)\s+(\d+)\s+(?:at|to|@|set to|fade to|take to|raise to|bring (?:up )?to)\s+([a-z\d]+)/))) {
    const v = n(m[3]);
    const out = v === 100 ? "Full" : v === 0 ? "Out" : v;
    return `Chan ${m[1]} Thru ${m[2]} @ ${out} Enter`;
  }
  // Plus list: "channels 1 plus 5 plus 9 at V"
  if ((m = s.match(/chan(?:nels?)?\s+([\d\s+andplus,]+?)\s+(?:at|to|@|set to|fade to)\s+([a-z\d]+)/))) {
    const list = m[1].replace(/and|plus|,/g, "+").replace(/\s+/g, "").split("+").filter(Boolean);
    const v = n(m[2]);
    const out = v === 100 ? "Full" : v === 0 ? "Out" : v;
    return `Chan ${list.join(" + ")} @ ${out} Enter`;
  }
  // Single: "channel 5 at V"
  if ((m = s.match(/chan(?:nel)?\s+(\d+)\s+(?:at|to|@|set to|fade to|take to|raise to|bring (?:up )?to)?\s*([a-z\d]+)?/))) {
    const v = n(m[2]);
    if (v == null) return `Chan ${m[1]} Enter`;
    const out = v === 100 ? "Full" : v === 0 ? "Out" : v;
    return `Chan ${m[1]} @ ${out} Enter`;
  }

  // "bring up 5 to full"
  if ((m = s.match(/(?:bring up|raise|take up)\s+(\d+)\s+(?:to\s+)?([a-z\d]+)/))) {
    const v = n(m[2]);
    const out = v === 100 ? "Full" : v === 0 ? "Out" : v;
    return `Chan ${m[1]} @ ${out} Enter`;
  }

  return `?? could not parse — try "channel 5 at 75" or "go to cue 12"`;
}

window.translateCommand = async function translateCommand(input) {
  const trimmed = (input || "").trim();
  if (!trimmed) return { syntax: "", ok: false, error: "empty" };

  // Prefer the Python backend if bridge.js has wired it up
  if (typeof window.__bridgeTranslate === "function") {
    return window.__bridgeTranslate(trimmed);
  }

  const claudeOut = await translateWithClaude(trimmed);
  if (claudeOut && !claudeOut.startsWith("??")) {
    return { syntax: claudeOut, ok: true, source: "claude" };
  }
  if (claudeOut && claudeOut.startsWith("??")) {
    return { syntax: claudeOut, ok: false, error: claudeOut.slice(2).trim(), source: "claude" };
  }
  // Fallback
  const fb = fallbackTranslate(trimmed);
  if (fb.startsWith("??")) {
    return { syntax: fb, ok: false, error: fb.slice(2).trim(), source: "fallback" };
  }
  return { syntax: fb, ok: true, source: "fallback" };
};

// Expose the offline regex engine so bridge.js can use it as a fallback
// when the Python backend is unreachable.
window._eosNlFallback = fallbackTranslate;
