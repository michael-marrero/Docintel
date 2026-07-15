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

// --- rendering (pure; used by brief.js/app.js before innerHTML) ---

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** HTML-escape any user- or corpus-originated text before it reaches innerHTML. */
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
}

/** A citation chip label from an Answer citation: `[FY24 · 1A]` (2-digit FY +
 * item code, "Item " stripped). The corpus lacks a per-citation form type, so
 * the chip is FY+item, not the mockup's `10-K'24` — honest to the data. */
export function citationChipLabel(cit) {
  const yy = String((Number(cit?.fiscal_year) || 0) % 100).padStart(2, "0");
  const item = String(cit?.item_code ?? "").replace(/^item\s+/i, "").trim();
  return item ? `[FY${yy} · ${item}]` : `[FY${yy}]`;
}

// A bracketed token that looks like a retrieval chunk_id: `TICKER-FY2024-…`.
// Used to distinguish a hallucinated citation (drop, AD-10) from legitimate
// bracketed prose the corpus/LLM may emit (`[sic]`, `[1]`, `[iii]`) — which we
// must KEEP, not silently delete.
const CHUNK_ID_RE = /^[A-Za-z]+-FY\d{4}-/;

/** Render a section's answer text to HTML with inline citation chips (FR-B2).
 * A `[chunk_id]` token the synthesis prompt emits becomes a chip built from
 * structured citation data (never string-parsed markup); a chunk-id-shaped token
 * not in the citation set is a hallucination and is dropped with its leading
 * space (AD-10); any other bracketed prose is preserved verbatim. All text is
 * escaped. */
export function citedTextToHTML(text, citations) {
  const byId = new Map((citations ?? []).map((c) => [c.chunk_id, c]));
  const re = /\[([A-Za-z0-9._-]+)\]/g;
  let html = "";
  let last = 0;
  let m;
  const src = String(text ?? "");
  while ((m = re.exec(src)) !== null) {
    const between = src.slice(last, m.index);
    const cit = byId.get(m[1]);
    if (cit) {
      html += esc(between);
      html += `<span class="chip" data-chunk-id="${esc(cit.chunk_id)}">${esc(citationChipLabel(cit))}</span>`;
    } else if (CHUNK_ID_RE.test(m[1])) {
      // hallucinated citation → drop it and one preceding space (no orphan gap)
      html += esc(between.replace(/ +$/, ""));
    } else {
      // legitimate bracketed prose (e.g. "[sic]") → keep verbatim
      html += esc(between) + esc(m[0]);
    }
    last = m.index + m[0].length;
  }
  html += esc(src.slice(last));
  return html;
}
