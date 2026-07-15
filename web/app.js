// docintel analyst workspace — bootstrap + state machine (Story 2.1).
// Talks to the API over HTTP only (AD-15): GET /coverage here; the brief stream
// (2.2), source panel (2.3), Q&A (2.4), refusal (2.6) attach at the marked seams.
import {
  parseCommand,
  formatScopeLabel,
  coveredTickers,
  isCovered,
  esc,
  citedTextToHTML,
} from "/lib.js";
import { streamBrief } from "/brief.js";
import { createPanel } from "/panel.js";

const $ = (sel) => document.querySelector(sel);
const view = $("#view");
const input = $("#command-input");
const scopeLabel = $("#scope-label");
const announcer = $("#announcer");

let activeStream = null; // the in-flight brief EventSource, if any

// Source drill-down panel (Story 2.3). Pinning from a source row syncs the
// inline chip's active state; dismissing clears it.
const panel = createPanel($("#source-panel"), {
  onPin: (id) => setActiveChip(id),
  onDismiss: () => setActiveChip(null),
});

// Mark the inline chip(s) for `id` active (teal), clearing any prior — or clear
// all when `id` is null. Several sections may cite the same source; mark each.
function setActiveChip(id) {
  for (const chip of view.querySelectorAll(".chip")) {
    chip.classList.toggle("active", id != null && chip.dataset.chunkId === id);
  }
}

// Announce a state transition to assistive tech via the dedicated live region,
// and move focus to the newly-rendered heading so keyboard/AT users land on the
// new content (the old focused element — e.g. a ticker-hint button — was just
// destroyed by the innerHTML swap).
function transition(message) {
  if (announcer) announcer.textContent = message;
  const heading = view.querySelector("[data-focus]");
  if (heading) heading.focus();
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
  panel.reset();
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

// Covered ticker → stream a four-section cited brief (Story 2.2). Renders four
// pending cards, then fills each as its `section` SSE event arrives (UX-DR16).
function renderGenerating(ticker) {
  if (activeStream) activeStream.close(); // supersede any in-flight brief
  panel.reset(); // drop the prior brief's sources before this one streams
  // Guard every row's ticker — a declared-but-unindexed filer may lack one.
  const company =
    companies.find((c) => String(c.ticker ?? "").toUpperCase() === ticker) ?? { name: ticker, ticker };
  const SECTIONS = ["Business & moat", "Financial trajectory", "Risk factors", "Recent material events"];
  const cards = SECTIONS.map(
    (title, i) => `
      <div class="card pending" data-section-index="${i}">
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
    <div class="statusline"><span id="brief-status" aria-live="polite">synthesizing · 0 of ${SECTIONS.length} sections</span></div>
    <div class="stack">${cards}</div>`;
  transition(`Generating brief for ${company.name}`);

  let rendered = 0;
  let chips = 0;
  activeStream = streamBrief(company.ticker, {
    onSection(evt) {
      const card = view.querySelector(`[data-section-index="${evt.index}"]`);
      if (!card) return; // unexpected/duplicate index — don't miscount
      fillSectionCard(card, evt);
      // Register this section's cited sources with the drill-down panel (2.3).
      panel.addCitations(evt.answer?.citations ?? [], evt.scores ?? {});
      rendered += 1;
      chips += card.querySelectorAll(".chip").length; // count chips ACTUALLY shown, not provided
      const status = $("#brief-status");
      if (status)
        status.textContent = `synthesizing · ${rendered} of ${SECTIONS.length} sections · ${chips} claims cited`;
    },
    onDone() {
      const gs = view.querySelector(".genstate");
      if (gs) gs.innerHTML = "GENERATED";
      const status = $("#brief-status");
      if (status) status.textContent = `${rendered} sections · ${chips} claims cited`;
    },
    onRefused() {
      // Only take over the view if nothing has rendered — never wipe good,
      // already-streamed sections (the backend only refuses first-and-only today).
      if (rendered === 0) renderRefusalStub(company.ticker);
    },
    onError() {
      // Legible failure surface; the full error banner is Story 2.8.
      const status = $("#brief-status");
      if (status) status.textContent = "brief stream failed — retry from the command bar";
    },
  });
}

// Fill one pending section card with its streamed, cited answer.
function fillSectionCard(card, evt) {
  const ans = evt.answer;
  card.classList.remove("pending");
  const body = ans.refused
    ? `<p class="section-refused">Not covered in the filings.</p>`
    : `<p>${citedTextToHTML(ans.text, ans.citations)}</p>`;
  card.innerHTML = `
    <p class="eyebrow"><span class="tick"></span> ${esc(evt.title).toUpperCase()}
      <span class="state done">✓ RENDERED</span></p>
    <h2>${esc(evt.title)}</h2>
    ${body}`;
}

// Uncovered ticker → refusal path (AC-3). Minimal, sober stub; the full banner
// (REFUSAL_TEXT_SENTINEL, WHAT-I-DO-HAVE cited list) is Story 2.6.
function renderRefusalStub(ticker) {
  panel.reset();
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
    renderAskPlaceholder(cmd.question);
  }
}

// Free-text questions get a Q&A thread over POST /query in Story 2.4. Until then
// an honest placeholder — NOT a mis-routed brief stream for the sentence.
function renderAskPlaceholder(question) {
  if (activeStream) activeStream.close();
  panel.reset();
  view.innerHTML = `
    <div class="empty">
      <h1 tabindex="-1" data-focus>Q&amp;A is coming</h1>
      <p>Cited follow-up answers land in the next build. For now, type a covered ticker for a brief.</p>
      <div class="hint">YOU ASKED</div>
      <p class="section-refused">${esc(question)}</p>
    </div>`;
  transition("Q&A is not available yet");
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

// --- citation drill-down wiring (Story 2.3) ---
// Delegated: a citation chip (native <button>, so Enter/Space fire click too)
// pins its source in the panel. Chips whose source isn't registered are inert.
view.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip || !view.contains(chip)) return;
  const id = chip.dataset.chunkId;
  if (panel.has(id)) panel.pin(id, chip); // chip is the focus-return target on Esc
});
// Esc dismisses the pinned source (panel restores focus to the opening chip).
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && panel.pinnedId) panel.dismiss();
});

// --- boot ---
$("#command-bar").addEventListener("submit", (e) => {
  e.preventDefault();
  submitCommand(input.value);
});
initTheme();
input.focus();
loadCoverage();
