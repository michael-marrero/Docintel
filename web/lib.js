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

// --- trust/accuracy panel (Story 3.9, UX-DR10) — pure; fetch+dialog in trust.js ---

/** Format a rate in [0,1] as a percentage, or "—" when absent. */
function pct(v) {
  return Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—";
}

/** The trust/accuracy panel body (Story 3.9): headline citation-accuracy +
 * faithfulness in teal mono with a 95%-CI band + the eval manifest. Pure +
 * escaped. `data` is the GET /trust payload. A placeholder (source ==
 * "placeholder") or a non-representative run is labeled honestly — the panel
 * never presents non-proof as proof (AD-11). */
export function trustPanelHTML(data) {
  const d = data ?? {};
  if (d.source === "placeholder" || !d.manifest) {
    return (
      `<p class="trust-note">Proof numbers aren't wired yet. Run the eval harness ` +
      `(<code>docintel-eval run</code>) to populate this panel.</p>`
    );
  }
  const f = d.faithfulness ?? {};
  const c = d.citation_accuracy ?? {};
  const ci = Array.isArray(f.ci) && f.ci.length === 2 ? f.ci : null;
  const band = ci ? `95% CI ${pct(ci[0])}–${pct(ci[1])}` : "";
  const warn = d.representative
    ? ""
    : `<p class="trust-warn">NON-REPRESENTATIVE (stub run) — not publishable proof.</p>`;

  const m = d.manifest;
  const rows = [
    ["generator", m.generator_name],
    ["embedder", m.embedder_name],
    ["reranker", m.reranker_name],
    ["judge", m.judge_name],
    ["provider", m.provider],
    ["prompt hash", m.prompt_version_hash],
    ["git sha", m.git_sha],
    ["dataset hash", m.dataset_hash],
    ["n questions", m.n_questions],
    ["run (UTC)", m.run_timestamp_utc],
  ]
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(String(v))}</td></tr>`)
    .join("");

  return (
    warn +
    `<div class="trust-metrics">` +
    `<div class="tm"><span class="tm-lbl">CITATION ACCURACY</span>` +
    `<span class="tm-val">${esc(pct(c.precision))}</span>` +
    `<span class="tm-sub">N=${esc(String(c.n_answered ?? "—"))}</span></div>` +
    `<div class="tm"><span class="tm-lbl">FAITHFULNESS</span>` +
    `<span class="tm-val">${esc(pct(f.pass_rate))}</span>` +
    `<span class="tm-sub tm-ci">${esc(band)}</span></div>` +
    `</div>` +
    `<div class="trust-manifest"><div class="trust-mlbl">EVAL MANIFEST</div>` +
    `<table>${rows}</table></div>`
  );
}

// --- error surface (Story 2.8) — pure; DOM wrapper + retry in app.js ---

/** The error banner inner HTML (Story 2.8, UX-DR13): mono `⚠ <LABEL>` (e.g.
 * `RETRIEVAL FAILED`), a plain message, and a `⏎ RETRY` control. Pure + escaped.
 * Visually distinct from a refusal — a terracotta *alert* rail + `role="alert"`
 * come from the `.errbanner` wrapper (app.js); a refusal is a neutral
 * `role="status"`. An error is a failure to answer, not an honest refusal. */
export function errorBannerHTML(label, message) {
  return (
    `<div class="errlbl">⚠ ${esc(label)}</div>` +
    `<p>${esc(message)}</p>` +
    `<button type="button" class="retry">⏎ RETRY</button>`
  );
}

// --- honest refusal (Story 2.6) — pure; DOM wrapper in app.js ---

/** `WHAT I DO HAVE` list items from the covered corpus: `AAPL — Apple Inc.`,
 * capped at `max`. This is the honest fallback when a query is out-of-corpus —
 * a refused answer has no citations (AD-10), so "what I do have" is the corpus
 * scope, not fabricated adjacent passages. */
export function corpusHaveList(companies, max = 6) {
  return (companies ?? [])
    .filter((c) => c && c.in_corpus && c.ticker)
    .slice(0, max)
    .map((c) => `${String(c.ticker).toUpperCase()} — ${c.name ?? c.ticker}`);
}

/** The refusal banner inner HTML (Story 2.6, UX-DR12/FR-B4): mono
 * `⊘ INSUFFICIENT EVIDENCE`, the echoed query, a plain reason, and a
 * `WHAT I DO HAVE:` list. Pure + escaped. Sober information, not an error —
 * the neutral rail + `role="status"` come from the `.refusal` wrapper (app.js).
 * `have` is a list of plain strings (e.g. from `corpusHaveList`). */
export function refusalBannerHTML(query, reason, have) {
  const items = (have ?? []).map((h) => `· ${esc(h)}`).join("<br>");
  return (
    `<div class="rlbl">⊘ INSUFFICIENT EVIDENCE — not enough in the corpus to answer that</div>` +
    `<div class="rq">&gt; ${esc(query)}</div>` +
    `<p>${esc(reason)}</p>` +
    (items ? `<div class="have"><b>WHAT I DO HAVE:</b><br>${items}</div>` : "")
  );
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
      const label = citationChipLabel(cit);
      // A real <button> (phrasing content, valid in <p>) → native Enter/Space
      // activation + focusability, no role/tabindex/keydown scaffolding (2.3/2.8).
      html +=
        `<button type="button" class="chip" data-chunk-id="${esc(cit.chunk_id)}"` +
        ` aria-label="View source ${esc(label)}">${esc(label)}</button>`;
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

// --- source drill-down panel (Story 2.3) — pure helpers, DOM lives in panel.js ---

/** The panel's per-source locator line: `NWL · FY2024 · ITEM 1A`. The corpus
 * has no filing-form type or filename per citation, so this is company + fiscal
 * year + item code (uppercased) — honest to the data, not the mockup's
 * `NWL_10-K_2024.pdf`. */
export function sourceDocLabel(cit) {
  const parts = [cit?.company, cit?.fiscal_year != null ? `FY${cit.fiscal_year}` : null];
  const item = String(cit?.item_code ?? "").trim().toUpperCase();
  if (item) parts.push(item);
  return parts.filter(Boolean).join(" · ");
}

/** `rerank 0.94` from a numeric score, or "" when no score is available (the
 * panel omits the line rather than showing a fake number). */
export function formatRerankScore(score) {
  return Number.isFinite(score) ? `rerank ${Number(score).toFixed(2)}` : "";
}

/** De-duplicate citations by `chunk_id`, preserving first-seen order — the panel
 * lists each cited source once even when several sections cite it. */
export function dedupeSources(citations) {
  const seen = new Set();
  const out = [];
  for (const c of citations ?? []) {
    if (!c || !c.chunk_id || seen.has(c.chunk_id)) continue;
    seen.add(c.chunk_id);
    out.push(c);
  }
  return out;
}

/** The panel-head count: `2 OF 5 · [FY24 · 1A]` when a source is pinned (1-based
 * position), else the collapsed `N SOURCES` state (UX-DR6/DR8). */
export function panelCountLabel(pinnedPos, total, chipLabel) {
  if (pinnedPos && pinnedPos >= 1) return `${pinnedPos} OF ${total} · ${chipLabel}`;
  return `${total} SOURCE${total === 1 ? "" : "S"}`;
}

// A short single-line snippet for a collapsed source row (~120 chars).
function snippet(text) {
  const t = String(text ?? "").replace(/\s+/g, " ").trim();
  return t.length > 120 ? `${t.slice(0, 118)}…` : t;
}

/** Build the full source-panel innerHTML (head + one row per source). Pure so
 * the escaping and the `<mark>` markup are unit-tested without a browser; the
 * DOM controller (panel.js) owns only class-toggling, listeners, and focus.
 *
 * `sources` is `[{cit, score}]` (unique, ordered); `pinnedId` is the expanded
 * chunk_id or null. Every corpus/LLM string is escaped. The pinned row shows the
 * locator + rerank score + full passage with the supporting span in a teal
 * `<mark>` (the whole cited chunk is the honest support — `char_span_in_section`
 * indexes the section, not this excerpt, so a sub-span can't be located here). */
export function sourcePanelHTML(sources, pinnedId) {
  const list = sources ?? [];
  const pos = pinnedId ? list.findIndex((s) => s.cit.chunk_id === pinnedId) + 1 : 0;
  const pinnedCit = pos >= 1 ? list[pos - 1].cit : null;
  const count = panelCountLabel(pos, list.length, pinnedCit ? citationChipLabel(pinnedCit) : "");

  const rows = list
    .map(({ cit, score }) => {
      const chip = esc(citationChipLabel(cit));
      if (cit.chunk_id === pinnedId) {
        const relev = formatRerankScore(score);
        return (
          `<div class="src expanded"><div class="srchead">` +
          `<span class="doc">${esc(sourceDocLabel(cit))}</span>` +
          (relev ? `<span class="relev">${esc(relev)}</span>` : "") +
          `</div><div class="passage" tabindex="-1" data-passage>` +
          `“<mark>${esc(cit.text)}</mark>”</div></div>`
        );
      }
      return (
        `<button type="button" class="src collapsed" data-chunk-id="${esc(cit.chunk_id)}"` +
        ` aria-label="Expand source ${chip}"><div class="srchead">` +
        `<span class="srctitle">${esc(cit.item_title || cit.item_code || "Source")}</span>` +
        `<span class="chev">▸ ${chip}</span></div>` +
        `<div class="snippet">${esc(snippet(cit.text))}</div></button>`
      );
    })
    .join("");

  return (
    `<div class="panel-head"><span class="lbl">SOURCE</span>` +
    `<span class="count">${esc(count)}</span></div>${rows}`
  );
}

// --- Q&A drill-down thread (Story 2.4) — pure helpers, DOM lives in app.js ---

/** `GROUNDED · 3 passages · 2 filings` from an answer's citations. A "filing" is
 * a unique (company, fiscal_year) pair; "passages" = citation count. Returns ""
 * when there are no citations (nothing to ground — a refusal). */
export function groundedLabel(citations) {
  const cites = citations ?? [];
  if (cites.length === 0) return "";
  const filings = new Set(cites.map((c) => `${c.company}|${c.fiscal_year}`)).size;
  const p = cites.length === 1 ? "passage" : "passages";
  const f = filings === 1 ? "filing" : "filings";
  return `GROUNDED · ${cites.length} ${p} · ${filings} ${f}`;
}

/** 1–3 cited next-question suggestions (UX-DR14) derived from the answer's
 * distinct citation item titles + the company — deterministic, grounded in the
 * sources actually retrieved (not free-invented). Empty on a refusal. */
export function suggestQuestions(answer, company) {
  if (!answer || answer.refused) return [];
  const who = company || "this company";
  const titles = [];
  for (const c of answer.citations ?? []) {
    const t = String(c.item_title || "").trim();
    if (t && !titles.includes(t)) titles.push(t);
    if (titles.length === 3) break;
  }
  return titles.map((t) => `How did ${who}'s ${t.toLowerCase()} change year over year?`);
}

/** Multi-hop badge (Story 2.5, UX-DR11): when an answer's citations combine ≥2
 * distinct filings, label the synthesis `MULTI-HOP · CROSS-COMPANY`/`CROSS-PERIOD`
 * (both when it spans companies AND periods). A "filing" is one company×fiscal
 * year. Empty for a single-filing answer — no false multi-hop claim. This is a
 * read-out of what the fixed hybrid retrieval already combined (AD-9, FR-B7);
 * it changes no retrieval behaviour. */
export function multiHopBadge(citations) {
  const cites = citations ?? [];
  const companies = new Set(cites.map((c) => c.company)).size;
  const years = new Set(cites.map((c) => c.fiscal_year)).size;
  const filings = new Set(cites.map((c) => `${c.company}|${c.fiscal_year}`)).size;
  if (filings < 2) return "";
  const parts = [];
  if (companies >= 2) parts.push("CROSS-COMPANY");
  if (years >= 2) parts.push("CROSS-PERIOD");
  return parts.length ? `MULTI-HOP · ${parts.join(" · ")}` : "MULTI-HOP";
}

/** Real grounding ratio for the confidence signal (Story 2.7): `{cited, total}`
 * where `total` = sentences in the answer and `cited` = sentences carrying ≥1
 * in-set `[chunk_id]` citation. This is the honest, computable "claims cited"
 * count (the synthesis prompt requires every sentence cited); `total: 0` means
 * no signal should render. */
export function claimsCited(text, citations) {
  const ids = new Set((citations ?? []).map((c) => c.chunk_id));
  const sentences = String(text ?? "")
    .split(/(?<=[.!?])\s+/)
    .filter((s) => s.trim());
  const re = /\[([A-Za-z0-9._-]+)\]/g;
  let cited = 0;
  for (const s of sentences) {
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(s)) !== null) {
      if (ids.has(m[1])) {
        cited += 1;
        break;
      }
    }
  }
  return { cited, total: sentences.length };
}

/** The confidence signal (Story 2.7, UX-DR7/FR-B6): `CONFIDENCE HIGH` (teal
 * category) + a 64×5px 3-level bar over an `accent-dim` track (the CI-band
 * shade) + `· N/M CLAIMS CITED`. NEVER shown without the claims-cited count,
 * and never for a refused answer.
 *
 * HONESTY (AC-2): the runtime signal is the LLM's *categorical* self-report
 * (`high`/`medium`/`low`) — there is no calibrated 0–1 score. Rendering the
 * mockup's `0.91` would assert a calibration Epic 3 (FR-C5) has not yet proven,
 * which AC-2 forbids. So we show the honest category + the *real* grounding
 * ratio, not a fabricated decimal. The bar is a coarse 3-level visual, not a
 * claimed percentage. */
export function confidenceSignalHTML(answer) {
  const a = answer ?? {};
  if (a.refused) return "";
  const level = a.confidence || "medium";
  const { cited, total } = claimsCited(a.text, a.citations);
  if (!total) return ""; // never without a claims-cited count
  return (
    `<div class="confidence" role="img" ` +
    `aria-label="Confidence ${esc(level)}, ${cited} of ${total} claims cited">` +
    `<span class="clabel">CONFIDENCE <b>${esc(level.toUpperCase())}</b></span>` +
    `<span class="cbar" aria-hidden="true"><span class="cfill lvl-${esc(level)}"></span></span>` +
    `<span class="cclaims">· ${cited}/${total} CLAIMS CITED</span></div>`
  );
}

/** The Q&A answer body HTML (Story 2.4/2.5): the `DOCINTEL` label (+ a multi-hop
 * badge when the answer spans filings), the cited prose, and the `GROUNDED`
 * footer. Pure + escaped (chips via citedTextToHTML). A refused answer renders
 * its text plainly with no badge/footer (the full refusal banner is Story 2.6). */
export function qaAnswerHTML(answer) {
  const a = answer ?? {};
  const prose = a.refused
    ? `<p class="section-refused">${esc(a.text)}</p>`
    : `<p>${citedTextToHTML(a.text, a.citations)}</p>`;
  const grounded = a.refused ? "" : groundedLabel(a.citations);
  const badge = a.refused ? "" : multiHopBadge(a.citations);
  return (
    `<div class="albl"><span class="d"></span> DOCINTEL` +
    (badge ? ` <span class="multihop">⤳ ${esc(badge)}</span>` : "") +
    `</div>${prose}` +
    (grounded ? `<div class="grounded"><b>GROUNDED</b>${esc(grounded.replace(/^GROUNDED/, ""))}</div>` : "") +
    confidenceSignalHTML(a)
  );
}
