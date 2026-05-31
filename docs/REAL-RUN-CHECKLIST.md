# Real-Run Checklist — populating the README with real eval measurements

**Audience:** the project owner (you), running the real-mode eval and
ablation jobs to replace the stub-sample numbers in the README's
`PASTE-REAL-NUMBERS` block with real measurements.

**Why this exists:** Phase 13 D-14 explicitly does NOT block the README on
real numbers. The README ships with a labeled `representative: false`
stub block + this checklist. Real numbers are populated by a manual
`gh workflow run` step the user owns.

**Claude (the AI engineering agent that built this project) does NOT run
this workflow.** This project is offline-first by design (ADR-001 in
[`../DECISIONS.md`](../DECISIONS.md)); Claude holds no API keys, and
the real-key workflow runs against live Anthropic + OpenAI clients.
The instructions below are for the human owner of the GitHub repo.

---

## TL;DR

```bash
# Prerequisites (one-time)
gh secret set DOCINTEL_ANTHROPIC_API_KEY    # paste your Anthropic API key
gh secret set DOCINTEL_OPENAI_API_KEY       # paste your OpenAI API key
git push origin <your-real-eval-branch>     # see "Branch prerequisites" below

# Run the real-key workflows (one at a time; they take ~25-50 minutes each)
gh workflow run ci.yml --ref <branch> -f run-real-eval=true
gh workflow run ci.yml --ref <branch> -f run-real-ablation=true

# After both runs land
git pull
# Open data/eval/reports/<timestamp>/results.json
# Open data/eval/ablations/<timestamp>/ablation-manifest.json
# Paste their numbers into README.md between the
#   <!-- PASTE-REAL-NUMBERS --> ... <!-- END-PASTE-REAL-NUMBERS -->
# markers, removing the "representative: false" disclaimer block.
# Commit:
git commit -am "docs: populate README with real eval measurements"
```

---

## Branch prerequisites

> **Important:** as of the time this checklist was written, **Phases 6-12
> are local-only / unmerged** to `main`. The branch chain
> `phase/6-generation → phase/7-answer-schema → phase/8-ground-truth-eval-set
> → phase/9-metrics → phase/10-eval-harness → phase/11-ablation-studies →
> phase/12-observability → phase/13-api-ui-polish` lives on your local
> machine but is not pushed to GitHub. The real-key workflow runs against
> code on a GitHub branch, so before you can trigger it you have to:

1. **Pick a target branch.** The cleanest choice is the head of the chain
   — `phase/13-api-ui-polish` — which carries every prior phase's code.
   Alternatively, fast-forward `main` to it (or to a tag of it). All
   commands below assume you've picked a branch and exported it:

   ```bash
   export REAL_RUN_BRANCH=phase/13-api-ui-polish
   ```

2. **Push the chain to the remote.** From a worktree on the branch:

   ```bash
   git push origin "$REAL_RUN_BRANCH"
   ```

   GitHub will accept it directly; no PR or merge is required for a
   `workflow_dispatch` trigger.

3. **Confirm the workflow file is on that branch.** The `real-eval` and
   `real-ablation` jobs live in
   [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) and are
   already on `phase/13-api-ui-polish`. You can verify with:

   ```bash
   git log --oneline -n 1 "$REAL_RUN_BRANCH" -- .github/workflows/ci.yml
   ```

---

## Setting the secrets

The workflow reads two GitHub Actions secrets:

| Secret name                    | What it is                                    |
| ------------------------------ | --------------------------------------------- |
| `DOCINTEL_ANTHROPIC_API_KEY`   | Your Anthropic API key (for the generator).   |
| `DOCINTEL_OPENAI_API_KEY`      | Your OpenAI API key (for the LLM-judge).      |

Set them via the `gh` CLI from a clean shell on the project root:

```bash
gh secret set DOCINTEL_ANTHROPIC_API_KEY    # interactive paste
gh secret set DOCINTEL_OPENAI_API_KEY       # interactive paste
gh secret list                              # confirm both are present
```

(You can also set them through the GitHub UI:
`Settings → Secrets and variables → Actions → New repository secret`.)

The workflow does **not** read any other secrets. The cost ceiling for one
real-mode eval run is roughly `$2` (32 questions × 1 generator call + 32
judge calls); the real-ablation run is `~$8` (3-5 arms × the same per-question
cost). These are not exact numbers — measure first.

---

## Triggering the real-eval workflow

The `real-eval` job runs the full 32-question eval against real LLMs and
commits the report to `data/eval/reports/<timestamp>/` on the branch you
triggered it on. It is gated on `workflow_dispatch` so it never runs on
push or PR.

```bash
gh workflow run ci.yml --ref "$REAL_RUN_BRANCH"
# wait for the run to appear:
gh run list --workflow=ci.yml --branch "$REAL_RUN_BRANCH" --limit 5
# follow it live (replace <run-id>):
gh run watch <run-id>
```

The run does:

1. Set `DOCINTEL_LLM_PROVIDER=real` in the job env.
2. `uv sync --all-packages --frozen` to install the workspace.
3. Pre-create `data/indices/{bm25,dense,.qdrant}/` as runner-owned (the
   qdrant compose volume mount creates parent dirs as root otherwise —
   one of the historical bite-points captured in `.planning/STATE.md`).
4. Bring up the qdrant container via `docker compose --profile real`.
5. `docintel-index all` to build the real BM25 + dense indices.
6. `docintel-eval run` to produce `data/eval/reports/<ts>/{report.md,results.json}`.
7. `docintel-eval validate data/eval/reports/<ts>/` to gate the report.
8. Commit the report with `[skip ci]` (so the commit doesn't trigger
   another run) and push.
9. Tear down qdrant.

Expected wall-clock: ~25 minutes (index build ~7 min, eval ~15 min,
overhead the rest).

---

## Triggering the real-ablation workflow

The `real-ablation` job runs the full ablation sweep (component swap arms
plus the chunk-size sweep) and commits the manifest to
`data/eval/ablations/<timestamp>/`. Same `workflow_dispatch` gate, same
branch model.

```bash
gh workflow run ci.yml --ref "$REAL_RUN_BRANCH"
# select the real-ablation job manually in the GitHub UI run, or use
# the workflow_dispatch input pattern if you've added one in ci.yml.
gh run watch <run-id>
```

Expected wall-clock: ~45-60 minutes (it builds 3 different chunk-size
indices and runs the eval against each).

---

## Pasting the numbers into the README

When both runs complete:

```bash
git pull origin "$REAL_RUN_BRANCH"   # pull the committed reports
ls data/eval/reports/                # find the newest timestamp directory
ls data/eval/ablations/              # find the newest timestamp directory
```

Open `data/eval/reports/<timestamp>/results.json` and read out:

| README cell                 | JSON path                                  |
| --------------------------- | ------------------------------------------ |
| Hit@5                       | `retrieval.hit_at_5` + `retrieval.hit_at_5_ci` |
| Hit@3                       | `retrieval.hit_at_3` + `retrieval.hit_at_3_ci` |
| MRR                         | `retrieval.mrr`                            |
| Faithfulness (pass)         | `faithfulness.faithfulness_pass_rate` + `faithfulness.faithfulness_ci` |
| Latency p50                 | `latency.p50_ms`                           |
| Latency p95                 | `latency.p95_ms`                           |
| $/query                     | `latency.cost_per_query_usd`               |

Open `data/eval/ablations/<timestamp>/ablation-manifest.json` and read out:

| README cell                 | JSON path                                                |
| --------------------------- | -------------------------------------------------------- |
| `baseline` Hit@5            | `arms.baseline.metrics.hit_at_5`                         |
| `no-rerank` Hit@5           | `arms.no-rerank.metrics.hit_at_5`                        |
| `no-rerank` Δ Hit@5         | `arms.no-rerank.deltas.hit_at_5` (3-tuple `[Δ, lo, hi]`) |
| `dense-only` Hit@5          | `arms.dense-only.metrics.hit_at_5`                       |
| `dense-only` Δ Hit@5        | `arms.dense-only.deltas.hit_at_5` (3-tuple `[Δ, lo, hi]`)|
| chunk-300 / 450 / 600 (if real run) | `arms.chunk-<size>.metrics.*` + `.deltas.*`     |

Then edit `README.md`:

1. Find the `<!-- PASTE-REAL-NUMBERS: ... -->` marker.
2. Find the matching `<!-- END-PASTE-REAL-NUMBERS -->` marker.
3. Replace everything between them with the real-numbers block. **Remove**
   the `representative: false` disclaimer paragraph — the real run is
   representative.
4. Re-add the two markers around the new block so a future re-paste is
   trivial:

   ```markdown
   <!-- PASTE-REAL-NUMBERS: last refreshed <date> from data/eval/reports/<ts>/ -->

   **Headline metrics** (real-mode, n=32, embedder=`BAAI/bge-small-en-v1.5`,
   reranker=`BAAI/bge-reranker-base`, generator=`<your generator name>`,
   judge=`<your judge name>`, git_sha=`<sha>`):

   | Metric              | Value     | 95% Wilson CI         |
   | ------------------- | --------- | --------------------- |
   | Hit@5               | 0.<n>     | [0.<lo>, 0.<hi>]      |
   ...

   <!-- END-PASTE-REAL-NUMBERS -->
   ```

5. Commit:

   ```bash
   git add README.md
   git commit -m "docs: populate README with real eval measurements"
   git push
   ```

The Streamlit Eval-Results tab will auto-detect the new real report on its
next render (it scans `data/eval/reports/` for any directory other than
`stub-sample/` whose `results.json` exists, and picks the newest by
lexical-sort timestamp — see ADR-013 and
`packages/docintel-ui/src/docintel_ui/eval_view.py` for details). No UI
change needed.

---

## Troubleshooting

- **`gh workflow run` returns "workflow not found":** the workflow file
  isn't on the branch you ran it on. Confirm `.github/workflows/ci.yml`
  exists on `$REAL_RUN_BRANCH`.
- **The run fails at "qdrant /readyz":** the qdrant container didn't come
  up. Check the run's qdrant logs (the workflow dumps them on failure).
  Most often a port collision with a previous run that didn't tear down.
- **The run fails at "Real-mode build" with PermissionError:** the
  pre-create step (`mkdir -p data/indices/...`) didn't run before docker
  did. Re-run the workflow; this is a known historical bite-point.
- **The eval report is committed but the README still shows stub numbers:**
  you didn't pull the committed report (`git pull`) and/or you didn't
  paste between the `PASTE-REAL-NUMBERS` markers. The README does not
  auto-rewrite; the paste step is intentional, so the README only shows
  numbers the project owner has verified.

---

_Last updated: Phase 13 plan 13-06._
