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
