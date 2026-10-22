# Local beta operations

This guide covers a trusted local installation, not a hosted service. No command here provisions paid infrastructure. Keep the server bound to localhost.

## Start and stop

Run `scripts/start.ps1` from a configured checkout. The server owns a separate queue worker, which supervises one attempt process. Ctrl+C stops the server and its worker. Use a second terminal for CLI commands; run them with the same `--data` directory. A wheel installation can use `skylark serve --frontend PATH_TO_BUILT_UI`.

On Windows, Skylark launches the actual virtual-environment interpreter directly so cancellation terminates the interpreter, not just its launcher. The worker checks that its server remains alive, and the attempt checks that its worker and ownership remain valid. These controls cover Skylark's owned processes; trusted adapters that create their own subprocesses remain responsible for their lifecycle.

The default directory is `data/agent-lab`. Secrets are environment variables, not settings saved in SQLite. `.env` files are not loaded automatically.

## Interpret an interrupted run

The journal distinguishes four boundaries:

1. `tool_requested`: the call was about to execute. A request alone cannot prove its effect.
2. `tool_effect`: execution returned; the authoritative outcome and state were checkpointed.
3. `tool_observed`: the raw response, including an injected fault, was checkpointed.
4. `agent_observed`: the response passed through runtime safeguards and was returned to the agent.

Cancellation allows a two-second grace period for a returning call to checkpoint, then terminates the owned attempt. The deadline remains enforced. An unreturned or unjournaled call is uncertain. A completed effect cannot be assumed to have rolled back. Reserved provider costs remain reserved until evidence resolves them.

After worker loss, the next claim fences an expired lease and marks the old run interrupted. It does not retry that attempt. Wait for the lease to expire (20 seconds), inspect the preserved evidence, then create a new experiment from a fresh sandbox. Do not hand-edit database status to force a retry.

## Resolve uncertain usage

Inspect `python -m skylark status` and reconcile against the provider dashboard. For a stopped attempt with a confirmed billed amount:

```text
python -m skylark reconcile USAGE_ATTEMPT_ID 0.0123 --evidence "Provider usage record and date identifying this charge"
```

Use the usage attempt ID, not the experiment ID. Reconciliation appends an audit record; it does not erase the original reservation. Never enter zero because an HTTP request failed or timed out. If evidence is absent, retain uncertainty and the reservation.

If a reported or reconciled charge exceeds its reserved estimate, Skylark pauses further inference across that data directory. The status screen reports the pause. Inspect the recorded model, prices, token bounds, and provider bill; stop active runs and correct local pricing or implementation as needed. Only then acknowledge the specific anomaly:

```text
python -m skylark resolve-usage-anomaly USAGE_ATTEMPT_ID --evidence "Verified provider record, pricing, and the reason for the corrected estimate"
```

This adds an audit record and retains the full charge. It does not increase the allowance, erase uncertain charges, or guarantee the provider's bill. A cancelled or expired worker cannot reserve a new model request.

## Preserve and recover data

Create a private snapshot in a new directory:

```text
python -m skylark --data data/agent-lab backup data/backups/before-upgrade
python -m skylark restore data/backups/before-upgrade data/restored-agent-lab
```

Backup uses SQLite's online backup API for a consistent snapshot, including committed WAL contents. It records a SHA-256 checksum, schema revision, and run count. The snapshot contains unredacted traces and usage records; keep it private. Environment API keys are not copied. Previously generated ZIPs can be exported again from the database.

Restore verifies the manifest and database, refuses an existing destination, suspends queued/running jobs as inconclusive, and clears their worker leases. Completed evidence, recorded effects, and unresolved costs remain preserved. Interrupted restores leave a marker that blocks execution; retry the original backup into another new directory. Do not remove that marker to force startup.

Stop the original installation before launching `python -m skylark --data data/restored-agent-lab serve`. Separate copies do not share budget counters. Verify completed run IDs, event sequences, and an exported regression before using the restored data. The local snapshot limit is 1 GB; this is not a scheduled off-machine backup service or a measured RPO/RTO commitment.

Migrations are serialized at startup. Migration 0001 contains frozen DDL; future schema changes need new Alembic revisions. Before upgrading, back up and run a clean-install check. Old verifier versions remain visible; repairs and exact replay refuse incompatible versions. Reproduce the scenario under the new version to obtain current evidence.

## Export and inspect

Results JSON keeps every scoped attempt, including cancellations, pending jobs, untriggered faults, and infrastructure failures. Exported costs include diagnosis calls attributed to the run. Known token counts do not imply that unreported calls cost nothing.

Incident ZIPs contain fixed members and hashes. Checksums establish integrity, not authorship. Redaction is best effort. Read the files before sharing, and do not execute a regression file obtained from an untrusted person. The `replay` CLI reads data without executing bundled Python. Redacted or incomplete traces cannot establish exact replay.

## Release check

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm run build
npm run test:e2e
cd ..
.\.venv\Scripts\python.exe scripts/release_smoke.py
```

The release check uses its own new data directory, all five fault/control conditions under the original and existing repaired configurations, plus a separate targeted stale-read freshness candidate. It verifies bundle replay, an exported pytest regression, and backup/restore. It spends no API credits. Its output is labeled scripted evidence. GitHub Actions is configured to run offline checks after publication; a local run is not evidence that hosted CI has run.

## Escalation boundaries

- Provider readiness: account access, eligible model, confirmed prices/credits, and expiry require the account owner.
- Runtime privacy: adapters are trusted local code and can access the machine. Do not run untrusted adapters.
- Public release: independent usability, judge access, live results, and funded operations remain separate gates.
