# Limited live benchmark evidence

The [summary JSON](limited-held-out-2026-10-22.json) contains every scheduled attempt in protocol `99564c8636104684b1b7d0b871bef639`, all eight condition/configuration groups, hashes, checks, execution statuses, timing, and locally estimated **protocol** spend. It omits account-wide budget, provider credentials, and the private SQLite database. [The interpretation and limitations](../live-held-out-2026-10-22.md) were written against the scoped source report.

The `bundles/` directory contains one best-effort-redacted incident bundle for each of the 12 attempts. All 11 `completed` bundles were replayed to their saved state and verdict; the one `failed` attempt is included for inspection but is incomplete and must not be represented as a replayable success. To check a completed bundle after installing Skylark:

```powershell
.\.venv\Scripts\python.exe -m skylark replay docs/evidence/bundles/fb5098b93b7e4c128e0c2a8aba62f6dc.zip
.\.venv\Scripts\python.exe -m skylark replay docs/evidence/bundles/0c727d868ff7492f9789ca0c11bb9e29.zip
```

Those two are the original and guarded stale-read attempts. The incomplete-response pair is `15eff0e2aca949689e451924463feed3.zip` and `c56c788d1d60452e9c860bc8014bb5a0.zip`. The inconclusive guarded timeout is `b7ade6dae7d04c70b8a81c99095df3d9.zip`; its fault was never triggered.

These are synthetic reservation tasks and saved model decisions. Replaying them checks preservation of the recorded trace, not fresh model behavior or production reliability. Review every bundle before public distribution; export redaction is best effort.

The later [independent-agent pilot](real-agent-pilot-2026-10-24.md) has a separate pair of live Nemotron runs and two replayable bundles. It tests one newly built booking agent through the trusted local adapter; it is not part of the 12-attempt held-out protocol.
