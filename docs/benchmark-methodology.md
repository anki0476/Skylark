# Benchmark methodology

No live NVIDIA evaluation has been performed. Fixtures and mocked-provider results validate the software only.

The fixed packs in `skylark.wind.benchmark` separate development and held-out cases. The held-out pack has four parameter variants for each fault family. Resource, customer, capacity, intent, and seed vary; faults attach to explicit eligible calls. This is a narrow synthetic set, not a representative production sample.

Freeze the pack hash, model/settings, prompt, policy, and verifier before evaluation. Target 12 fault scenarios × 3 fresh trials × 2 configurations plus six controls. Each attempt starts from a fresh snapshot. Compare identical tasks and faults.

An untriggered fault is inconclusive, not passed. Include infrastructure errors, incomplete attempts, denominators, and uncertainty. Repetitions on the same scenario are correlated. Report safety, completion, factual final reporting, coverage, tool calls, latency, and cost separately. Distinguish runtime safeguards from prompt changes and disclose required tool contracts.

The report command and Results screen implement these dimensions with passed/failed/unknown counts. Fault-free controls have no fault-coverage denominator. Rates use observed checks; pending, interrupted, and infrastructure-failed attempts remain visible as unknown. Descriptive 95% Wilson intervals assume independent trials, an assumption repeated scenarios do not satisfy; do not use them as guarantees. Median latency and tool-call counts include only attempts with recorded measurements, with observed counts retained. Costs include all provider calls attributed to the run, including diagnosis, and retain unconfirmed reservations.

Groups separate model/settings, policy, agent, tool, verifier, environment, execution limits, condition, and split. Use `skylark report --comparison ID --output results.json` to freeze a scoped report after the planned jobs complete. The scoped export includes every scheduled run, including failures; a global report also includes exploratory runs and must not be presented as a predeclared benchmark.

The benchmark refuses protocols exceeding the conservative configured allowance. Predeclare fewer trials before collecting results if needed. Never select only successful trials or discard expensive failures.

The initial model probe has a $2 ceiling and at most two available NVIDIA candidates. Select the lowest-cost model that actually supports native tool calls and structured completion for this task. Record identifiers, rates, usage, malformed-output frequency, and latency. Catalogue availability does not establish working access.

Claim template: "On [N] predefined synthetic scenarios and [R] fresh trials per configuration, [model/settings] produced [counts]. The [prompt/runtime] change altered safety from [a/n] to [b/n], and completion from [c/n] to [d/n], with [e] uncovered and [f] infrastructure-failed attempts. This does not establish general agent safety."
