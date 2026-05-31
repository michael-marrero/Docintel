# Hero GIF Storyboard

**Audience:** the project owner, recording the hero GIF for the README.

**Why this exists:** Phase 13 D-17 splits the hero GIF deliverable into
two: Claude builds the recordable demo (the running stack + pre-filled
hero question + distinct refusal card) + this shot-by-shot storyboard;
the actual screen recording is a manual user step (an AI agent cannot
screen-record). This document is the script.

**Target output:** `docs/hero.gif` — a short (~15-25 second) screen
recording of the demo answering the locked hero question with hoverable
citations, then answering an out-of-corpus question with the amber refusal
card. This GIF is what the README's top-of-file image anchor points at.

---

## Before you record

1. **Have Docker running** with a fresh project state:

   ```bash
   docker-compose down -v   # purge any prior state
   docker-compose up --build
   ```

2. **Wait for both healthchecks to pass.** In a separate shell:

   ```bash
   curl -fsS http://localhost:8000/health   # expect {"status":"ok",...}
   curl -fsS http://localhost:8501/_stcore/health   # expect "ok"
   ```

3. **Pick a screen recorder.** Recommended:
   - macOS: QuickTime Player → File → New Screen Recording (built-in,
     records `.mov`). Convert to GIF with `ffmpeg -i input.mov -vf
     "fps=10,scale=960:-1:flags=lanczos" -loop 0 docs/hero.gif`.
   - Linux: `peek` (https://github.com/phw/peek) or
     `gif-screen-recorder`. Both export `.gif` directly.
   - Windows: ShareX (https://getsharex.com/), GIF capture mode.

4. **Browser window:** open one Chrome/Firefox window cropped to a
   tight 1280×720 or 960×540 rectangle around the Streamlit page. The GIF
   doesn't need to show the OS chrome.

5. **Pre-load the page once** (so first-paint asset compilation isn't in
   the recording):

   ```bash
   open http://localhost:8501   # or your browser's open command
   ```

   Wait until the Query tab fully renders. Then close + reopen for the
   take.

---

## Shot 1 — Multi-hop comparative hero question (~10-12 seconds)

The Query tab is pre-filled with the locked hero question
`GT-comparative-001 +TSLA`:

> _"Among Apple, Microsoft, NVIDIA, and Tesla in their FY2024 10-K
> filings, which companies grew R&D spending year-over-year while their
> gross margin (or automotive gross margin, for Tesla) contracted?"_

**Action sequence:**

| t (sec) | Action                                                                    |
| ------- | ------------------------------------------------------------------------- |
| 0       | Recording starts on the Query tab. Hero question is pre-filled.           |
| 0-1     | Mouse moves into the **Submit** button area.                              |
| 1       | Click **Submit**.                                                         |
| 1-2     | `st.spinner("Querying...")` shows briefly (~instant in stub mode).        |
| 2-4     | Answer card renders: synthesized answer text with inline `[1] [2] [3]`    |
|         | numbered citation badges, confidence pill (high/medium/low), cost +       |
|         | latency `st.metric` row, Sources list below.                              |
| 4-6     | Mouse hovers over `[1]` — browser shows tooltip with                      |
|         | `[Company · Item N: Title]\n<excerpt>`.                                   |
| 6-8     | Mouse hovers over `[2]` — different tooltip with different excerpt.       |
| 8-10    | Mouse moves down to the Sources list, scrolls a half-screen to show       |
|         | all 3-5 sources rendered as Markdown bullets.                             |
| 10-12   | Mouse moves back up to the question text area, **clears the text** in    |
|         | preparation for shot 2.                                                   |

**What to capture:** the inline `[N]` badges must be visible. The
tooltip-on-hover is the load-bearing UX (UI-02). The expected hero answer
is something like: "TSLA: R&D grew +14% (4%→5% of revenue) while automotive
GM contracted 19.4%→18.4%. AAPL, MSFT, NVDA all expanded their gross
margins YoY, so they do not qualify." (The exact wording depends on the
stub LLM's deterministic output — see Note 1 below.)

**Stub-mode caveat (visible in the GIF):** the cost metric shows
`$0.000000 (stub — non-representative)` and latency shows
`0.0 ms (stub — non-representative)`. **This is correct and honest** —
the stub LLM hardcodes both to zero (see ADR-001 in
[`../DECISIONS.md`](../DECISIONS.md)). Don't try to fake it; the suffix
is the credibility signal.

---

## Shot 2 — Out-of-corpus refusal (~5-7 seconds)

**Action sequence:**

| t (sec) | Action                                                                    |
| ------- | ------------------------------------------------------------------------- |
| 12-14   | Type into the text_area: "What is the best recipe for sourdough bread?"   |
|         | (or any obviously-out-of-corpus question — see "Refusal question         |
|         | candidates" below).                                                       |
| 14      | Click **Submit**.                                                         |
| 14-15   | `st.spinner` shows briefly.                                               |
| 15-18   | **Amber `st.warning` card renders** with the refusal sentinel:            |
|         | "I cannot answer this question from the retrieved 10-K excerpts."         |
|         | + the "out-of-corpus" why-line.                                           |
| 18-20   | Mouse moves to the trace-id caption below the refusal card (the deep-link |
|         | affordance into the Traces tab).                                          |
| 20      | Recording stops.                                                          |

**What to capture:** the **distinct amber card** is the load-bearing
visual (D-04). The same text rendered as a plain `st.markdown` would
not be recognizable as a refusal at a 30-second skim. Make sure the GIF
shows the colored card, not just the sentinel text.

**Refusal question candidates** (any of these triggers the refusal path
because they're obviously out-of-corpus — pick one for the recording):

- "What is the best recipe for sourdough bread?"
- "Who won the 2026 World Cup?"
- "Summarize Tesla's 2030 10-K filing." (out-of-range year — D-17 flavor 2)
- "What is Amazon's R&D spending?" (in-corpus topic but AMZN's chunks are
  empty in this clone — D-17 flavor 1)

**Stub-mode caveat for refusal (an honest disclosure):** the stub LLM's
deterministic refusal path requires zero retrieved chunks. Since BM25 over
the 6,053-chunk corpus returns chunks for any non-empty question, the
*stub-mode* refusal in the live demo is driven by the **API's monkeypatched
refusal-shape fixture** OR the stub bundle's hardcoded zero-chunks
fallback for clearly out-of-corpus queries. In **real mode** the refusal
fires organically: the real LLM recognizes the retrieved chunks don't
answer the question and emits the refusal sentinel. The recording
captures the UI shape (amber card + sentinel), which is identical across
modes — what differs is just *how* the refusal got triggered.

---

## After recording — saving and embedding

1. **Convert to GIF** (if your recorder produced a video format):

   ```bash
   ffmpeg -i raw-recording.mov \
       -vf "fps=10,scale=960:-1:flags=lanczos" \
       -loop 0 docs/hero.gif
   ```

   Tune `fps=10` down to `8` if the file is too large; tune `scale=960` up
   to `1200` if quality is too low. The trade-off is file size vs.
   readability.

2. **Target file size:** aim for under 5 MB. A 20-second
   `960×540@10fps` GIF compresses to roughly 3-4 MB with reasonable
   content. GitHub renders inline up to ~10 MB but larger files load
   slowly.

3. **Drop the file at `docs/hero.gif`** — exactly that path. The README
   already embeds it at the top:

   ```markdown
   ![hero demo — multi-hop comparative answer + out-of-corpus refusal](docs/hero.gif)
   ```

4. **Commit:**

   ```bash
   git add docs/hero.gif
   git commit -m "docs: add hero GIF (multi-hop comparative + refusal)"
   git push
   ```

5. **Verify the README rendering** on the GitHub web UI. The GIF should
   auto-play on the README page. If it doesn't load, check the path
   case-sensitively (`docs/hero.gif`, not `Docs/Hero.gif`).

---

## Optional shot 3 — Traces tab + Eval-Results tab (for a longer GIF)

If you want a longer recording showcasing the full UI (a 30-40 second
version targeted at engineer reviewers), append after shot 2:

| t (sec) | Action                                                                    |
| ------- | ------------------------------------------------------------------------- |
| 20-22   | Click the **Traces** tab.                                                 |
| 22-25   | Recent-queries table shows the seed records + your just-issued query +    |
|         | the refusal query. Click your query's row.                                |
| 25-28   | Per-stage Altair horizontal Gantt-waterfall renders (stub mode: bars are  |
|         | zero-width with "all durations are 0 ms (non-representative)" caption).   |
| 28-30   | Click the **Eval-Results** tab.                                           |
| 30-33   | Headline tables render (Hit@5/Hit@3/MRR with Wilson CIs; faithfulness;    |
|         | ablation deltas). Prominent `representative: false` banner is visible at  |
|         | the top.                                                                  |
| 33-35   | Click the "Full eval report" expander; show the embedded `report.md`.     |
| 35      | Recording stops.                                                          |

This longer GIF is **optional** — the primary hero GIF (shots 1+2) is the
required deliverable for UI-03.

---

## Validation reference

This storyboard is the manual half of validation node UI-03
(per [`../.planning/phases/13-api-ui-polish/13-VALIDATION.md`](../.planning/phases/13-api-ui-polish/13-VALIDATION.md)
Manual-Only rows). An AI agent cannot screen-record; the user owns the
recording step. The automated guarantees that everything the recording
exercises actually works are:

- `tests/test_api_query.py` — `POST /query` returns the answer + trace
  shape the Query tab consumes (Phase 13-02).
- `tests/test_ui_citations.py` — the inline `<abbr title>` badge HTML +
  V5 HTML escaping (Phase 13-03).
- `tests/test_ui_eval_tab.py` — the eval auto-detect + `representative:
  false` banner (Phase 13-04).
- The Docker compose-smoke job in
  [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) — confirms
  `docker-compose up` produces an api with `/health == ok` and a ui
  serving `/_stcore/health` on a fresh image build.

If the recording fails because a tab doesn't render the expected content,
the failure points at one of the four bullets above — not at this
storyboard.

---

## Note 1 — stub LLM determinism

The stub LLM's output for the hero question is deterministic but
synthesized from chunk text via a templated stub generator. The answer
will mention `TSLA`, `R&D`, and `gross margin` because those tokens come
from the retrieved chunks; the exact prose comes from the stub generator.
The recording is correct as long as:

- An answer renders with inline numbered citation badges.
- Hovering a badge surfaces a tooltip with excerpt + company + section.
- The Sources list below shows the citation chunks.

If the answer text reads strangely, that's the stub LLM, not a bug. The
real-mode answer would be coherent prose; the stub-mode answer is the
load-bearing demonstration that the *pipeline* works end-to-end.

---

_Last updated: Phase 13 plan 13-06._
