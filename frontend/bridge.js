// bridge.js — exposes the Python backend as window.__bridgeTranslate.
//
// This runs synchronously as a plain script BEFORE Babel Standalone finishes
// processing the JSX files. Rather than overriding window.translateCommand
// (which Babel would overwrite after), we set window.__bridgeTranslate here
// so that translator.jsx can check for it at call time, not at setup time.
(function () {
  async function callBackend(input) {
    var res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: input }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return res.json();
  }

  window.__bridgeTranslate = async function (input) {
    var trimmed = (input || "").trim();
    if (!trimmed) return { syntax: "", ok: false, error: "empty input", source: "bridge" };

    try {
      var data = await callBackend(trimmed);
      // Backend returns { ok, syntax, source, error, sent }
      // The frontend only reads { ok, syntax, source, error } — extra fields are ignored.
      return data;
    } catch (err) {
      console.warn("[bridge] backend unreachable, falling back to regex:", err);
      // Use the offline regex engine exposed by translator.jsx
      if (typeof window._eosNlFallback === "function") {
        var fb = window._eosNlFallback(trimmed);
        if (fb.startsWith("??")) {
          return { syntax: fb, ok: false, error: fb.slice(2).trim(), source: "fallback" };
        }
        return { syntax: fb, ok: true, source: "fallback" };
      }
      return { ok: false, syntax: null, error: "backend unreachable", source: "bridge" };
    }
  };
})();
