// Pure-logic tests for the command bar. Run: `node --test tests/frontend/`.
// Uses node:test / node:assert only — no npm install. Lives OUTSIDE web/ so the
// static mount never serves test source at a public URL.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseCommand,
  formatScopeLabel,
  coveredTickers,
  isCovered,
  esc,
  citationChipLabel,
  citedTextToHTML,
  sourceDocLabel,
  formatRerankScore,
  dedupeSources,
  panelCountLabel,
  sourcePanelHTML,
  groundedLabel,
  suggestQuestions,
  qaAnswerHTML,
  multiHopBadge,
  corpusHaveList,
  refusalBannerHTML,
  claimsCited,
  confidenceSignalHTML,
  errorBannerHTML,
} from "../../web/lib.js";

const COVERED = ["NWL", "AAPL", "BRK.B"];

test("parseCommand: brief-prefixed ticker (explicit → brief regardless of coverage)", () => {
  assert.deepEqual(parseCommand("brief NWL"), { intent: "brief", ticker: "NWL" });
  assert.deepEqual(parseCommand("BRIEF nwl"), { intent: "brief", ticker: "NWL" });
  assert.deepEqual(parseCommand("brief TSLA"), { intent: "brief", ticker: "TSLA" }); // uncovered → router refuses
  assert.deepEqual(parseCommand("brief brk.b"), { intent: "brief", ticker: "BRK.B" });
});

test("parseCommand: 'brief' + a sentence is a question, not a ticker", () => {
  assert.equal(parseCommand("brief me on how margins moved").intent, "ask");
});

test("parseCommand: bare covered ticker (any case) → brief", () => {
  assert.deepEqual(parseCommand("NWL", COVERED), { intent: "brief", ticker: "NWL" });
  assert.deepEqual(parseCommand("nwl", COVERED), { intent: "brief", ticker: "NWL" });
  assert.deepEqual(parseCommand("brk.b", COVERED), { intent: "brief", ticker: "BRK.B" });
});

test("parseCommand: bare all-uppercase uncovered token → brief attempt (→ refusal downstream)", () => {
  assert.deepEqual(parseCommand("TSLA", COVERED), { intent: "brief", ticker: "TSLA" });
});

test("parseCommand: lowercase/mixed everyday words are questions, not tickers", () => {
  for (const w of ["sales", "risks", "trend", "cash", "Apple", "brief"]) {
    assert.equal(parseCommand(w, COVERED).intent, "ask", `${w} should be ask`);
  }
});

test("parseCommand: natural-language question → ask", () => {
  const r = parseCommand("how did gross margin move in FY24?", COVERED);
  assert.equal(r.intent, "ask");
  assert.equal(r.question, "how did gross margin move in FY24?");
});

test("parseCommand: empty / whitespace / nullish → null", () => {
  assert.equal(parseCommand(""), null);
  assert.equal(parseCommand("   "), null);
  assert.equal(parseCommand(null), null);
  assert.equal(parseCommand(undefined), null);
});

test("formatScopeLabel: full span (two-digit FY, matches mockup)", () => {
  assert.equal(
    formatScopeLabel({ company_count: 14, fy_min: 2022, fy_max: 2024 }),
    "CORPUS · 14 FILERS · FY22–FY24",
  );
});

test("formatScopeLabel: singular filer + single-year span", () => {
  assert.equal(
    formatScopeLabel({ company_count: 1, fy_min: 2024, fy_max: 2024 }),
    "CORPUS · 1 FILER · FY24",
  );
});

test("formatScopeLabel: missing years collapse to filer count", () => {
  assert.equal(formatScopeLabel({ company_count: 5, fy_min: null, fy_max: null }), "CORPUS · 5 FILERS");
  assert.equal(formatScopeLabel({}), "CORPUS · 0 FILERS");
  assert.equal(formatScopeLabel(null), "CORPUS · 0 FILERS");
});

const COMPANIES = [
  { ticker: "NWL", in_corpus: true },
  { ticker: "aapl", in_corpus: true },
  { ticker: "GHOST", in_corpus: false }, // declared scope but not indexed
  { in_corpus: true }, // malformed row: in_corpus but no ticker
];

test("coveredTickers: only in_corpus rows with a ticker, uppercased (no UNDEFINED)", () => {
  assert.deepEqual(coveredTickers(COMPANIES), ["NWL", "AAPL"]);
  assert.deepEqual(coveredTickers(null), []);
});

test("isCovered: case-insensitive, excludes not-in-corpus and malformed", () => {
  assert.equal(isCovered("nwl", COMPANIES), true);
  assert.equal(isCovered("AAPL", COMPANIES), true);
  assert.equal(isCovered("GHOST", COMPANIES), false); // in_corpus:false → not answerable
  assert.equal(isCovered("ZZZZ", COMPANIES), false);
  assert.equal(isCovered("", COMPANIES), false);
  assert.equal(isCovered(null, COMPANIES), false);
});

test("esc: escapes the five HTML metacharacters", () => {
  assert.equal(esc(`<a href="x">&'`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
  assert.equal(esc(null), "");
});

test("citationChipLabel: FY + item code (Item stripped)", () => {
  assert.equal(citationChipLabel({ fiscal_year: 2024, item_code: "Item 1A" }), "[FY24 · 1A]");
  assert.equal(citationChipLabel({ fiscal_year: 2023, item_code: "Item 7" }), "[FY23 · 7]");
  assert.equal(citationChipLabel({ fiscal_year: 2024, item_code: "" }), "[FY24]");
});

test("citedTextToHTML: inline chips from known ids, prose escaped", () => {
  const citations = [{ chunk_id: "AAPL-FY2024-Item-1A-018", fiscal_year: 2024, item_code: "Item 1A" }];
  const html = citedTextToHTML("Risk is <high> here [AAPL-FY2024-Item-1A-018].", citations);
  assert.match(html, /Risk is &lt;high&gt; here/); // prose escaped
  // Native <button> chip (Story 2.3) with an aria-label + data-chunk-id.
  assert.match(
    html,
    /<button type="button" class="chip" data-chunk-id="AAPL-FY2024-Item-1A-018" aria-label="View source \[FY24 · 1A\]">\[FY24 · 1A\]<\/button>/,
  );
});

test("citedTextToHTML: hallucinated chunk-id-shaped token dropped, no orphan space (AD-10)", () => {
  const html = citedTextToHTML("Claim [GHOST-FY2099-Item-9-999].", []);
  assert.equal(html, "Claim."); // dropped WITH its leading space
  assert.doesNotMatch(html, /span/);
});

test("citedTextToHTML: legitimate bracketed prose is preserved, not eaten", () => {
  assert.equal(citedTextToHTML("the filing [sic] states x.", []), "the filing [sic] states x.");
  assert.equal(citedTextToHTML("see note [1] here.", []), "see note [1] here.");
});

test("citedTextToHTML: no citations / empty text is safe", () => {
  assert.equal(citedTextToHTML("", []), "");
  assert.equal(citedTextToHTML(null, null), "");
});

// --- source drill-down panel helpers (Story 2.3) ---

test("sourceDocLabel: company · FY · ITEM (uppercased), missing item collapses", () => {
  assert.equal(
    sourceDocLabel({ company: "Apple Inc.", fiscal_year: 2024, item_code: "Item 1A" }),
    "Apple Inc. · FY2024 · ITEM 1A",
  );
  assert.equal(sourceDocLabel({ company: "Apple Inc.", fiscal_year: 2024 }), "Apple Inc. · FY2024");
});

test("formatRerankScore: 2dp when finite, empty string otherwise (no fake number)", () => {
  assert.equal(formatRerankScore(0.9412), "rerank 0.94");
  assert.equal(formatRerankScore(1), "rerank 1.00");
  assert.equal(formatRerankScore(undefined), "");
  assert.equal(formatRerankScore(NaN), "");
});

test("dedupeSources: unique by chunk_id, first-seen order, drops falsy/id-less", () => {
  const out = dedupeSources([
    { chunk_id: "A" },
    { chunk_id: "B" },
    { chunk_id: "A" }, // dup
    null,
    { fiscal_year: 2024 }, // no chunk_id
  ]);
  assert.deepEqual(out.map((c) => c.chunk_id), ["A", "B"]);
});

test("panelCountLabel: pinned shows N OF M · chip; unpinned shows N SOURCES", () => {
  assert.equal(panelCountLabel(2, 5, "[FY24 · 1A]"), "2 OF 5 · [FY24 · 1A]");
  assert.equal(panelCountLabel(0, 5, ""), "5 SOURCES");
  assert.equal(panelCountLabel(0, 1, ""), "1 SOURCE");
});

const SRC = (over = {}) => ({
  cit: {
    chunk_id: "AAPL-FY2024-Item-1A-018",
    company: "Apple Inc.",
    fiscal_year: 2024,
    item_code: "Item 1A",
    item_title: "Risk Factors",
    text: "Multi-year contracts covered 68% of revenue in fiscal 2024.",
    ...over.cit,
  },
  score: over.score,
});

test("sourcePanelHTML: nothing pinned → head count + collapsed button rows only", () => {
  const html = sourcePanelHTML([SRC({ score: 0.94 })], null);
  assert.match(html, /<span class="count">1 SOURCE<\/span>/);
  assert.match(html, /<button type="button" class="src collapsed" data-chunk-id="AAPL-FY2024-Item-1A-018"/);
  assert.match(html, /Risk Factors/); // item_title as the collapsed row title
  assert.doesNotMatch(html, /<mark>/); // no expanded passage until pinned
});

test("sourcePanelHTML: pinned row → locator, rerank score, passage in a <mark>", () => {
  const html = sourcePanelHTML([SRC({ score: 0.94 })], "AAPL-FY2024-Item-1A-018");
  assert.match(html, /1 OF 1 · \[FY24 · 1A\]/); // pinned count
  assert.match(html, /class="doc">Apple Inc\. · FY2024 · ITEM 1A</); // locator
  assert.match(html, /class="relev">rerank 0\.94</); // rerank score
  assert.match(html, /<mark>Multi-year contracts covered 68% of revenue in fiscal 2024\.<\/mark>/);
  assert.match(html, /data-passage/); // focus target
});

test("sourcePanelHTML: no score → the rerank line is omitted, not faked", () => {
  const html = sourcePanelHTML([SRC({ score: undefined })], "AAPL-FY2024-Item-1A-018");
  assert.doesNotMatch(html, /relev/);
});

test("sourcePanelHTML: malicious company/passage is escaped (XSS)", () => {
  const evil = SRC({
    cit: { text: "<img src=x onerror=alert(1)>", company: "<script>alert(1)</script>" },
    score: 0.5,
  });
  const html = sourcePanelHTML([evil], "AAPL-FY2024-Item-1A-018");
  assert.doesNotMatch(html, /<img|<script>/); // no live markup injected
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/); // passage escaped inside <mark>
});

// --- Q&A drill-down thread helpers (Story 2.4) ---

const ANS = (over = {}) => ({
  text: "Revenue rose [AAPL-FY2024-Item-8-006].",
  citations: [
    { chunk_id: "AAPL-FY2024-Item-8-006", company: "Apple Inc.", fiscal_year: 2024, item_code: "Item 8", item_title: "Financial Statements" },
    { chunk_id: "AAPL-FY2023-Item-8-006", company: "Apple Inc.", fiscal_year: 2023, item_code: "Item 8", item_title: "Financial Statements" },
  ],
  confidence: "high",
  refused: false,
  ...over,
});

test("groundedLabel: passages + distinct filings, plural-aware, empty on no citations", () => {
  assert.equal(groundedLabel(ANS().citations), "GROUNDED · 2 passages · 2 filings");
  assert.equal(
    groundedLabel([{ company: "Apple Inc.", fiscal_year: 2024 }]),
    "GROUNDED · 1 passage · 1 filing",
  );
  assert.equal(groundedLabel([]), "");
});

test("suggestQuestions: ≤3 from distinct item titles + company; empty on refusal", () => {
  const qs = suggestQuestions(ANS(), "Apple Inc.");
  assert.equal(qs.length, 1); // both citations share one item_title → deduped
  assert.match(qs[0], /Apple Inc\.'s financial statements change year over year/);
  assert.deepEqual(suggestQuestions({ refused: true, text: "no" }, "Apple Inc."), []);
});

test("qaAnswerHTML: DOCINTEL label + cited prose + GROUNDED footer; escapes prose", () => {
  const html = qaAnswerHTML(ANS({ text: "x <b>y</b> [AAPL-FY2024-Item-8-006]." }));
  assert.match(html, /class="albl"/);
  assert.match(html, /x &lt;b&gt;y&lt;\/b&gt;/); // prose escaped
  assert.match(html, /<button type="button" class="chip"/); // inline chip
  assert.match(html, /<b>GROUNDED<\/b> · 2 passages · 2 filings/);
});

test("qaAnswerHTML: refused answer → plain text, no chips, no GROUNDED footer", () => {
  const html = qaAnswerHTML({ refused: true, text: "I cannot answer from the corpus.", citations: [] });
  assert.match(html, /section-refused/);
  assert.doesNotMatch(html, /GROUNDED/);
  assert.doesNotMatch(html, /class="chip"/);
});

// --- multi-hop / cross-document synthesis (Story 2.5) ---

test("multiHopBadge: single filing → empty (no false multi-hop claim)", () => {
  assert.equal(
    multiHopBadge([
      { company: "Apple Inc.", fiscal_year: 2024 },
      { company: "Apple Inc.", fiscal_year: 2024 },
    ]),
    "",
  );
});

test("multiHopBadge: distinct years same company → CROSS-PERIOD", () => {
  const b = multiHopBadge([
    { company: "Microsoft Corporation", fiscal_year: 2023 },
    { company: "Microsoft Corporation", fiscal_year: 2024 },
  ]);
  assert.equal(b, "MULTI-HOP · CROSS-PERIOD");
});

test("multiHopBadge: distinct companies AND years → CROSS-COMPANY · CROSS-PERIOD", () => {
  const b = multiHopBadge([
    { company: "Apple Inc.", fiscal_year: 2023 },
    { company: "Microsoft Corporation", fiscal_year: 2024 },
  ]);
  assert.equal(b, "MULTI-HOP · CROSS-COMPANY · CROSS-PERIOD");
});

test("qaAnswerHTML: multi-hop answer shows the ⤳ badge; single-filing does not", () => {
  const multi = qaAnswerHTML(ANS({
    citations: [
      { chunk_id: "MSFT-FY2023-Item-7-001", company: "Microsoft Corporation", fiscal_year: 2023, item_title: "MD&A" },
      { chunk_id: "MSFT-FY2024-Item-7-001", company: "Microsoft Corporation", fiscal_year: 2024, item_title: "MD&A" },
    ],
    text: "R&D rose [MSFT-FY2023-Item-7-001] [MSFT-FY2024-Item-7-001].",
  }));
  assert.match(multi, /class="multihop">⤳ MULTI-HOP · CROSS-PERIOD</);
  // single-filing answer (one company, one year) → no badge
  const single = qaAnswerHTML(ANS({
    citations: [{ chunk_id: "AAPL-FY2024-Item-8-006", company: "Apple Inc.", fiscal_year: 2024, item_title: "Financials" }],
    text: "Revenue rose [AAPL-FY2024-Item-8-006].",
  }));
  assert.doesNotMatch(single, /multihop/);
});

// --- honest refusal banner (Story 2.6) ---

test("corpusHaveList: TICKER — Name for covered filers only, capped", () => {
  const out = corpusHaveList(
    [
      { ticker: "aapl", name: "Apple Inc.", in_corpus: true },
      { ticker: "MSFT", name: "Microsoft Corporation", in_corpus: true },
      { ticker: "ZZZZ", name: "Not Indexed", in_corpus: false }, // dropped
      { name: "No Ticker", in_corpus: true }, // dropped
    ],
    1,
  );
  assert.deepEqual(out, ["AAPL — Apple Inc."]); // capped to 1, uppercased, in_corpus only
});

test("refusalBannerHTML: label + echoed query + reason + WHAT I DO HAVE, escaped", () => {
  const html = refusalBannerHTML("brief TSLA", "TSLA is not indexed.", ["AAPL — Apple Inc."]);
  assert.match(html, /⊘ INSUFFICIENT EVIDENCE/);
  assert.match(html, /class="rq">&gt; brief TSLA</); // echoed query, > escaped
  assert.match(html, /<p>TSLA is not indexed\.<\/p>/);
  assert.match(html, /<b>WHAT I DO HAVE:<\/b>.*· AAPL — Apple Inc\./s);
});

test("refusalBannerHTML: no corpus → WHAT I DO HAVE omitted; malicious query escaped", () => {
  const html = refusalBannerHTML("<img src=x onerror=alert(1)>", "reason", []);
  assert.doesNotMatch(html, /WHAT I DO HAVE/);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x/);
});

// --- confidence signal (Story 2.7) ---

test("claimsCited: counts sentences with an in-set citation vs total sentences", () => {
  const cits = [{ chunk_id: "A-FY2024-Item-8-1" }, { chunk_id: "A-FY2024-Item-1A-2" }];
  const r = claimsCited(
    "Revenue rose [A-FY2024-Item-8-1]. Margins held. Risks grew [A-FY2024-Item-1A-2].",
    cits,
  );
  assert.deepEqual(r, { cited: 2, total: 3 }); // 3 sentences, 2 carry a valid cite
  assert.deepEqual(claimsCited("", []), { cited: 0, total: 0 });
});

test("confidenceSignalHTML: honest CATEGORY (not a fabricated decimal) + real N/M", () => {
  const html = confidenceSignalHTML({
    confidence: "high",
    refused: false,
    text: "Revenue rose [A-FY2024-Item-8-1]. Margins held.",
    citations: [{ chunk_id: "A-FY2024-Item-8-1" }],
  });
  assert.match(html, /CONFIDENCE <b>HIGH<\/b>/); // category, not "0.91"
  assert.doesNotMatch(html, /0\.\d/); // AC-2: no fabricated calibrated decimal
  assert.match(html, /· 1\/2 CLAIMS CITED/); // real grounding ratio
  assert.match(html, /class="cfill lvl-high"/); // 3-level bar
  assert.match(html, /aria-label="Confidence high, 1 of 2 claims cited"/);
});

test("confidenceSignalHTML: never shown for a refusal, nor without a claims count", () => {
  assert.equal(confidenceSignalHTML({ refused: true, text: "no", citations: [] }), "");
  assert.equal(confidenceSignalHTML({ refused: false, text: "", citations: [] }), ""); // total 0 → no signal
});

// --- error banner (Story 2.8) ---

test("errorBannerHTML: mono label + message + RETRY, escaped, distinct from refusal", () => {
  const html = errorBannerHTML("RETRIEVAL FAILED", "The <brief> failed.");
  assert.match(html, /⚠ RETRIEVAL FAILED/);
  assert.match(html, /<p>The &lt;brief&gt; failed\.<\/p>/); // message escaped
  assert.match(html, /<button type="button" class="retry">⏎ RETRY<\/button>/);
  assert.doesNotMatch(html, /INSUFFICIENT EVIDENCE/); // not a refusal
});
