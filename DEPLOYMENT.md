# Deploying docintel (self-host)

docintel is a self-hostable RAG engine over SEC filings. It runs entirely inside
your perimeter — one command, your infra, your choice of tier. This is the
operator's guide (Epic 4).

## One-command self-host (Story 4.1, FR-E1)

```bash
git clone <repo> && cd docintel
docker compose up            # builds api + ui, boots the stub demo
```

- **api** → http://localhost:8000 (FastAPI; `/health`, `/ready`, `/coverage`,
  `POST /query`, `/brief/{ticker}`, `/trust`, `/traces`).
- **ui** → http://localhost:8501 (the analyst workspace). The UI reaches the API
  over HTTP only (AD-15) — it never touches the filesystem.
- **qdrant** starts only under the `real` profile (`docker compose --profile real up`);
  the default stub demo uses an in-process NumPy index (no external services).

The api entrypoint builds the stub index on first boot; the compose healthcheck
gates readiness. Everything is offline-first — the default demo needs no keys and
makes no external calls.

## Tiers (Stories 4.2 / 4.3 · AD-17)

The **tier** (`DOCINTEL_TIER`) is a construction-time posture — it never branches
the hot path (AD-2). Configure via `.env` (copied from `.env.example`).

| Tier | `DOCINTEL_TIER` | What leaves the perimeter | Config |
|------|-----------------|---------------------------|--------|
| **stub demo** | (any) + `DOCINTEL_LLM_PROVIDER=stub` | nothing | default |
| **open** | `open` | only the LLM call (corpus + queries stay local, NFR-SEC1) | `DOCINTEL_LLM_PROVIDER=real` + a hosted provider key |
| **sealed** | `sealed` | **nothing** — zero external calls (NFR-SEC1/DEP2) | `real` + a **local** OpenAI-compatible endpoint + local qdrant |

- **Open tier (4.2):** bring your own key. `DOCINTEL_ANTHROPIC_API_KEY` /
  `DOCINTEL_OPENAI_API_KEY` pass from the host env — **never baked into an image**
  (NFR-SEC3). Secrets are `SecretStr` (masked in logs/repr) and never serialized
  into `/health`.
- **Sealed tier (4.3):** point `DOCINTEL_OPENAI_BASE_URL` at a local
  OpenAI-compatible model server (e.g. a local vLLM/NIM/Ollama container) and
  `DOCINTEL_QDRANT_URL` at a local qdrant. The adapter factory **rejects any
  egressing adapter at construction** (`SealedTierViolation`) — the hosted
  Anthropic provider and any public base-URL are refused. A sealed process makes
  zero external network calls. *(Air-tight enforcement is an egress-blocking
  network policy at the container; the factory guard catches misconfiguration.)*

## Licensing (Story 4.4 · AD-18)

A license is a **signed token verified entirely offline** — no vendor network
call, ever, so it coexists with the air-gap.

- `DOCINTEL_LICENSE_KEY` — the signed token (licensee / expiry / tier scope).
  **Empty → the unlicensed demo grant** (the demo runs out-of-the-box).
- `DOCINTEL_LICENSE_PUBLIC_KEY_HEX` — the vendor's **Ed25519 public key** (hex).
  Set it to use the real, unforgeable verifier; unset uses the deterministic
  dev/demo stub.
- Enforcement is offline at startup: an expired or out-of-tier-scope license makes
  `GET /ready` return **503** (the orchestrator stops routing traffic) — nothing is
  transmitted to the vendor. The token/signature is never logged.

Issuance (vendor side): sign the JSON payload with the Ed25519 **private** key;
ship only the public key with the deployment.

## Single config surface + sizing (Story 4.6 · AD-5, NFR-DEP1)

**Every** knob flows through one reader — `docintel_core.config.Settings`
(`DOCINTEL_` prefix). There are **zero** ad-hoc `os.environ`/`os.getenv` reads
anywhere else (CI-gated by `tests/test_no_env_outside_config.py`). See
`.env.example` for the full annotated surface.

**Sizing (reproducible from documented inputs):**

| Tier | CPU | RAM | Disk | Notes |
|------|-----|-----|------|-------|
| stub demo | 2 vCPU | 4 GB | ~3 GB image + ~0.1 GB corpus | no GPU, no keys |
| open | 2 vCPU | 4 GB | as above | + outbound HTTPS to your provider |
| sealed | 4+ vCPU (or GPU for the local model) | 8–16 GB + model RAM/VRAM | image + local model weights + qdrant | model server sizing dominates |

The 15-company / 3-year corpus index is ~sub-GB. A local model server (sealed)
is sized by the model you choose, not by docintel.

## Versioned releases + update path (Story 4.5 · FR-E3, NFR-DEP1)

- **Version:** the running build is stamped by `DOCINTEL_GIT_SHA` (in `/health`
  and every eval manifest) — the reproducibility anchor.
- **Update to a new version:** `git pull` (or pull the new image tag) →
  `docker compose build` → `docker compose up`. Config is unchanged (single
  surface); the api entrypoint re-runs the **idempotent** index build (MANIFEST
  SHA skip — unchanged corpus is a no-op).
- **Corpus/index update (incremental):** drop new filings into `data/corpus/`,
  run `docintel-ingest` + `docintel-index build` (idempotent — only new/changed
  chunks are re-embedded, gated by the corpus MANIFEST SHA). The eval-set freeze
  (AD-13) bounds any ground-truth change to its 4-step protocol.
- Every step is reproducible from documented inputs (the corpus MANIFEST + the
  pinned `uv.lock` + the git SHA).

## Image footprint (Story 4.7 · FR-E6, NFR-DEP1)

- CI job `docker-build-and-size` builds both targets and **asserts image size
  < 3 GiB** on every run — a measured reduction from the ~4.8 GB early baseline,
  re-verified continuously. The slimmer image still passes the full stub-mode
  eval and the startup healthcheck smoke (AD-14).
- The image is multi-stage (shared `base` → `api` / `ui` targets); `.dockerignore`
  keeps `.git`, `.planning`, secrets, and the gitignored runtime trees
  (`data/indices/`, `data/traces/`) out of the build context.
- **Next lever** (documented in `docker/Dockerfile`): a dedicated builder stage
  that compiles wheels (`pystemmer`) then copies them into a clean runtime stage
  without `build-essential`/`python3-dev` — drops ~260 MB from the runtime images.
  Deferred as a measured change (needs a docker host to verify, like real-mode
  eval runs); the < 3 GiB gate already enforces the reduction target.

## Operability (Story 4.8 · FR-E7, AD-16)

- `GET /health` — liveness (status, service, version, provider, git_sha, timestamp).
- `GET /ready` — readiness for orchestrators: `ready` iff the index is present
  **and** the license verifies; **503** when not ready, with a non-secret payload
  (tier, provider, per-check flags, license status) either way.
- Every request carries a `trace_id` with per-stage timings via the pure-ASGI
  `TraceIdMiddleware`, producing exactly **one** `trace_completed` record per
  request (AD-16, NFR-OBS1) — your ops team runs docintel without vendor access.
