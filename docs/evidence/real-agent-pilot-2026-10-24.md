# Live independent-agent pilot — October 24, 2026

This is one controlled test of a newly built, independent booking agent, **not** a connection to an existing deployed customer agent. `examples/pilot_booking_agent.py` has no Skylark imports. It used `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` through Nebius Token Factory to choose `create_reservation` in each run. The trusted local adapter routed that operation into Skylark's synthetic reservation system. A post-commit timeout was injected after the first booking, before the confirmation reached the agent. The agent's deliberately faulty retry layer tried again without a stable operation key.

| Same agent and fault | Original | With proposed runtime guard |
| --- | --- | --- |
| Run ID | `321ce526347541c0bac2aeb52599852e` | `b5cba17cf0cb4ec5851e0201deeaf3a9` |
| Fresh model calls | 1 | 1 |
| Reported input/output tokens | 377 / 395 | 377 / 296 |
| Fault reached | Yes | Yes |
| Verified reservations | 2 | 1 |
| Independent verdict | Failed | Passed |

The adapter SHA-256 for both runs was `858437320858300f7b985a3001c5299b2512c6f3f6dc0005763f95dec1e959ed`. The stored model-usage and model-decision events were checked in both runs; their model snapshots matched. Locally estimated cost for the two calls was **$0.000212** at the configured $0.06/$0.24 per-million input/output rates. This is not a Nebius invoice. No API key is in the saved report or bundles.

The [original bundle](bundles/321ce526347541c0bac2aeb52599852e.zip) and [guarded bundle](bundles/b5cba17cf0cb4ec5851e0201deeaf3a9.zip) both replayed to their recorded states and verdicts with verifier `reservation/5`. Replay checks saved evidence; it does not make fresh model calls. The CLI proposed and tested a **runtime reservation guard** without editing the independent agent. It did not patch or deploy that agent, and this single comparison cannot establish a general success rate or support for n8n, Make, or arbitrary agents.
