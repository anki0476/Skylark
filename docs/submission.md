# Submission checklist

The four official judging criteria and the evidence required for each are mapped in [judging readiness](judging-readiness.md).

Working-app target: October 25 evening IST. Final evaluation/submission: October 26–29. The official deadline is October 30, 2026 at 10:00 a.m. PDT (10:30 p.m. IST); leave time for upload and review. [Official rules](https://nebiusglobalaihackathon.devpost.com/rules).

- [x] Verify local Nebius access and Nemotron Nano tool calling in fresh runs; its [public Nebius listing](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference) shows $0.06/$0.24 per million input/output tokens as of October 22. Confirm account-applied billing separately.
- [x] Check the account's trial balance, remaining trial time, and applied Nemotron Nano rates. The October 22 account check showed trial access ending before the December judging period; do not include private billing details in the public submission.
- [x] Set post-trial usage to stop; the account confirmed the saved preference and no charges after trial. A separate automatic top-up setting was not found.
- [x] Observe a genuine live-agent failure, or honestly report passing scenarios. See the [exploratory live evidence](live-evaluation-2026-10-22.md).
- [ ] Compare an approved repair with fresh repeated trials and controls.
- [ ] Publish raw counts, uncertainty, failures, latency, and cost.
- [ ] Have another person follow the [independent clean-install review](independent-review.md), including an exported regression, and record any blockers.
- [x] Pass hosted Python, browser, build, and release-smoke checks; PR #1 was merged into `main` on October 22. The workflow is now configured to verify an archive and upload it from a successful `main` push for review.
- [ ] Publish an MIT-licensed repository with attribution and setup instructions.
- [ ] Secure free judge access through December 15 and verify live-inference access for that period. The current trial expires beforehand, and the saved preference stops usage at its end.
- [x] Check track fit against current official rules. Best Apps and Agents is the recommended track for the present Token Factory/Nemotron app; Coding and Agentic Engineering specifically calls for code-writing/testing tools in Token Factory Sandboxes, which Skylark does not use.
- [ ] Record a public YouTube video under three minutes.

## Suggested 150-second demonstration

0–20s: Explain the missing-confirmation problem and agent request.

20–55s: Show a clearly labeled live incident, the timeout, and actual reservations. Label saved evidence when used.

55–85s: Show independent safety, completion, and reporting checks.

85–115s: Review and approve a targeted repair.

115–140s: Show fresh comparisons, controls, and limitations.

140–150s: Export a reproducible regression and show local adapter integration.

Do not substitute fixtures for live evidence or claim that runtime guards teach the model. Never publish an API key. Do not assume a recording alone satisfies judge access requirements.

Rules: https://nebiusglobalaihackathon.devpost.com/rules
