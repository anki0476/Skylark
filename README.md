# Skylark

**Reproduce tool failures. Inspect the consequences. Verify agent recovery.**

Skylark is a local agent reliability lab. Its example reservation agent encounters timeouts after bookings commit, stale reads, and incomplete receipts. An independent verifier checks actual reservations, task completion, and the agent's final claim.

## What works

- React workbench: experiments, incident timeline, reviewed repair comparisons, and results.
- Optional custom booking messages for live evaluations; the same reservation tools and one-booking verifier apply. Scripted fixtures keep their fixed task.
- Durable SQLite queue, Alembic schema, worker ownership fencing, restart preservation, and cancellation.
- Three fault families plus fault-free and timeout-before-commit controls.
- Separate execution status and test verdict; missing evidence never becomes a pass.
- Approved runtime safeguards or prompt edits; originals remain immutable.
- Local Python agent adapter, bounded process supervision, portable evidence ZIPs, and regression replay.
- Nebius tool calling with explicit live enablement, usage reservations, and uncertainty accounting.
- Fixed development/held-out scenario packs and offline tests.
- Separate outcome counts, descriptive uncertainty intervals, and downloadable results JSON.
- Verified local database backups and restores that suspend unfinished work instead of rerunning it.

**Current evidence:** offline fixtures, mocked-provider tests, and live runs using `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` through Nebius Token Factory. A predeclared, one-trial live development pack completed 12/12 runs: all six fault injections were reached, original fault runs passed 1/3, guarded fault runs passed 2/3, and all six fault-free controls passed. A separate [limited live held-out protocol](docs/live-held-out-2026-10-22.md) reached terminal status for all 12 attempts: 11 completed, one guarded timeout attempt failed before reaching its fault and remains inconclusive. Original stale-read and incomplete-response runs failed accurate reporting; guarded pairs passed. All six controls passed. Earlier exploratory runs also exposed a safe but incomplete pre-commit timeout and a duplicate booking after a post-commit timeout. These narrow synthetic results are not a general reliability rate. This is a local controlled-beta implementation, not a multi-tenant production service.

The stale-read development result led to an optional runtime freshness guard. In one fresh exploratory comparison under verifier `reservation/5`, the original agent repeated stale availability and failed reporting accuracy, while the guarded run refreshed the read and passed. Both traces replay exactly. This single pair is not a held-out reliability estimate; existing approved repairs retain their original configuration. The [judging-readiness map](docs/judging-readiness.md) links the working product and its remaining evidence to the four official criteria.

See the [exploratory live evaluation log](docs/live-evaluation-2026-10-22.md), including a discovered limitation in the original free-text reporting check.

## Start locally

Requires Python 3.12+ and Node 22+. No Docker or GPU required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m skylark serve
```

Open **http://127.0.0.1:8000**. The server starts a separate local worker. Choose **Run fixture** to exercise the complete workflow without an API key. Do not expose this localhost application through a public tunnel.

PowerShell shortcuts: `./scripts/setup.ps1`, then `./scripts/start.ps1`.

The local test-build archive includes `frontend/dist`. After extracting it, Python dependencies and `pip install -e . --no-deps --no-build-isolation` are sufficient to start the included interface; Node is needed only to rebuild it. Run `python scripts/package_release.py` after a successful build to create `dist/skylark-local-beta.zip`. The script uses explicit source paths and excludes local data, credentials, virtual environments, and Git history. Inspect the archive before public sharing.

For someone new to the project, use the [independent clean-install review](docs/independent-review.md) to check the packaged fixture workflow and a saved evidence replay without an API key.

Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python`. Run from the repository root. The frontend is built separately and is not embedded in the Python wheel.

## Live inference: deliberate setup

1. Confirm Nebius access, credits, expiry, and disabled automatic top-ups.
2. Set `NEBIUS_API_KEY` locally. Never commit or paste it into chat.
3. Run `python -m skylark models`; verify a public NVIDIA model's native tool support, terms, and current prices in your account.
4. Configure the variables in `.env.example`. The app **does not automatically load `.env` files**; set environment variables in the shell or process launcher.
5. Set `SKYLARK_ALLOWANCE_USD` to a small amount within 60% of confirmed credits (for example, `$0.50` with at least `$1` confirmed). Enable live execution only after prices and credits are confirmed.
6. Restart Skylark and run a small fresh evaluation. Inspect tool validity, latency, usage, and outcomes before expanding.

SDK retries are disabled. Ambiguous timeouts retain their usage reservation and stop; rate limits permit one bounded retry. The project allowance cannot exceed 60% of confirmed credits. These controls do not replace the provider dashboard or guarantee a provider-enforced spending cap.

A charge above its reserved estimate pauses further inference until the anomaly is inspected and explicitly resolved. See [usage reconciliation and backup recovery](docs/operations.md).

```powershell
.\.venv\Scripts\python.exe -m skylark status
.\.venv\Scripts\python.exe -m skylark models
```

## Reproduce an incident

```powershell
.\.venv\Scripts\python.exe -m skylark demo --fault timeout_after_commit
.\.venv\Scripts\python.exe -m skylark demo --fault timeout_after_commit --repaired
.\.venv\Scripts\python.exe -m skylark export RUN_ID incident.zip
.\.venv\Scripts\python.exe -m skylark replay incident.zip
```

The first fixture creates two reservations and fails. The repaired fixture uses runtime safeguards and preserves one reservation. This demonstrates the harness, not model intelligence.

Bundles contain `run.json`, `events.json`, a checksum manifest, instructions, and `test_incident.py`. Replay validates integrity and versions, re-executes recorded business operations, and checks the verdict. After extracting a trusted bundle, `pytest test_incident.py` runs its regression. Reproducing a failing incident is successful regression verification. Redacted or incomplete bundles cannot establish exact replay. Checksums detect corruption; they do not authenticate third-party evidence.

## Connect a local agent

```powershell
.\.venv\Scripts\python.exe -m skylark adapter examples/cautious_adapter.py
```

Only run adapter files you trust. The example independently implements cautious recovery and is labeled local-adapter evidence. The adapter receives a task and an instrumented context; `context.call` records and fault-injects tool calls. Optional `create_environment(scenario)` supplies a versioned environment, tool schemas and argument types, initial state, tool execution, fault eligibility, stale responses, and an independent verifier. See the `Environment` protocol in `runner.py`. Reservation replay and repair presets are built in; custom environments require their own trusted replay logic and repair integration. The HTTP server never imports this code.

Uninstrumented calls are outside coverage. Process supervision is not isolation for malicious code. The browser cannot upload or import Python.

## Evaluation

```powershell
.\.venv\Scripts\python.exe -m skylark benchmark --mode fixture --split development --trials 1
.\.venv\Scripts\python.exe -m skylark worker
```

The held-out protocol queues 12 fault scenarios × 3 trials × 2 configurations plus six controls: 78 attempts. Use `--split held_out --trials 3`. Live mode refuses a protocol whose projected maximum exceeds the remaining allowance. Reduce repetitions before inspecting results and disclose the change. See [methodology](docs/benchmark-methodology.md).

For a *new* smaller predeclared live held-out check under the current local allowance, run this in the Nebius-enabled PowerShell session only after checking remaining credits. The October 22 limited protocol has already run; repeating this command creates a new protocol and incurs new charges:

```powershell
.\.venv\Scripts\python.exe -m skylark benchmark --mode live --split held_out --trials 1 --cases-per-fault 1 --freshness-guard
```

This selects the first fixed variant of each of the three fault families, queues six fault runs and six controls, and enables freshness validation only for the guarded configuration. It is a 12-run limited held-out sample, **not** the 78-run target or a general reliability estimate. Its conservative admission bound is about $0.371 at the configured Nemotron Nano rates; scheduling still checks the remaining local allowance before queueing anything. Record the returned protocol ID, scenario pack hash, and full protocol hash before running the worker.

After workers complete the scheduled jobs, export a report for the returned benchmark ID:

```powershell
.\.venv\Scripts\python.exe -m skylark report --comparison BENCHMARK_ID --output results.json
```

The report retains every attempt and separates model, verifier, tool, policy, and split versions. Unknown checks stay outside observed-rate denominators and remain visible. Untriggered faults cannot become successful fault tests. The UI also provides **Download results JSON**.

Reports use `skylark-report/2`: the dashboard loads summaries on the Results screen, while exports include per-run attempts and scoped usage details. The project budget remains explicitly global. Completed incident and comparison polling stops; idle workspace refreshes slow to ten seconds.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm run build
npm run test:e2e
```

Browser tests expect the local server on port 8000 and use installed Microsoft Edge. Configure a Playwright-managed Chromium channel on platforms without Edge. Tests require no paid inference.

Run `python scripts/release_smoke.py` for a disposable offline check covering all five conditions, both configurations, bundle replay, and an exported pytest test. Output is clearly labeled scripted evidence. GitHub Actions is configured for Python 3.12, Node 22, and Chromium; hosted CI has not run before repository publication.

## Documentation

- [Architecture and security](docs/architecture.md)
- [End-to-end review and fixes](docs/review-2026-10-18.md)
- [Implementation status](docs/implementation-status.md)
- [Production roadmap](docs/production-roadmap.md)
- [Submission checklist](docs/submission.md)
- [Operations and recovery](docs/operations.md)
- [Submission draft and recording script](docs/submission-draft.md)

The robotics prototype is preserved at Git commit `d8a07d5`. Its files remain for historical tests; the active CLI and UI run the agent lab. The new database is `data/agent-lab/agent-lab.sqlite3` and does not reuse robotics records.

MIT licensed original code. Models and dependencies retain their own licenses; see [attribution](docs/dependency-attribution.md).
