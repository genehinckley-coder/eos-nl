// app.jsx — top-level wiring

const { useState, useEffect, useRef, useMemo } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "amber",
  "density": "comfortable",
  "showName": "Hamlet · Act II",
  "channelCount": 32,
  "showStripChrome": true
}/*EDITMODE-END*/;

const ACCENT_PRESETS = {
  amber:  { amber: "oklch(0.78 0.13 75)",  amberSoft: "oklch(0.78 0.13 75 / 0.18)",  amberLine: "oklch(0.78 0.13 75 / 0.35)" },
  rose:   { amber: "oklch(0.74 0.15 18)",  amberSoft: "oklch(0.74 0.15 18 / 0.18)",  amberLine: "oklch(0.74 0.15 18 / 0.35)" },
  cyan:   { amber: "oklch(0.78 0.10 215)", amberSoft: "oklch(0.78 0.10 215 / 0.18)", amberLine: "oklch(0.78 0.10 215 / 0.35)" },
  lime:   { amber: "oklch(0.83 0.15 130)", amberSoft: "oklch(0.83 0.15 130 / 0.18)", amberLine: "oklch(0.83 0.15 130 / 0.35)" },
  violet: { amber: "oklch(0.74 0.13 295)", amberSoft: "oklch(0.74 0.13 295 / 0.18)", amberLine: "oklch(0.74 0.13 295 / 0.35)" },
};

// --- helpers --------------------------------------------------------------

function pad2(n) { return String(n).padStart(2, "0"); }
function nowStamp(d = new Date()) {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}
function uid() { return Math.random().toString(36).slice(2, 9); }

// Build a believable initial channel set: a few hot, several mid, the rest dark
function seedChannels(n) {
  const arr = [];
  for (let i = 0; i < n; i++) {
    const id = i + 1;
    let level = 0;
    if (i < 4) level = 70 + Math.floor(Math.random() * 30);
    else if (i < 12) level = 30 + Math.floor(Math.random() * 40);
    else if (i < 18) level = Math.floor(Math.random() * 25);
    arr.push({ id, level });
  }
  return arr;
}

// Tiny EOS-syntax interpreter — updates state from a translated command.
// Returns { result: string, mutator: (state) => state }
function interpretSyntax(syntax) {
  if (!syntax) return { result: "no-op" };
  const s = syntax.trim();

  // Out / Blackout
  if (/^Out\s+Enter$/i.test(s)) {
    return {
      result: "blackout",
      mutator: (st) => ({ ...st, channels: st.channels.map((c) => ({ ...c, level: 0 })) }),
    };
  }

  // Go to cue N
  let m;
  if ((m = s.match(/^Go\s+To\s+Cue\s+([\d.]+)\s+Enter$/i))) {
    const cue = m[1];
    return {
      result: `cue ${cue} active`,
      mutator: (st) => ({
        ...st,
        activeCue: cue,
        nextCue: String((parseFloat(cue) || 0) + 1),
        cueList: cue,
      }),
    };
  }
  if (/^Go\s+Enter$/i.test(s)) {
    return {
      result: "next cue",
      mutator: (st) => {
        const next = parseFloat(st.nextCue) || (parseFloat(st.activeCue) + 1);
        return {
          ...st,
          activeCue: String(next),
          nextCue: String(next + 1),
          cueList: String(next),
        };
      },
    };
  }
  if (/^Back\s+Enter$/i.test(s)) {
    return {
      result: "previous cue",
      mutator: (st) => {
        const prev = Math.max(1, (parseFloat(st.activeCue) || 1) - 1);
        return {
          ...st,
          activeCue: String(prev),
          nextCue: String(prev + 1),
          cueList: String(prev),
        };
      },
    };
  }

  if ((m = s.match(/^Record\s+Cue\s+([\d.]+)\s+Enter$/i))) {
    return { result: `recorded as cue ${m[1]}` };
  }
  if (/^Update\s+Enter$/i.test(s)) return { result: "cue updated" };
  if (/^Group\s+\d+\s+Enter$/i.test(s)) return { result: "group selected" };

  // Chan A Thru B @ V Enter
  if ((m = s.match(/^Chan\s+(\d+)\s+Thru\s+(\d+)\s+@\s+(Full|Out|\d+)\s+Enter$/i))) {
    const a = parseInt(m[1], 10), b = parseInt(m[2], 10);
    const lvl = m[3].toLowerCase() === "full" ? 100 : m[3].toLowerCase() === "out" ? 0 : parseInt(m[3], 10);
    return {
      result: `${b - a + 1} channels @ ${lvl}`,
      mutator: (st) => ({
        ...st,
        channels: st.channels.map((c) =>
          c.id >= a && c.id <= b ? { ...c, level: lvl } : c
        ),
      }),
    };
  }

  // Chan list (1 + 5 + 9) @ V Enter
  if ((m = s.match(/^Chan\s+([\d\s+]+)\s+@\s+(Full|Out|\d+)\s+Enter$/i))) {
    const ids = m[1].split("+").map((x) => parseInt(x.trim(), 10)).filter(Boolean);
    const lvl = m[2].toLowerCase() === "full" ? 100 : m[2].toLowerCase() === "out" ? 0 : parseInt(m[2], 10);
    return {
      result: `${ids.length} channel${ids.length > 1 ? "s" : ""} @ ${lvl}`,
      mutator: (st) => ({
        ...st,
        channels: st.channels.map((c) => (ids.includes(c.id) ? { ...c, level: lvl } : c)),
      }),
    };
  }

  // Single Chan N @ V
  if ((m = s.match(/^Chan\s+(\d+)\s+@\s+(Full|Out|\d+)\s+Enter$/i))) {
    const id = parseInt(m[1], 10);
    const lvl = m[2].toLowerCase() === "full" ? 100 : m[2].toLowerCase() === "out" ? 0 : parseInt(m[2], 10);
    return {
      result: `Ch ${id} @ ${lvl}`,
      mutator: (st) => ({
        ...st,
        channels: st.channels.map((c) => (c.id === id ? { ...c, level: lvl } : c)),
      }),
    };
  }

  return { result: "executed" };
}

// --- App ------------------------------------------------------------------

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Inject CSS vars from accent + density
  useEffect(() => {
    const accent = ACCENT_PRESETS[tweaks.accent] || ACCENT_PRESETS.amber;
    const root = document.documentElement;
    root.style.setProperty("--amber", accent.amber);
    root.style.setProperty("--amber-soft", accent.amberSoft);
    root.style.setProperty("--amber-line", accent.amberLine);
  }, [tweaks.accent]);

  const [status, setStatus] = useState(() => ({
    showName: tweaks.showName,
    cueList: "47",
    cueTotal: "120",
    activeCue: "47",
    nextCue: "48",
    gm: 100,
    mode: "Live",
    connection: "Online",
    clock: nowStamp(),
    channels: seedChannels(tweaks.channelCount),
  }));

  // Keep showName/channels in sync with tweaks
  useEffect(() => {
    setStatus((st) => ({
      ...st,
      showName: tweaks.showName,
      channels: st.channels.length === tweaks.channelCount
        ? st.channels
        : seedChannels(tweaks.channelCount),
    }));
  }, [tweaks.showName, tweaks.channelCount]);

  // Live clock
  useEffect(() => {
    const id = setInterval(() => {
      setStatus((st) => ({ ...st, clock: nowStamp() }));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // History
  const [entries, setEntries] = useState(() => {
    // Seed with two pre-canned entries so the UI doesn't feel empty
    return [
      {
        id: uid(),
        ts: "19:24:03",
        natural: "Bring channels 1 through 10 to full",
        syntax: "Chan 1 Thru 10 @ Full Enter",
        status: "ok",
        source: "fallback",
        result: "10 channels @ 100",
      },
      {
        id: uid(),
        ts: "19:24:41",
        natural: "Go to cue 47",
        syntax: "Go To Cue 47 Enter",
        status: "ok",
        source: "fallback",
        result: "cue 47 active",
      },
    ];
  });

  const [busy, setBusy] = useState(false);
  const recallRef = useRef({ index: -1, snapshot: "" });

  const submit = async (natural) => {
    const id = uid();
    const ts = nowStamp();
    setEntries((arr) => [
      ...arr,
      { id, ts, natural, syntax: "", status: "pending" },
    ]);
    setBusy(true);

    const result = await window.translateCommand(natural);

    setEntries((arr) =>
      arr.map((e) => {
        if (e.id !== id) return e;
        if (!result.ok) {
          return {
            ...e,
            syntax: result.error || "could not parse",
            status: "error",
            source: result.source,
            result: "",
          };
        }
        return {
          ...e,
          syntax: result.syntax,
          status: "ok",
          source: result.source,
          result: "",
        };
      })
    );

    if (result.ok) {
      const interp = interpretSyntax(result.syntax);
      if (interp.mutator) {
        setStatus((st) => interp.mutator(st));
      }
      setEntries((arr) =>
        arr.map((e) => (e.id === id ? { ...e, result: interp.result } : e))
      );
    }

    setBusy(false);
  };

  // Up/Down history recall on the input
  useEffect(() => {
    const handler = (ev) => {
      if (ev.target.tagName !== "INPUT") return;
      const inputEl = ev.target;
      if (ev.key === "ArrowUp") {
        const naturals = entries.map((e) => e.natural);
        if (naturals.length === 0) return;
        ev.preventDefault();
        if (recallRef.current.index === -1) {
          recallRef.current.snapshot = inputEl.value;
        }
        recallRef.current.index = Math.min(recallRef.current.index + 1, naturals.length - 1);
        const v = naturals[naturals.length - 1 - recallRef.current.index];
        // synthesize change event
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        setter.call(inputEl, v);
        inputEl.dispatchEvent(new Event("input", { bubbles: true }));
      } else if (ev.key === "ArrowDown") {
        if (recallRef.current.index < 0) return;
        ev.preventDefault();
        recallRef.current.index -= 1;
        const naturals = entries.map((e) => e.natural);
        const v = recallRef.current.index < 0
          ? recallRef.current.snapshot
          : naturals[naturals.length - 1 - recallRef.current.index];
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        setter.call(inputEl, v);
        inputEl.dispatchEvent(new Event("input", { bubbles: true }));
      } else if (ev.key === "Enter") {
        recallRef.current.index = -1;
        recallRef.current.snapshot = "";
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [entries]);

  // Wrap layout per density
  const wrap = useMemo(() => ({
    display: "flex",
    flexDirection: "column",
    height: "100%",
    fontSize: tweaks.density === "compact" ? 13 : 14,
  }), [tweaks.density]);

  return (
    <div style={wrap}>
      <StatusBar state={status} />
      <History entries={entries} onClear={() => setEntries([])} />
      <Composer onSubmit={submit} busy={busy} />

      <TweaksPanel title="Tweaks">
        <TweakSection label="Appearance">
          <TweakRadio
            label="Accent"
            value={tweaks.accent}
            onChange={(v) => setTweak("accent", v)}
            options={[
              { value: "amber",  label: "Amber" },
              { value: "rose",   label: "Rose" },
              { value: "cyan",   label: "Cyan" },
              { value: "lime",   label: "Lime" },
              { value: "violet", label: "Violet" },
            ]}
          />
          <TweakRadio
            label="Density"
            value={tweaks.density}
            onChange={(v) => setTweak("density", v)}
            options={[
              { value: "comfortable", label: "Comfortable" },
              { value: "compact",     label: "Compact" },
            ]}
          />
        </TweakSection>
        <TweakSection label="Show">
          <TweakText
            label="Show Name"
            value={tweaks.showName}
            onChange={(v) => setTweak("showName", v)}
          />
          <TweakSlider
            label="Channels"
            value={tweaks.channelCount}
            min={8} max={64} step={4}
            onChange={(v) => setTweak("channelCount", v)}
          />
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
