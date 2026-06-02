// composer.jsx — bottom command-entry area

const compStyles = {
  wrap: {
    flexShrink: 0,
    background: "var(--bg-1)",
    borderTop: "1px solid var(--line)",
  },
  chips: {
    display: "flex",
    gap: 8,
    padding: "10px 20px 0",
    flexWrap: "wrap",
  },
  chip: {
    fontFamily: "var(--sans)",
    fontSize: 12,
    color: "var(--ink-1)",
    background: "var(--bg-2)",
    border: "1px solid var(--line)",
    padding: "5px 10px",
    cursor: "pointer",
    transition: "all 120ms ease",
    borderRadius: 2,
    letterSpacing: 0.1,
  },
  chipLabel: {
    fontFamily: "var(--mono)",
    fontSize: 9.5,
    letterSpacing: 1.4,
    color: "var(--ink-3)",
    textTransform: "uppercase",
    paddingTop: 8,
    marginRight: 4,
    alignSelf: "center",
  },
  inputRow: {
    display: "grid",
    gridTemplateColumns: "auto 1fr auto",
    alignItems: "stretch",
    padding: "12px 20px 16px",
    gap: 12,
  },
  prompt: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    paddingRight: 4,
    fontFamily: "var(--mono)",
    fontSize: 13,
    color: "var(--amber)",
    letterSpacing: 0.5,
  },
  promptCaret: { color: "var(--amber)" },
  input: {
    width: "100%",
    background: "var(--bg-2)",
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "var(--line)",
    color: "var(--ink-0)",
    fontFamily: "var(--sans)",
    fontSize: 15,
    padding: "12px 14px",
    outline: "none",
    transition: "border-color 120ms ease, background 120ms ease",
    letterSpacing: 0.1,
  },
  inputFocus: {
    borderColor: "var(--amber-line)",
    background: "var(--bg-2)",
  },
  send: {
    display: "inline-flex",
    alignItems: "center",
    gap: 10,
    padding: "0 18px",
    background: "var(--amber)",
    border: "1px solid var(--amber)",
    color: "#1b1408",
    fontFamily: "var(--mono)",
    fontWeight: 600,
    fontSize: 11.5,
    letterSpacing: 1.6,
    textTransform: "uppercase",
    cursor: "pointer",
    transition: "all 120ms ease",
  },
  sendDisabled: {
    background: "var(--bg-3)",
    borderColor: "var(--line)",
    color: "var(--ink-3)",
    cursor: "not-allowed",
  },
  sendKbd: {
    fontFamily: "var(--mono)",
    fontSize: 9.5,
    background: "rgba(0,0,0,0.18)",
    padding: "2px 6px",
    border: "1px solid rgba(0,0,0,0.25)",
  },
  hint: {
    display: "flex",
    justifyContent: "space-between",
    fontFamily: "var(--mono)",
    fontSize: 10,
    color: "var(--ink-3)",
    letterSpacing: 1.1,
    textTransform: "uppercase",
    padding: "0 20px 10px",
  },
};

const SUGGESTIONS = [
  "Bring channels 1 through 10 to full",
  "Channel 5 at 75",
  "Go to cue 12",
  "Next cue",
  "Record cue 5",
  "Blackout",
  "Group 3 at half",
  "Channels 1 plus 5 plus 9 to full",
];

function Composer({ onSubmit, busy }) {
  const [value, setValue] = React.useState("");
  const [focused, setFocused] = React.useState(false);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    // Auto-focus on mount
    if (inputRef.current) inputRef.current.focus();
  }, []);

  const submit = () => {
    const v = value.trim();
    if (!v || busy) return;
    onSubmit(v);
    setValue("");
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div style={compStyles.wrap}>
      <div style={compStyles.chips}>
        <span style={compStyles.chipLabel}>Try:</span>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            style={compStyles.chip}
            onClick={() => {
              setValue(s);
              if (inputRef.current) inputRef.current.focus();
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "var(--amber)";
              e.currentTarget.style.borderColor = "var(--amber-line)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "var(--ink-1)";
              e.currentTarget.style.borderColor = "var(--line)";
            }}
          >{s}</button>
        ))}
      </div>

      <div style={compStyles.inputRow}>
        <div style={compStyles.prompt}>
          <span>NL</span>
          <span style={compStyles.promptCaret}>›</span>
        </div>
        <input
          ref={inputRef}
          style={{ ...compStyles.input, ...(focused ? compStyles.inputFocus : {}) }}
          placeholder='Speak naturally — e.g. "bring up channels 1 through 10 to full"'
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKey}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          spellCheck={false}
          autoComplete="off"
        />
        <button
          style={{ ...compStyles.send, ...(!value.trim() || busy ? compStyles.sendDisabled : {}) }}
          onClick={submit}
          disabled={!value.trim() || busy}
        >
          <span>{busy ? "Translating" : "Execute"}</span>
          <span style={compStyles.sendKbd}>↵</span>
        </button>
      </div>

      <div style={compStyles.hint}>
        <span>NL → EOS Syntax · {busy ? "translating…" : "ready"}</span>
        <span>↑/↓ recall · ⏎ send · Shift+⏎ newline</span>
      </div>
    </div>
  );
}

window.Composer = Composer;
