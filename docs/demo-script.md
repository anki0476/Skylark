# 150-second Skylark demonstration script

Record from the running local workbench after restarting the server with the current build. Select **Results → Result scope → held out · live · 12 runs · 99564c86**. Keep the protocol selected throughout the evidence segment so older development runs are not mixed in. The demo can use saved live evidence and should say so; no new paid inference is required to record it.

| Time | Screen | Narration |
|---|---|---|
| 0–15 s | Experiments, fault choices, task box | “An agent may receive a stale answer, a broken receipt, or no confirmation after an operation. Skylark tests what the agent believed against what the tool actually did.” |
| 15–42 s | Incident `fb5098b9` (original stale read); show observed response and final claim | “In this saved live Nemotron run, the tool returned stale availability of two. Authoritative availability was one. The agent completed the booking but reported the wrong remaining count.” |
| 42–70 s | Incident `0c727d86` (guarded stale read); show runtime guard and final claim | “The repaired runtime compared the read with the operation version, refreshed it, and delivered one available slot. The agent then reported the current value. This is a runtime safeguard, not model learning.” |
| 70–105 s | Results scoped to `99564c86`; show stale and incomplete pairs, timeout unknowns, controls | “This protocol was frozen before execution: one held-out variant per fault, one trial per version, and six controls. The stale-read and incomplete-response original runs failed reporting accuracy; guarded pairs passed. One guarded timeout attempt failed before the fault, so its checks are unknown. All six controls passed.” |
| 105–130 s | Protocol attempts and Usage & uncertainty; export JSON | “The interface keeps all 12 attempts in the denominator and separates protocol spend from the whole-project ledger. Eleven completed traces replay exactly. Local estimated cost was about eight-tenths of a cent; it is not a provider invoice.” |
| 130–150 s | Open the [evidence packet](evidence/README.md), show one replay command | “The source, scoped counts, and replayable incident bundles travel with the test build. This small synthetic sample is evidence of the workflow, not a general reliability claim.” |

Before recording, verify the current server offers the protocol selector, that the export URL contains `comparison_id=99564c8636104684b1b7d0b871bef639`, and that no API key, account balance, email, or PowerShell key prompt appears on screen. Capture at a readable resolution and keep the final public video under three minutes.
