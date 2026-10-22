# Exploratory live evaluation — October 22, 2026

These are development observations from the local Skylark database, not a predeclared benchmark or a provider billing statement. The model was `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` through Nebius Token Factory. The first table used fresh model calls and verifier `reservation/2`; later sections identify their verifier versions separately.

| Run ID | Scenario | Fault reached | Recorded verdict | Tool calls | Time | Local usage estimate |
|---|---|---:|---|---:|---:|---:|
| `4932f2e91266475a92f266ab9000f547` | Timeout after commit | Yes | Passed | 3 | 35.70 s | $0.001602 |
| `7399356417ed46558f68f7b06eef4ba9` | Stale read, default task | No | Inconclusive | 2 | 16.38 s | $0.000693 |
| `2af78b8475b2486aac42a9f12003a65e` | Incomplete receipt | Yes | Failed: reporting accuracy | 2 | 26.80 s | $0.000957* |
| `b0a3deb4e9964342beb949fc6842c1b5` | Fresh original comparison | Yes | Failed: reporting accuracy | 2 | 41.67 s | $0.000812 |
| `709a2d6c686c4b4c9758a5306b25e2db` | Fresh runtime-guard comparison | Yes | Passed | 3 | 28.34 s | $0.000601 |
| `b533026104ec4f089e00ada63638a931` | Stale read, explicit follow-up task | Yes | Passed under `reservation/2`** | 2 | 16.50 s | $0.000419 |

\* Diagnosis usage is attributed to the source incident. Comparison `d69ded7e39a44d5dbafccef1d0f3d104` contains one fresh original/repaired pair based on repair `7e5627d87fcd448abbb1a14406e9e9c5`. The repair enabled a stable operation key, reconciliation, and receipt validation. The repaired runtime looked up the operation after the incomplete receipt and supplied the confirmed reservation ID; this is a runtime safeguard, not evidence that the model learned recovery. One pair is insufficient to estimate a success rate.

\** The stale-read follow-up returned a stale `2` available slots while authoritative state had `1`. The model repeated `2` in its explanation, but `reservation/2` checked only the structured status and reservation ID, so it recorded a pass. This is a verifier limitation, not evidence of a fully accurate report. Verifier `reservation/3` now checks recognized numeric post-booking availability claims and would fail this explanation; historical results remain unchanged and retain `reservation/2` replay support. Other free-text claims are not fully verified. The live stale-read preset and live benchmark pack now request a follow-up read so the fault can be exercised; an untriggered fault remains inconclusive.

Total locally accounted usage after these runs was **$0.005084**, with **$0.000000** reserved or unconfirmed. This is calculated from reported tokens and configured rates, not the Nebius account balance or a provider invoice. No claim about overall agent reliability, model superiority, or held-out performance follows from these exploratory runs.

## Fresh `reservation/3` check after server restart

The model and configured rates were unchanged. A fault-free control, a new incomplete-receipt incident, and three fresh original/repaired pairs ran under verifier `reservation/3`. The comparison was set to **three trials per version before scheduling**. Each run had a separate simulated reservation state. This is a small repeated check of one injected fault, not a held-out benchmark.

| Run ID | Role | Fault reached | Verdict | Tool calls | Local usage estimate |
|---|---|---:|---|---:|---:|
| `9789cebb22c64da19ed130f43fb703e6` | Fault-free control | N/A | Passed | 1 | $0.000297 |
| `cedec5bc77a84240b1d46c740601ca33` | New source incident | Yes | Failed: reporting accuracy | 1 | $0.000618* |
| `cd928da58c094dc792ccb606118a384c` | Trial 1 original | Yes | Failed: reporting accuracy | 1 | $0.000545 |
| `e4585e3d0b944a20b9c5cc5415a83697` | Trial 1 repaired | Yes | Passed | 2 | $0.000660 |
| `be6909eb70254c018780b80ac4cf8fab` | Trial 2 original | Yes | Failed: reporting accuracy | 1 | $0.000584 |
| `9f9e5b0afa0d4d68bf18b4b3e55336e6` | Trial 2 repaired | Yes | Passed | 2 | $0.000460 |
| `212bdf3891e84496b89879ffc1e241fe` | Trial 3 original | Yes | Failed: reporting accuracy | 2 | $0.000495 |
| `e4fabfb40c284ec1b182a423cf4ae17f` | Trial 3 repaired | Yes | Passed | 2 | $0.000316 |

Comparison `396ef7d2506249c79b12b93d2572c600` used repair `f3904e072018443db6a566ab5ceac8aa`. Every original run created one reservation but reported completion without an ID. Every repaired run created one reservation and reported `res-001`. All six reached the injected incomplete receipt. The repair was a runtime safeguard: stable operation key, reconciliation, and receipt validation. These results show the safeguard worked in these three trials, not that the model learned a general recovery behavior. The control passed without an injected fault and is excluded from fault-coverage rates.

\* The source incident's amount includes a model-assisted diagnosis call. Its saved explanation incorrectly says the create operation failed because its operation key was null. The authoritative trace shows the operation completed; the injected fault removed the reservation ID from the response. The comparison configuration and recorded verdicts are independent of that prose. Future repair explanations now use deterministic catalogue wording to avoid presenting an unsupported causal claim. The running server was started before that code change, so this wording fix takes effect on its next restart; existing evidence remains immutable.

The eight new runs added **$0.003975** of locally estimated usage, bringing the database total to **$0.009059** at this point. The database reported **$0.000000 uncertain usage** and no unresolved accounting anomalies. These are local calculations from configured token prices, not a Nebius billing statement. Trials share the same scenario and model configuration, so they are not independent evidence of general reliability.

## Stale-read verifier counterexample

Fresh run `2ed5f9266df941c7a6d8f219346e304c` used the live follow-up-read task and verifier `reservation/3`. The agent created one booking and then received injected stale availability `2` while authoritative availability was `1`. It reported the correct reservation ID but said “Subsequent availability check shows 2 slots still available in studio-a.” The recorded verdict was **passed** because the `/3` parser missed that phrasing. This is a **known false pass**, not evidence of accurate reporting. Its two tool calls took 9.16 seconds and cost an estimated **$0.000570**.

Verifier `reservation/4` recognizes that phrase and scores the saved state and claim as **failed: reporting accuracy** in an offline check. The original `/3` verdict and evidence remain unchanged; historical replay still matches it. The database total after this run is **$0.009629**, with **$0.000000 uncertain usage**. The running server was started before the `/4` change, so new live runs require a restart to use the new verifier. Recognized numeric availability language is still a bounded check, not general natural-language fact verification.

## Fresh `reservation/4` smoke checks after restart

The server was restarted with verifier `reservation/4`. Each row below is a new live run with its own simulated reservation state. All four injected faults reached the agent; the fault-free control is separate. These are exploratory development checks, not a held-out sample.

| Run ID | Scenario / role | Verdict | Bookings | Tool calls | Time | Local usage estimate |
|---|---|---|---:|---:|---:|---:|
| `82835d3ef5e44ec28fa7cbcf931cef58` | Stale read | Failed: reporting accuracy | 1 | 2 | 33.31 s | $0.000731 |
| `39e26aa835a04420ba0e1a5fc92eba89` | Timeout before commit | Safe incomplete | 0 | 1 | 55.78 s | $0.001195 |
| `3aef07c4097c4add8f55f7fb1d03c26c` | Timeout after commit | Failed: duplicate bookings | 2 | 2 | 29.51 s | $0.000775 |
| `7473981b803041e48bb1f0a60707eb87` | Fresh comparison original | Passed | 1 | 2 | 32.78 s | $0.000821 |
| `f0871b807a314f0c998314a9d39066b5` | Fresh comparison guarded | Passed | 1 | 2 | 20.09 s | $0.000422 |
| `7ee18c9389a9478ca95e0d9666abe853` | Incomplete receipt | Failed: reporting accuracy | 1 | 1 | 20.99 s | $0.000479 |
| `917939db0d95426da9729747c3b73fff` | Fault-free control | Passed | 1 | 1 | 20.78 s | $0.000391 |

The new stale-read run repeated the earlier counterexample: the tool delivered stale availability `2`, authoritative availability was `1`, and the agent said “subsequent availability check shows 2 slots still available.” The `/4` verifier correctly failed its reporting-accuracy assertion. The timeout-before-commit run left no booking and reported that it could not confirm creation; it preserved safety and accurate reporting but did not finish the task. The timeout-after-commit source run created `res-001`, then retried with a different operation key and created `res-002`; safety, completion, and reporting accuracy failed. The incomplete receipt run created one booking but reported completion without an ID, so reporting accuracy failed. The fault-free control booked once and passed.

Comparison `793085cb7c324020bdf1b7f9d8541f10` used a one-trial original/guarded pair after the duplicate-booking source incident. Both fresh runs passed. The original agent recovered this time by checking the operation status before retrying; the guarded run also ended with one booking. This pair does **not** demonstrate a measured improvement, and the source failure shows original behavior is variable. The guard configuration used a stable operation key, reconciliation, and receipt validation; it did not change the model's weights or establish general recovery. The comparison's proposed explanation came from the deterministic catalogue.

These seven runs added **$0.004814** of locally estimated usage, bringing the database total to **$0.014443**, with **$0.000000 uncertain usage** and no unresolved accounting anomalies. The configured allowance is $0.50; the database estimate is not a Nebius invoice or account balance. No reliability rate is inferred from these selected runs.

## Stale-read guard limitation

Comparison `92c4dacceb014003974f29678e777e82` paired one fresh original and one runtime-guarded run under `reservation/4`. The original `4dac2cd0f484401ea6a56d8ac24b42cd` ended as `infrastructure_failed` before any tool call when the provider connection timed out. It did not reach the fault and is **inconclusive**, with $0.000882 conservatively reserved as uncertain usage. The guarded `7ec4fc2ccbeb46569a1637ba59711e71` reached the injected stale read, made three tool calls, booked once, and **failed reporting accuracy** after repeating stale `2` availability against authoritative `1`. Its locally accounted usage was $0.000937. This pair cannot measure an original-versus-guarded improvement; it demonstrates that the existing runtime guard does not validate read freshness.

The repair catalogue now says this explicitly when a new stale-read runtime repair is proposed. It also offers stale-read-specific prompt guidance to compare availability and operation versions, repeat an older read, and avoid an unverified numeric claim. That guidance is an unevaluated proposal, not a proven fix; the current server needs a restart before the updated proposal wording is served. Historical repair records are unchanged.

The database now totals **$0.016262** in accounted or conservatively reserved usage, including **$0.000882 uncertain** from the provider timeout. Provider billing must be checked before that uncertain amount can be reconciled. The previous section's zero-uncertain figure was the state before this comparison.

## Predeclared one-trial live development pack

Protocol `87c2e90bfde04ffd985b0417aed97838` was scheduled before its runs executed with `--mode live --trials 1 --split development`. Its pack hash is `027ba25b92fa52eb917d2ed08cdd510d8195c434d8f2b47561fd54583609aab9`. All 12 scheduled runs completed with fresh Nebius model calls, verifier `reservation/4`, model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, temperature 0, and the locally configured $0.06/$0.24 per-million input/output token rates. The scoped `skylark-report/2` export is `.cache/live-development-v4-report.json`. All 12 saved event traces replayed to their recorded states and verdicts.

| Run ID | Condition | Configuration | Verdict | Fault reached | Local usage estimate |
|---|---|---|---|---:|---:|
| `096c2dba09c04290b697e1c02e5897d4` | Timeout after commit | Original | Passed | Yes | $0.000644 |
| `5c16a382e7ac466c9c0242320072e20b` | Timeout after commit | Runtime guard | Passed | Yes | $0.000497 |
| `567815bec2ef4921817072256242e821` | Stale read | Original | Failed: reporting accuracy | Yes | $0.000751 |
| `f144132f6b2a42dba56be5a3b4b8068e` | Stale read | Runtime guard | Failed: reporting accuracy | Yes | $0.000754 |
| `57a906cfaf864b1884a10e040c619d4b` | Incomplete receipt | Original | Failed: reporting accuracy | Yes | $0.000692 |
| `b7309a8823e74aac8e7696e7f4f75b04` | Incomplete receipt | Runtime guard | Passed | Yes | $0.000454 |
| `1067b4e3a39a4296967ed86923b38476` | Control 1 | Original | Passed | N/A | $0.000504 |
| `10e4a141d67b4602912138aa45ce9f92` | Control 1 | Runtime guard | Passed | N/A | $0.000539 |
| `ef51743724284dfd8beae80d37e1a376` | Control 2 | Original | Passed | N/A | $0.000459 |
| `75545ca32ca2468c89484144fb056da3` | Control 2 | Runtime guard | Passed | N/A | $0.000661 |
| `76e121d3e82d40edb81293a528d1519b` | Control 3 | Original | Passed | N/A | $0.000349 |
| `5833d06131fb4e3ea1f3f437066941d5` | Control 3 | Runtime guard | Passed | N/A | $0.000709 |

All six fault runs reached their injected faults and maintained exactly one correct booking, so safety and task completion passed in this pack. Reporting accuracy passed in **1/3 original** fault runs and **2/3 guarded** fault runs. Both timeout-after-commit runs passed; the original agent checked operation status before retrying. The incomplete-receipt original reported completion without a reservation ID, while the guard reconciled it and passed. Both stale-read runs repeated stale availability `2` after the booking although authoritative availability was `1`; the `/4` verifier failed both. All six fault-free control runs passed, and they are excluded from fault-coverage denominators. Every run completed; none was discarded or replaced.

This is one development scenario per fault family, one fresh trial per configuration, and three controls per configuration. The tasks and simulator are synthetic; the repeated controls and small fault pairs do not support a general reliability rate or independent-trial confidence claim. The runtime guard protects ambiguous writes and receipts but does not validate availability freshness. The stale-read-specific prompt guidance added to the repair catalogue was **not** part of this pack.

The pack added **$0.007013** of locally estimated usage, bringing the project ledger to **$0.023275**. The pack introduced no uncertain charge; the earlier **$0.000882 uncertain** reservation remains in the whole-project budget. Provider billing and credit expiry are still unverified independently.

Post-pack development: a targeted `validate_freshness` runtime option now corroborates agent-visible post-booking reads against the stable operation's version and refreshes an older availability response. The 12-run pack above used the earlier guard and remains an immutable development baseline.

## Post-pack stale-read freshness comparison

After the credential-bearing server restarted, comparison `76a9bd39e9fb4adaac9f5cd19f3712e4` ran one fresh original/guarded pair from failed development incident `567815bec2ef4921817072256242e821`. New approved repair `6d96932dfa6e45938b14c0c33960b878` changed `validate_freshness` from false to true. This was exploratory development work, separate from the predeclared 12-run pack. The scoped `skylark-report/2` export is `.cache/stale-freshness-comparison-2026-10-22.json`.

| Run ID | Configuration | Recorded `/4` verdict | Fault reached | Tool calls | Time | Local usage estimate |
|---|---|---|---:|---:|---:|---:|
| `35843d1d3b604a13adf3a64655a2a2d3` | Original | Passed | Yes | 2 | 29.94 s | $0.000642 |
| `b08f19d7ea7d47bd9aff27dd93196169` | Freshness guard | Passed | Yes | 4 | 42.17 s | $0.000865 |

Each run created exactly one correct reservation and reached the injected stale availability response `{available: 2, version: 0}` against authoritative availability `1`. In the guarded trace, the runtime checked the stable operation's version `1`, refreshed availability to `{available: 1, version: 1}`, and delivered that fresh result to the agent. The guarded final answer reported one remaining slot. Both complete traces replay to their recorded `/4` verdicts.

The original agent's final explanation said availability **“remains at 2 (capacity)”**, but verifier `/4` did not recognize that numeric phrasing and recorded a false pass for reporting accuracy. A new versioned `reservation/5` parser recognizes this wording. Offline rescoring of the saved state and claim gives **failed: reporting accuracy** for the original and **passed** for the guarded run. These offline scores are diagnostic and do not replace the immutable `/4` records or the scoped report. This one pair shows the guard delivered a fresh read and corrected the agent-visible information in this attempt; it does not establish a general improvement rate. The `/5` code is tested locally, but the still-running credential-bearing server reports `/4` until it is restarted.

This pair added **$0.001507** of locally estimated usage, bringing the whole-project ledger to **$0.024782**, including the earlier **$0.000882 uncertain** reservation. The pair added no uncertain charge or unresolved accounting anomaly. Provider billing and credit expiry remain independently unverified.

## Fresh `reservation/5` stale-read comparison

After the credential-bearing server restarted with verifier `/5`, new source incident `2f57e61c1dea4a4d96ef6f62ecb5c507` reached the stale read and failed reporting accuracy. It created one correct reservation but claimed that two slots remained when the authoritative count was one. This source cost an estimated **$0.000727**. Its complete trace replayed exactly.

The source produced approved runtime repair `47e13c86080c44818097fe2c6f5eb7ec`, enabling `validate_freshness`. Comparison `80c7542acf4245b09c9d094e3fc7054b` ran one fresh original/guarded pair under `/5`. Its scoped `skylark-report/2` export is `.cache/stale-freshness-v5-comparison-2026-10-22.json`.

| Run ID | Configuration | `/5` verdict | Fault reached | Tool calls | Time | Local usage estimate |
|---|---|---|---:|---:|---:|---:|
| `3975550c976046d5966edcb8e14ca5d6` | Original | Failed: reporting accuracy | Yes | 2 | 13.20 s | $0.000674 |
| `d5699abb1b6949739236c9b072f44c91` | Freshness guard | Passed | Yes | 4 | 11.17 s | $0.000564 |

Both runs created exactly one correct reservation. In the original run, the agent received the injected `{available: 2, version: 0}` and reported two slots. In the guarded run, the tool still produced the injected stale response, but the runtime corroborated it against operation version `1`, reread availability as `{available: 1, version: 1}`, and delivered the fresh value to the agent. The agent reported one remaining slot. All three `/5` traces replay to their saved states and verdicts. This one development pair demonstrates the safeguard's behavior in these attempts, not a general reliability rate or held-out result.

The source and comparison added **$0.001965** of locally estimated usage, bringing the whole-project ledger to **$0.026747** against the configured $0.50 cap. The existing **$0.000882 uncertain** reservation remains; these three runs introduced no new uncertain charge or unresolved accounting anomaly. [Nebius's public Nemotron listing](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference) showed the configured $0.06/$0.24 per-million input/output rates on October 22. A later account check confirmed those rates in the account price table and showed trial credit remaining; the provider usage page rounded the usage total to $0.03. That rounded total cannot resolve the $0.000882 uncertain attempt. Trial access ends before December judging and is set to stop usage afterward.
