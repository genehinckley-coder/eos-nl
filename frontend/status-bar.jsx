// status-bar.jsx — top status section

const subTextBase = { fontFamily: "var(--mono)", color: "var(--ink-2)" };

const sbStyles = {
  bar: {
    display: "grid",
    gridTemplateColumns: "minmax(0, auto) minmax(0, 1fr) minmax(0, auto)",
    alignItems: "stretch",
    background: "var(--bg-1)",
    borderBottom: "1px solid var(--line)",
    flexShrink: 0,
    minWidth: 0,
    overflow: "hidden",
  },
  brandCell: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 16px",
    borderRight: "1px solid var(--line)",
    minWidth: 0,
    flexShrink: 1,
  },
  brandMark: {
    width: 28,
    height: 28,
    display: "grid",
    placeItems: "center",
    background: "var(--bg-3)",
    border: "1px solid var(--line)",
    color: "var(--amber)",
    fontFamily: "var(--mono)",
    fontWeight: 700,
    fontSize: 11,
    letterSpacing: 0.5,
    borderRadius: 2,
  },
  brandText: { display: "flex", flexDirection: "column", gap: 2 },
  brandLabel: {
    fontFamily: "var(--mono)",
    fontSize: 10,
    letterSpacing: 1.4,
    color: "var(--ink-2)",
    textTransform: "uppercase",
  },
  brandTitle: { fontSize: 13, fontWeight: 600, color: "var(--ink-0)", letterSpacing: 0.2 },
  metricsRow: {
    display: "flex",
    alignItems: "stretch",
    minWidth: 0,
    overflow: "hidden",
  },
  metric: {
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    gap: 3,
    padding: "10px 16px",
    borderRight: "1px solid var(--line)",
    minWidth: 0,
    flexShrink: 0,
    whiteSpace: "nowrap",
  },
  metricLabel: {
    fontFamily: "var(--mono)",
    fontSize: 9.5,
    letterSpacing: 1.3,
    color: "var(--ink-2)",
    textTransform: "uppercase",
  },
  metricValue: {
    fontFamily: "var(--mono)",
    fontSize: 15,
    fontWeight: 500,
    color: "var(--ink-0)",
    letterSpacing: 0.3,
  },
  metricValueAccent: { color: "var(--amber)" },
  metricSub:     { ...subTextBase, fontSize: 10, marginLeft: 4 },
  metricSubLine: { ...subTextBase, display: "block", fontSize: 9, marginLeft: 4 },
  rightCell: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 16px",
    borderLeft: "1px solid var(--line)",
    flexShrink: 0,
  },
  pill: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "5px 10px",
    border: "1px solid var(--line)",
    borderRadius: 999,
    fontFamily: "var(--mono)",
    fontSize: 10,
    letterSpacing: 1.1,
    color: "var(--ink-1)",
    textTransform: "uppercase",
    background: "var(--bg-2)",
  },
  dot: { width: 7, height: 7, borderRadius: 999, background: "var(--ink-3)" },
  dotLive: { background: "var(--green)", boxShadow: "0 0 0 3px oklch(0.78 0.13 150 / 0.18)" },
  dotBlind: { background: "var(--cool)" },
  dotAlert: { background: "var(--red)" },
  dotNeutral: { background: "var(--ink-3)" },
};

function Pill({ tone = "live", children }) {
  const dotStyle = {
    ...sbStyles.dot,
    ...(tone === "live"    ? sbStyles.dotLive
      : tone === "blind"   ? sbStyles.dotBlind
      : tone === "alert"   ? sbStyles.dotAlert
      : tone === "neutral" ? sbStyles.dotNeutral
      : {}),
  };
  return (
    <span style={sbStyles.pill}>
      <span style={dotStyle}></span>
      {children}
    </span>
  );
}

function Metric({ label, value, sub, subLine, accent }) {
  return (
    <div style={sbStyles.metric}>
      <div style={sbStyles.metricLabel}>{label}</div>
      <div>
        <span style={{ ...sbStyles.metricValue, ...(accent ? sbStyles.metricValueAccent : {}) }}>{value}</span>
        {sub && <span style={sbStyles.metricSub}>{sub}</span>}
        {subLine && <span style={sbStyles.metricSubLine}>{subLine}</span>}
      </div>
    </div>
  );
}

// Live channel intensity strip — purely visual, animates subtly
function ChannelStrip({ channels }) {
  const wrapRef = React.useRef(null);
  // fits: how many bars fit in the container (updated by ResizeObserver on resize)
  // visible: derived during render — no second ResizeObserver fire needed when channels arrive
  const [fits, setFits] = React.useState(0);
  const fitsRef = React.useRef(0);

  React.useEffect(() => {
    if (!wrapRef.current) return;
    const el = wrapRef.current;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      // each bar is 16px wide + 2px gap, padding ~32px
      const next = Math.max(0, Math.floor((w - 32) / 18));
      if (next !== fitsRef.current) {
        fitsRef.current = next;
        setFits(next);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []); // runs once on mount; ResizeObserver handles subsequent resizes

  const visible = Math.min(channels.length, fits);
  const shown = channels.slice(0, visible);
  const hidden = channels.length - shown.length;

  return (
    <div ref={wrapRef} style={{
      display: "flex",
      gap: 2,
      padding: "10px 16px",
      borderRight: "1px solid var(--line)",
      alignItems: "center",
      overflow: "hidden",
      flex: 1,
      minWidth: 0,
    }}>
      {shown.map((c, i) => {
        const v = c.level;
        const h = Math.max(2, Math.round((v / 100) * 28));
        const isHot = v > 70;
        const isOn = v > 0;
        return (
          <div key={i} style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "flex-end",
            width: 16,
            height: 32,
            flexShrink: 0,
          }} title={`Ch ${c.id} @ ${v}`}>
            <div style={{
              width: 8,
              height: h,
              background: isOn ? `oklch(${0.55 + (v / 100) * 0.28} ${isHot ? 0.13 : 0.08} 75)` : "var(--bg-3)",
              transition: "height 220ms ease, background 220ms ease",
            }}></div>
          </div>
        );
      })}
      {hidden > 0 && (
        <span style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--ink-3)",
          letterSpacing: 0.6,
          marginLeft: 8,
          flexShrink: 0,
        }}>+{hidden}</span>
      )}
    </div>
  );
}

function StatusBar({ state }) {
  return (
    <div style={sbStyles.bar}>
      <div style={sbStyles.brandCell}>
        <div style={sbStyles.brandMark}>NL</div>
        <div style={{ ...sbStyles.brandText, minWidth: 0 }}>
          <div style={{ ...sbStyles.brandLabel, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>EOS ION · Natural Language</div>
          <div style={{ ...sbStyles.brandTitle, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{state.showName}</div>
        </div>
      </div>

      <div style={sbStyles.metricsRow}>
        <Metric label="Cue List" value={`${state.cueList}`} sub={`/${state.cueTotal}`} />
        <Metric label="Active" value={state.activeCue} subLine={state.activeCueLabel} accent />
        <Metric label="Next" value={state.nextCue} subLine={state.nextCueLabel} />
        <Metric label="GM" value={`${state.gm}`} sub="%" />
        <ChannelStrip channels={state.channels} />
      </div>

      <div style={sbStyles.rightCell}>
        <Pill tone={state.mode === "Live" ? "live" : state.mode === "Blind" ? "blind" : "neutral"}>{state.mode}</Pill>
        <Pill tone={state.connection === "Online" ? "live" : "alert"}>{state.connection}</Pill>
        <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-1)", letterSpacing: 0.5 }}>
          {state.clock}
        </span>
      </div>
    </div>
  );
}

window.StatusBar = StatusBar;
