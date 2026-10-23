# 150-second Skylark demonstration script

Record from the current local workbench. The [independent-agent pilot](evidence/real-agent-pilot-2026-10-24.md) already made fresh Nemotron calls; show its saved evidence without entering a key or paying for another run. When the app uses `.cache/ux-preview`, the Connect agent page links directly to both saved attempts.

| Time | Screen | Narration |
|---|---|---|
| 0–18 s | Clean Experiments page, sample test, compact **Connect my agent** button | “Skylark helps us reproduce an agent failure, check what actually happened, and test a proposed fix. The sample is safe to try; we also connected a separate model-driven agent.” |
| 18–40 s | [Pilot report](evidence/real-agent-pilot-2026-10-24.md), agent and adapter source names, saved run IDs | “This booking agent has no Skylark imports. A local adapter connected its real Nemotron tool decision to a synthetic reservation system. We injected a timeout after the booking succeeded but before the confirmation arrived.” |
| 40–76 s | Connect agent → **Original: failed**; show tool calls, two reservations, failed safety check | “The agent interpreted the missing confirmation as failure and retried. The verifier found two bookings, even though the agent was asked for one.” |
| 76–112 s | Connect agent → **With safeguard: passed**; show fault reached, one reservation, passed checks | “Skylark proposed a runtime guard and tested the same connected agent again. The guard reconciled the uncertain first operation, leaving one booking. This is a runtime safeguard, not a claim that the model learned or its code was patched.” |
| 112–135 s | Replayed original and guarded bundles, both `matches_recorded: true` | “Both runs used fresh Nemotron calls and their saved traces replay to the recorded failed and passed verdicts. We can inspect the evidence without another model request.” |
| 135–150 s | Results held-out scope or [evidence packet](evidence/README.md) | “The broader held-out pack includes an inconclusive attempt, and this pilot is only one synthetic agent and fault. Skylark keeps those limits visible.” |

Before recording, confirm the server uses the current frontend build and `.cache/ux-preview` data, and that both pilot links open the expected run IDs (`321ce526` and `b5cba17c`). Do not show an API key, credit balance, or PowerShell key prompt. Keep the public video under three minutes.
