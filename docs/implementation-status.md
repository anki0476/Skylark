# Implementation status — October 18, 2026

Skylark now tests agent recovery from tool failures. The robotics prototype is preserved at `d8a07d5`; its data was not migrated.

## Implemented

React workbench; local FastAPI API; SQLAlchemy/SQLite WAL and Alembic; durable runs and event journals; exclusive worker leases and fencing; supervised attempts; cancellation; reservation simulator; three faults and two controls; independent verifier; immutable snapshots; reviewed repair comparisons; Nebius integration and spending controls; Python adapter; ZIP exports/replay; best-effort redaction; fixed evaluation packs.

## Verified

All 156 Python tests passed: 98 agent-lab/provider/hardening/operations tests and 58 retained robotics tests. Four Playwright tests passed: complete fixture/repair/export/refresh workflow, narrow-screen layout, polling without SSE or a recent-history entry, and settings keyboard focus. TypeScript and the Vite production build succeeded. The clean virtual environment installed the final wheel and reproduced all five fault/control conditions under both configurations, replayed their bundles, passed an exported pytest regression, and preserved the same evidence through backup/restore. The installed CLI also completed the supplied adapter through its supervised process. `pip check` found no broken requirements. A Starlette warning recommends migrating its test client from HTTPX to HTTPX2; the locked test environment passes.

## Additional hardening

- Checkpoint returned effects before honoring cancellation; record the response actually delivered after runtime safeguards.
- Serialize startup migrations, freeze initial DDL, and handle concurrent downloads without shared temporary filenames.
- Reject incomplete replay traces and incompatible repair/comparison dependencies. Verifier version is now `reservation/2`; historical runs remain preserved separately.
- Drain terminal SSE events, fall back to polling, and load selected incidents even outside the recent-history limit.
- Report safety, completion, reporting, coverage, unknowns, execution statuses, token counts, timing, and cost separately. Do not pool incompatible model/verifier versions.
- Add results export, a portable offline release check, a local archive builder, an operations guide, and an internal submission/video draft.
- Configure offline GitHub Actions verification; no hosted CI run or publication has occurred.
- Launch the actual Windows virtual-environment interpreter, stop orphaned workers/attempts, and test cancellation, deadlines, and real process termination before and after effect checkpoints.
- Reject malformed usage/decisions, fence model spending after ownership loss, and pause further inference after an underestimated charge until an audited resolution.
- Snapshot SQLite consistently; verify hashes/schema/integrity; restore with pending jobs suspended and block incomplete restores. Private backups remain excluded from release archives.
- Retry only SQLite startup lock contention within a bounded window; cache deterministic ZIPs under their content hash to avoid replacing a concurrently opened export.
- Restrict the demo CLI to its own queued run.

## Remaining gates

- No Nebius key configured; no live inference or paid API usage occurred.
- Model selection, real capability/cost measurement, live repair quality, and held-out model results require account setup.
- Local adapters can supply custom versioned environments and verifiers. Automatic bundle replay and repair presets support the reservation domain; other domains need trusted replay and repair integration.
- OIDC, organizations, tenant isolation, PostgreSQL runtime, cloud runner pairing, shared hosting, off-machine recovery operations, and production capacity remain post-hackathon work.
- Public repository publication, independent user trial, final video, judge access, and submission are not complete.

The October 19 reminder now covers Nebius and the agent experiment; photographs are no longer required.
