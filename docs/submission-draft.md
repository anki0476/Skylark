# Skylark submission draft

**Status: internal draft. Not submitted. Live-model evidence and public URLs remain outstanding.**

## One-line description

Reproduce tool failures, inspect their real consequences, and turn reviewed agent repairs into executable regression tests.

## Inspiration

A timeout is not proof that an operation failed. A reservation service can save a booking and lose its confirmation. An agent that retries carelessly can book twice; an agent that stops can leave the user without a useful answer. We built Skylark to make that ambiguity testable.

## What it does

Skylark runs a local agent against a synthetic reservation service. Developers select a timeout after commit, stale read, or incomplete response and inspect both the tool's actual state and the information delivered to the agent. An independent verifier scores safety, task completion, reporting accuracy, and fault coverage separately.

The developer reviews a bounded prompt or runtime change, approves a new configuration, compares repeated fresh trials, and exports evidence plus a regression test. Recorded playback, deterministic regression, and fresh inference are labeled separately. Runtime safeguards are credited as runtime safeguards.

## How it is built

React and TypeScript provide the workbench. FastAPI exposes a localhost API. SQLite, SQLAlchemy, and Alembic preserve run snapshots, a durable queue, event sequences, and usage accounting. A separate supervised Python worker enforces execution limits. The instrumented adapter allows trusted local Python agents to participate without uploading their code.

The Nebius integration uses its OpenAI-compatible inference API for agent tool decisions and explanations of supported repairs. The exact NVIDIA model and settings must be filled in after the live capability experiment. No NVIDIA performance result is claimed in this draft.

## What is distinctive

Skylark tests observable business consequences at specific call boundaries. It preserves the difference between an executed operation, a damaged response, and the agent's final claim. The repair workflow requires review, keeps original evidence intact, and exports executable regression evidence. It does not claim a model learned recovery when a runtime guard supplied it.

## Engineering evidence

The implemented tests cover duplicate operations, operation-key conflicts, false claims, uncertain billing, worker fencing, cancellation, incomplete traces, concurrent initialization, and concurrent exports. Browser checks cover the main workflow and offline fixture use. Publish the final verified test counts and commit alongside the release; do not infer live model quality from these checks.

## Results to complete before publication

- Exact eligible NVIDIA model, provider settings, rates, and capability-probe outcome.
- Predeclared protocol ID/hash and scenario/trial counts.
- Original and repaired safety, completion, reporting, coverage, and infrastructure counts.
- Known and uncertain spend, latency, and regressions.
- Public repository, downloadable test build, video, and judge-access instructions.
- Feedback from actual Nebius/NVIDIA use; do not invent product feedback.

## Limitations and next steps

The current release is local and uses synthetic business scenarios. Small repeated trials do not establish universal agent reliability. Custom adapters are trusted code, and their state assertions are locally reported evidence. Multi-tenant hosting, tenant isolation, production capacity, and operational guarantees remain future work requiring independent validation.

## Rules check

Reviewed October 18, 2026. The official rules require a runtime Nebius integration using an NVIDIA open-source model, public source with a license and setup guidance, a working demo/application/test-build URL, track identification, and a public YouTube demonstration under three minutes. The one-minute hardware/module clause is specified for Physical AI. Our selected track is Coding and Agentic Engineering. Judging is December 1–15, 2026; account access and credit expiry must support the proposed judging arrangement. Source: [official rules](https://nebiusglobalaihackathon.devpost.com/rules).

## 150-second recording script

| Time | Screen and narration |
|---|---|
| 0–15 | “The booking succeeded, but its confirmation timed out. Does the agent know what to do next?” Show the actual user task. |
| 15–45 | Show a genuine live incident or clearly labeled saved live evidence. Follow the request, committed state, and response received. If no failure occurred, show that result honestly. |
| 45–65 | Explain safety, completion, reporting, and fault coverage using actual checks. |
| 65–95 | Show the proposed change, its evidence, and approval. Name whether it changes the prompt or runtime. |
| 95–130 | Show the completed fresh comparison and controls, with counts, uncertainty, costs, and any regression. Do not substitute fixture results. |
| 130–150 | Export and run the regression test. Finish with local adapter support and the limits of the evidence. |

Wait for genuine live measurements before recording claims about model improvement. This script requires no invented percentages or winning probability.
