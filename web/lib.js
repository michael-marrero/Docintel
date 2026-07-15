// docintel frontend — pure logic (no DOM, no fetch). Unit-tested by lib.test.mjs.
// Kept dependency-free and side-effect-free so command routing + label formatting
// can be verified with `node --test` (zero install).

// A ticker: starts with a letter, then letters/dots, ≤6 chars total (covers
// class-B tickers like BRK.B). Rejects "...", ".", and long words.
const TICKER_RE = /^[A-Za-z][A-Za-z.]{0,5}$/;

/**
 * Parse a command-bar string into an intent, disambiguating a bare token
 * against the covered-ticker set.
 *   "brief NWL" / "brief brk.b"  -> { intent: "brief", ticker: "NWL" }  (explicit)
 *   "NWL" (covered) / "nwl"      -> { intent: "brief", ticker: "NWL" }
 *   "TSLA" (all-caps, uncovered) -> { intent: "brief", ticker: "TSLA" } (ticker attempt → refusal downstream)
 *   "sales" / "Apple" / "brief"  -> { intent: "ask", question: "<raw>" } (a word, not a ticker)
 *   "how did margins move?"      -> { intent: "ask", question: "<raw>" }
 *   "" / "   "                    -> null
 *
 * A bare token is a brief request only when it's a known covered ticker OR was
 * typed all-uppercase (an unmistakable ticker attempt). A lowercase/mixed-case
 * word (e.g. "sales", "Apple") is a one-word question — this keeps everyday
 * words out of the brief/refusal path.
 * ponytail: heuristic, not a parser. Upgrade to a grammar only if the command
 * surface grows beyond "brief <ticker>" and free-text ask.
 *
 * @param {string} raw
 * @param {string[]} covered - covered tickers (any case)
 */
export function parseCommand(raw, covered = []) {
  const s = (raw ?? "").trim();
  if (!s) return null;

  const briefPrefixed = s.match(/^brief\s+(.+)$/i);
  if (briefPrefixed) {
    const tok = briefPrefixed[1].trim();
    // "brief NWL" → explicit brief (router decides covered vs refusal).
    // "brief how did margins move" → the remainder is a question, not a ticker.
    if (TICKER_RE.test(tok)) return { intent: "brief", ticker: tok.toUpperCase() };
    return { intent: "ask", question: s };
  }

  if (TICKER_RE.test(s)) {
    const t = s.toUpperCase();
    const isCovered = covered.some((c) => String(c).toUpperCase() === t);
    const typedAsTicker = s === t; // all-uppercase as typed
    if (isCovered || typedAsTicker) return { intent: "brief", ticker: t };
  }

  return { intent: "ask", question: s };
}

/**
 * The `CORPUS · N FILERS · FY22–FY24` scope label from a /coverage corpus block.
 * Two-digit fiscal years (matches the mockup). Missing years collapse gracefully.
 */
export function formatScopeLabel(corpus) {
  const n = corpus?.company_count ?? 0;
  const filers = `CORPUS · ${n} FILER${n === 1 ? "" : "S"}`;
  const lo = corpus?.fy_min;
  const hi = corpus?.fy_max;
  if (lo == null || hi == null) return filers;
  const fy = (y) => `FY${String(y % 100).padStart(2, "0")}`;
  const span = lo === hi ? fy(lo) : `${fy(lo)}–${fy(hi)}`;
  return `${filers} · ${span}`;
}

/** Uppercase tickers of the in-corpus companies from a /coverage response.
 * Rows missing a ticker are dropped (no "UNDEFINED" chip). */
export function coveredTickers(companies) {
  return (companies ?? [])
    .filter((c) => c && c.in_corpus && c.ticker)
    .map((c) => String(c.ticker).toUpperCase());
}

/** Case-insensitive membership test against the covered (in_corpus) set. */
export function isCovered(ticker, companies) {
  if (!ticker) return false;
  return coveredTickers(companies).includes(String(ticker).toUpperCase());
}
