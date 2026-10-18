# Production roadmap — acceptance gates, not existing capabilities

## Private multi-user service

- PostgreSQL repository and tested migration path; OIDC; organizations and owner/editor/viewer roles.
- Authorization on every record, stream, artifact, and job; row-level security and negative cross-tenant tests.
- Revocable workspace-scoped runner pairing. Runners pull approved jobs over HTTPS; no arbitrary callbacks or uploaded code.
- Customer code and model credentials remain local. Local verdicts are customer-reported, not independently attested.
- Authorized object storage, expiring downloads, retention/deletion controls, and per-workspace quotas.

## Operations

- Stateless replicas, durable short-claim jobs, no network calls in DB transactions.
- Worker leases, backpressure, tenant fairness, provider-limit coordination, and bounded retries.
- Metadata telemetry, queue/heartbeat/usage alerts; content capture off by default.
- Backups, restoration drills, migration rollback/roll-forward, incident runbooks, and operational ownership.
- Dependency/secret scanning, independent security review, abuse controls, and remediation.

## Capacity gate

Target: 5,000 accounts, 100 concurrent dashboards, 20 active local runners, 50 aggregate events/second, and bursts of 100 metadata requests/second. Run a one-hour sustained test and a longer soak test on funded infrastructure.

Targets: metadata API p95 below 300 ms excluding model inference/downloads; no acknowledged event loss; no cross-tenant access; no duplicate execution from queue redelivery; no concurrent budget-reservation overspend. Exercise restarts, worker loss, DB failover, expired credentials, and restores. Initial RPO: 15 minutes; RTO: four hours.

Mocked-provider tests measure the control service only. Live capacity depends on provider quotas and cost. Hosting, operations funding, security review, and measured capacity must be completed before public launch. No paid services are provisioned by this repository.
