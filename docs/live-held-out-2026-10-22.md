# Limited live held-out protocol — October 22, 2026

This protocol was frozen in the local database before execution. It is a deliberately small, budget-constrained sample, not the 78-run target or a general reliability estimate.

- Protocol ID: `99564c8636104684b1b7d0b871bef639`
- Scenario pack SHA-256: `299ff9c89e13e55017047e88bf24ca692c72a1002c23b39f4292eaf36ae318e9`
- Full protocol SHA-256: `130ac0df635569791d929286a42f7089f805e13e4d0a20e54af3d8375932d7ef`
- Execution: `live`; split: `held_out`; model: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
- Selection: first fixed case in each of three fault families, one trial of the original and repaired configuration, plus three fault-free controls under both configurations (12 runs total).
- Repair policy: stable operation key, reconciliation, receipt validation, and freshness validation. Freshness validation is enabled only on the repaired side (6 of 12 snapshots).
- Snapshot state before worker start: all 12 runs queued. No held-out verdicts had been observed.

Predeclared reporting: publish all 12 attempts, including infrastructure failures and unknown checks; keep each fault family and control condition visible. Report safety, task completion, reporting accuracy, fault coverage, latency, tool calls, and accounted versus uncertain cost. Compare only like-for-like model, verifier, and task versions. Do not pool this result with exploratory development runs, call the small sample a reliability rate, or infer production safety from a synthetic reservation task.

After execution, export a report scoped to the protocol ID and verify every saved run by replay before citing results. The local spending allowance is $0.50; at the configured $0.06/$0.24 per-million input/output rates, the preflight maximum for these 12 runs is $0.370944. The earlier project ledger was $0.026747 accounted, including $0.000882 uncertain, leaving room under the cap at scheduling time. These are local estimates, not a provider invoice.

## Observed result

All 12 scheduled attempts reached a terminal status: 11 completed and one failed before making a tool call. Eleven completed traces replay exactly to their recorded verdicts. The failed attempt is retained in the denominator and cannot be replayed as a complete regression. The scoped source export is `.cache/live-held-out-2026-10-22-report.json` (a local, ignored evidence file). A [curated summary and inspectable bundles](evidence/README.md) are prepared separately; review them before publication.

| Condition | Original | Runtime guard | Fault reached |
|---|---|---|---|
| Timeout after commit | Passed | Inconclusive: execution failed after two invalid or truncated model responses, before any tool call | 1 of 2 |
| Stale read | Failed reporting accuracy | Passed after corroborating the stale read against operation status and refreshing availability | 2 of 2 |
| Incomplete response | Failed reporting accuracy | Passed with the reservation identifier recovered | 2 of 2 |
| Fault-free controls | 3 of 3 passed | 3 of 3 passed | Not applicable |

The original timeout run passed on this single trial. Because the guarded timeout run never reached the fault, this pair says nothing about comparative recovery. Across the three fault cases, original had 1 passed and 2 failed; guarded had 2 passed and 1 inconclusive. The apparent difference is not a reliability rate or a causal estimate. Five of six configured fault runs actually triggered their fault. All six controls passed. The 12 attempts made 30 provider requests and accounted for $0.008189 at configured local token prices, with no new uncertain charge. The whole-project ledger after the run was $0.034936 accounted, including $0.000882 of earlier uncertain usage. Neither number is a provider invoice.

The stale-read pair shows a useful distinction: the original reported stale availability `2` when authoritative availability was `1`; the guarded run observed the stale value, checked the operation version, refreshed to `1`, and reported it accurately. The incomplete-response pair likewise changed the final claim from a missing reservation ID to `res-001`. These are effects of a **runtime guard** on a small synthetic task, not evidence that the model learned a general recovery skill. Model revision was reported as unknown by the endpoint, and only one held-out variant per fault family was sampled.
