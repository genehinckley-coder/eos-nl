// history.jsx — scrolling command transcript

const histStyles = {
  wrap: {
    flex: 1,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    background: "var(--bg-0)",
    position: "relative",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 20px",
    borderBottom: "1px solid var(--line)",
    background: "var(--bg-1)",
    flexShrink: 0,
  },
  headerLabel: {
    fontFamily: "var(--mono)",
    fontSize: 10,
    letterSpacing: 1.4,
    color: "var(--ink-2)",
    textTransform: "uppercase",
  },
  headerActions: { display: "flex", gap: 14, alignItems: "center" },
  miniBtn: {
    fontFamily: "var(--mono)",
    fontSize: 10,
    letterSpacing: 1.2,
    color: "var(--ink-2)",
    textTransform: "uppercase",
    background: "transparent",
    border: "1px solid var(--line)",
    padding: "4px 9px",
    cursor: "pointer",
    transition: "color 120ms ease, border-color 120ms ease",
  },
  scroll: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    padding: "20px 20px 24px",
  },
  empty: {
    height: "100%",
    display: "grid",
    placeItems: "center",
    color: "var(--ink-3)",
    fontFamily: "var(--mono)",
    fontSize: 12,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  entry: {
    display: "grid",
    gridTemplateColumns: "60px 1fr",
    columnGap: 16,
    padding: "12px 0",
    borderBottom: "1px dashed var(--line-soft)",
  },
  ts: {
    fontFamily: "var(--mono)",
    fontSize: 11,
    color: "var(--ink-3)",
    letterSpacing: 0.4,
    paddingTop: 2,
    userSelect: "none",
  },
  body: { display: "flex", flexDirection: "column", gap: 6, minWidth: 0 },
  natural: {
    display: "flex",
    alignItems: "baseline",
    gap: 10,
    color: "var(--ink-0)",
    fontSize: 14.5,
    lineHeight: 1.4,
  },
  arrow: {
    fontFamily: "var(--mono)",
    fontSize: 12,
    color: "var(--amber)",
    flexShrink: 0,
    paddingTop: 1,
  },
  syntaxRow: {
    display: "flex",
    alignItems: "baseline",
    gap: 10,
    color: "var(--ink-1)",
  },
  syntaxArrow: {
    fontFamily: "var(--mono)",
    fontSize: 12,
    color: "var(--ink-3)",
    flexShrink: 0,
  },
  syntax: {
    fontFamily: "var(--mono)",
    fontSize: 13.5,
    color: "var(--ink-0)",
    background: "var(--bg-2)",
    border: "1px solid var(--line)",
    padding: "5px 10px",
    letterSpacing: 0.3,
    wordBreak: "break-all",
    flex: 1,
  },
  syntaxError: {
    color: "var(--red)",
    background: "transparent",
    border: "1px dashed var(--red)",
  },
  meta: {
    display: "flex",
    gap: 12,
    fontFamily: "var(--mono)",
    fontSize: 10.5,
    color: "var(--ink-2)",
    letterSpacing: 0.6,
    paddingLeft: 22,
  },
  metaOk: { color: "var(--green)" },
  metaErr: { color: "var(--red)" },
  metaPending: { color: "var(--amber)" },
  pendingDots: {
    display: "inline-block",
    width: 14,
  },
};

function PendingDots() {
  const [n, setN] = React.useState(1);
  React.useEffect(() => {
    const id = setInterval(() => setN((x) => (x % 3) + 1), 350);
    return () => clearInterval(id);
  }, []);
  return <span style={histStyles.pendingDots}>{".".repeat(n)}</span>;
}

function Entry({ entry }) {
  const { id, ts, natural, syntax, status, source, result } = entry;
  const isError = status === "error";
  const isPending = status === "pending";
  return (
    <div style={histStyles.entry}>
      <div style={histStyles.ts}>{ts}</div>
      <div style={histStyles.body}>
        <div style={histStyles.natural}>
          <span style={histStyles.arrow}>›</span>
          <span style={{ flex: 1 }}>{natural}</span>
        </div>

        <div style={histStyles.syntaxRow}>
          <span style={histStyles.syntaxArrow}>→</span>
          <code style={{ ...histStyles.syntax, ...(isError ? histStyles.syntaxError : {}) }}>
            {isPending ? <span style={{ color: "var(--ink-2)" }}>translating<PendingDots /></span> : syntax}
          </code>
        </div>

        <div style={histStyles.meta}>
          {isPending && <span style={histStyles.metaPending}>● pending</span>}
          {status === "ok" && <span style={histStyles.metaOk}>● executed</span>}
          {isError && <span style={histStyles.metaErr}>● rejected</span>}
          {result && <span>{result}</span>}
          {source && !isPending && <span>via {source}</span>}
        </div>
      </div>
    </div>
  );
}

function History({ entries, onClear }) {
  const scrollRef = React.useRef(null);
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [entries]);

  return (
    <div style={histStyles.wrap}>
      <div style={histStyles.header}>
        <div style={histStyles.headerLabel}>Command Transcript · {entries.length}</div>
        <div style={histStyles.headerActions}>
          <button
            style={histStyles.miniBtn}
            onClick={onClear}
            onMouseEnter={(e) => { e.currentTarget.style.color = "var(--amber)"; e.currentTarget.style.borderColor = "var(--amber-line)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "var(--ink-2)"; e.currentTarget.style.borderColor = "var(--line)"; }}
          >Clear</button>
        </div>
      </div>
      <div style={histStyles.scroll} ref={scrollRef}>
        {entries.length === 0 ? (
          <div style={histStyles.empty}>— transcript empty —</div>
        ) : (
          entries.map((e) => <Entry key={e.id} entry={e} />)
        )}
      </div>
    </div>
  );
}

window.History = History;
