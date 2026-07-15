// docintel analyst workspace — bootstrap + state machine (Story 2.1).
// Talks to the API over HTTP only (AD-15): GET /coverage here; the brief stream
// (2.2), source panel (2.3), Q&A (2.4), refusal (2.6) attach at the marked seams.
import { parseCommand, formatScopeLabel, coveredTickers, isCovered } from "/lib.js";

const $ = (sel) => document.querySelector(sel);
const view = $("#view");
const input = $("#command-input");
const scopeLabel = $("#scope-label");
const announcer = $("#announcer");

// Announce a state transition to assistive tech via the dedicated live region,
// and move focus to the newly-rendered heading so keyboard/AT users land on the
// new content (the old focused element — e.g. a ticker-hint button — was just
// destroyed by the innerHTML swap).
function transition(message) {
  if (announcer) announcer.textContent = message;
  const heading = view.querySelector("[data-focus]");
  if (heading) heading.focus();
}

// Escape any text that originates from the user or the corpus before it reaches
// innerHTML. The command echo + ticker are user-controlled — never trust them.
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );
}

// --- coverage state (loaded once on boot) ---
let companies = [];
let corpus = null;

async function loadCoverage() {
  try {
    const res = await fetch("/coverage", { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`/coverage ${res.status}`);
    const data = await res.json();
    corpus = data.corpus;
    companies = data.companies ?? [];
    scopeLabel.textContent = formatScopeLabel(corpus);
    renderEmpty();
  } catch (err) {
    // Retrieval-failure surface is hardened in Story 2.8; a legible fallback now.
    scopeLabel.textContent = "CORPUS · UNAVAILABLE";
    view.innerHTML = `<div class="empty"><h1>Coverage unavailable</h1>
      <p>Could not reach the corpus. Is the API running?</p></div>`;
    console.error(err);
  }
}

// --- views (the state machine swaps #view) ---

function renderEmpty() {
  const hints = coveredTickers(companies)
    .slice(0, 8)
    .map((t) => `<button class="ticker-hint" type="button" data-ticker="${esc(t)}">${esc(t)}</button>`)
    .join("");
  view.innerHTML = `
    <div class="empty">
      <h1>Ask a company.</h1>
      <p>Type a ticker for a cited brief, or a question for a cited answer.</p>
      <div class="hint">COVERED</div>
      <div class="ticker-hints">${hints || '<span class="hint">no companies indexed</span>'}</div>
    </div>`;
  for (const b of view.querySelectorAll(".ticker-hint")) {
    b.addEventListener("click", () => submitCommand(b.dataset.ticker));
  }
}

// Covered ticker → generating-brief placeholder. The real streamed sections land
// in Story 2.2 (this is the transition target required by AC-2 / UX-DR16).
function renderGenerating(ticker) {
  // Guard every row's ticker — a declared-but-unindexed filer may lack one.
  const company =
    companies.find((c) => String(c.ticker ?? "").toUpperCase() === ticker) ?? { name: ticker, ticker };
  const SECTIONS = ["Business & moat", "Financial trajectory", "Risk factors", "Recent material events"];
  const cards = SECTIONS.map(
    (title) => `
      <div class="card pending">
        <p class="eyebrow"><span class="tick"></span> ${esc(title).toUpperCase()}
          <span class="state">QUEUED</span></p>
        <h2>${esc(title)}</h2>
        <div class="ph-line w1"></div><div class="ph-line w2"></div><div class="ph-line w3"></div>
      </div>`,
  ).join("");
  view.innerHTML = `
    <div class="titlerow">
      <h1 tabindex="-1" data-focus>${esc(company.name)}</h1>
      <div class="genstate"><span class="spin"></span> GENERATING <b>· LIVE</b></div>
    </div>
    <div class="stack">${cards}</div>`;
  transition(`Generating brief for ${company.name}`);
  // TODO(2.2): open the brief stream (EventSource/fetch-stream) and fill sections.
}

// Uncovered ticker → refusal path (AC-3). Minimal, sober stub; the full banner
// (REFUSAL_TEXT_SENTINEL, WHAT-I-DO-HAVE cited list) is Story 2.6.
function renderRefusalStub(ticker) {
  view.innerHTML = `
    <div class="refusal" role="status">
      <div class="rlbl" tabindex="-1" data-focus>⊘ INSUFFICIENT EVIDENCE — not in the covered corpus</div>
      <div class="rq">&gt; brief ${esc(ticker)}</div>
      <p>${esc(ticker)} is not among the indexed filers, so there is nothing to ground a brief on.</p>
    </div>`;
  transition(`No coverage for ${ticker}`);
  // TODO(2.6): full refusal banner + WHAT-I-DO-HAVE list from the API refusal path.
}

// --- command routing ---
function submitCommand(raw) {
  const cmd = parseCommand(raw, coveredTickers(companies));
  if (!cmd) return;
  if (cmd.intent === "brief") {
    if (isCovered(cmd.ticker, companies)) renderGenerating(cmd.ticker);
    else renderRefusalStub(cmd.ticker);
  } else {
    // TODO(2.4): route free-text questions to the Q&A thread over POST /query.
    renderGenerating(cmd.question); // placeholder until Q&A lands
  }
}

// --- theme (dark default; light co-equal, persisted) ---
// The saved theme is applied pre-paint by an inline script in index.html (no
// flash-of-wrong-theme); here we only keep the toggle's accessible state in sync.
function initTheme() {
  const toggle = $("#theme-toggle");
  const sync = () => {
    toggle.setAttribute("aria-pressed", String(document.documentElement.getAttribute("data-theme") === "light"));
  };
  sync();
  toggle.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("docintel-theme", next);
    sync();
  });
}

// --- boot ---
$("#command-bar").addEventListener("submit", (e) => {
  e.preventDefault();
  submitCommand(input.value);
});
initTheme();
input.focus();
loadCoverage();
