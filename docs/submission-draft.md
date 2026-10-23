# Skylark submission draft

**Status: internal draft. Not submitted. A limited live held-out evaluation and one independent-agent pilot are complete; public URLs and judge access remain outstanding.**

## One-line description

Reproduce tool failures, inspect their real consequences, and turn reviewed agent repairs into executable regression tests.

## Inspiration

A timeout is not proof that an operation failed. A reservation service can save a booking and lose its confirmation. An agent that retries carelessly can book twice; an agent that stops can leave the user without a useful answer. We built Skylark to make that ambiguity testable.

## What it does

Skylark runs a local agent against a synthetic reservation service. Developers select a timeout after commit, stale read, or incomplete response and inspect both the tool's actual state and the information delivered to the agent. An independent verifier scores safety, task completion, reporting accuracy, and fault coverage separately.

The developer reviews a bounded prompt or runtime change, approves a new configuration, compares repeated fresh trials, and exports evidence plus a regression test. Recorded playback, deterministic regression, and fresh inference are labeled separately. Runtime safeguards are credited as runtime safeguards.

## How it is built

React and TypeScript provide the workbench. FastAPI exposes a localhost API. SQLite, SQLAlchemy, and Alembic preserve run snapshots, a durable queue, event sequences, and usage accounting. A separate supervised Python worker enforces execution limits. The instrumented adapter allows trusted local Python agents to participate without uploading their code.

The Nebius integration uses its OpenAI-compatible inference API for agent tool decisions. Supported repair descriptions use a deterministic catalogue so that an unverified model explanation cannot misstate the tool outcome. A predeclared live development pack ran `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` with tool calling: 12/12 runs completed, all six fault injections were reached, and both stale-read conditions failed reporting accuracy. In a separate exploratory `/5` stale-read comparison, the fresh original reported stale availability and failed, while the freshness guard refreshed the read and passed. Both saved traces replay exactly. These narrow synthetic observations do not support a general reliability-rate claim.

A later [limited held-out protocol](live-held-out-2026-10-22.md) scheduled 12 live attempts under a frozen scenario and policy hash. Eleven completed and replay exactly; one guarded timeout attempt failed before reaching its fault and is inconclusive. The stale-read and incomplete-response original runs failed accurate reporting while their guarded pairs passed. All six controls passed. The original timeout run also passed, so that pair does not demonstrate an improvement. This one-variant-per-fault result is too small for a reliability rate.

An [independent-agent pilot](evidence/real-agent-pilot-2026-10-24.md) then connected a newly built model-driven booking agent through the local adapter. Fresh Nemotron calls chose the reservation tool in both runs. With a post-commit timeout, the agent's original retry made two bookings and failed verification; Skylark's proposed runtime guard produced one booking and passed. Both saved traces replay exactly. This tests one real agent implementation in a synthetic service, not arbitrary customer agents or automatic code patching.

The [evidence packet](evidence/README.md) contains all 12 attempt summaries and bundles; the [recording script](demo-script.md) uses the scoped Results view. Review exports before publication.

## What is distinctive

Skylark tests observable business consequences at specific call boundaries. It preserves the difference between an executed operation, a damaged response, and the agent's final claim. The repair workflow requires review, keeps original evidence intact, and exports executable regression evidence. It does not claim a model learned recovery when a runtime guard supplied it.

## Engineering evidence

The implemented tests cover duplicate operations, operation-key conflicts, false claims, uncertain billing, worker fencing, cancellation, incomplete traces, concurrent initialization, and concurrent exports. The current full Python suite, 25 Playwright browser tests on an isolated server with live inference disabled, a production frontend build, and an 11-case offline release smoke check passed. A fresh virtual environment installed the previous release archive, passed `pip check`, ran a scripted fault, exported and replayed its incident, replayed a saved live trace without an API key, and served the included interface. The refreshed archive passed manifest verification, but a new clean install has not been repeated. This is same-machine verification; independent user testing remains. Do not infer live model quality from these checks.

## Results to complete before publication

- The account price table confirmed $0.06/$0.24 per million input/output tokens for `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` on October 22. The usage page rounded current Token Factory usage to $0.03; the local ledger is an estimate and not an account invoice. Keep account-specific billing details out of the public submission.
- Have an independent person reproduce the held-out protocol export and inspect the failed guarded timeout attempt.
- Verify local spend estimates against provider billing and the unresolved earlier charge.
- Public repository, downloadable test build, video, and judge-access instructions.
- Free live-model access for judges through December 15; the current trial ends before judging and is set to stop usage afterward.
- Feedback from actual Nebius/NVIDIA use; do not invent product feedback.

## Limitations and next steps

The current release is local and uses synthetic business scenarios. Small repeated trials do not establish universal agent reliability. Custom adapters are trusted code, and their state assertions are locally reported evidence. Multi-tenant hosting, tenant isolation, production capacity, and operational guarantees remain future work requiring independent validation.

## Rules check

Reviewed October 22, 2026. The official rules require a working app that makes runtime Nebius Token Factory calls or uses Nebius AI Cloud and at least one NVIDIA open-source model; public source with a license and setup guidance; a working demo/application/test-build URL; track identification; and a public YouTube demonstration under three minutes. **Best Apps and Agents** is the recommended track for Skylark's current implementation. The Coding and Agentic Engineering track now specifically describes coding agents and developer tools that write, run, and test code in Token Factory Sandboxes; Skylark does not use those Sandboxes. The submission deadline is **October 30, 2026 at 10:00 a.m. PDT (10:30 p.m. IST)**. Judging is December 1–15, 2026, and the project must remain free and unrestricted for judges through that period. Account access and credit expiry must support that arrangement. Source: [official rules](https://nebiusglobalaihackathon.devpost.com/rules).

## 150-second recording script

| Time | Screen and narration |
|---|---|
| 0–15 | “The booking succeeded, but its confirmation timed out. Does the agent know what to do next?” Show the actual user task. |
| 15–45 | Show a genuine live incident or clearly labeled saved live evidence. Follow the request, committed state, and response received. If no failure occurred, show that result honestly. |
| 45–65 | Explain safety, completion, reporting, and fault coverage using actual checks. |
| 65–95 | Show the proposed change, its evidence, and approval. Name whether it changes the prompt or runtime. |
| 95–130 | Show the completed fresh comparison and controls, with counts, uncertainty, costs, and any regression. Do not substitute fixture results. |
| 130–150 | Export and run the regression test. Finish with local adapter support and the limits of the evidence. |

Use the completed limited live measurements, including the inconclusive attempt, when recording the demo. This script requires no invented percentages or winning probability.
