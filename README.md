# Skylark

**Reviewed training data for robot vision.**

Skylark helps test whether proposed labels for tabletop objects are useful enough
to justify building an assisted labeling product. The intended audience is student
robotics teams and small labs working with apples, cups, and bottles.

## Current status: feasibility pipeline implemented

This repository implements the plan's **first milestone**, not the completed
four-screen web application. No Nebius account, API key, credits, or annotated real
photographs were available during implementation. No live inference has run, no
model has been selected, and no real accuracy or labeling-time result is claimed.

The plan explicitly requires a live accuracy/cost gate **before the full UI**.
Accordingly, React/Konva, background product jobs, and deployment remain deferred.
The local FastAPI data/review API, CLI, annotation validation, evaluation, ledger,
cache, and reviewed YOLO export are ready to support that experiment.

Implemented:

- Account model discovery using Nebius's public `/v1/models` API.
- Explicit, consented vision inference through the OpenAI-compatible Nebius SDK.
- A maximum-$2 experiment allowance shared across runs in one SQLite store.
- One retry maximum, conservative accounting for unknown billing, and cached successes.
- Per-image checkpoints, cancellation state, raw prediction metrics, and model comparison.
- JPEG/PNG validation, EXIF orientation normalization, and resized-coordinate restoration.
- Manual-review persistence and reviewed-only YOLO ZIP exports.
- Scene-split and exact-image duplicate checks, fixed-IoU evaluation, and timing summaries.
- A clearly marked, deterministic offline fixture that **cannot pass the live gate**.
- A portable visual report with prediction/reference overlays and per-condition results.

## Install on Windows

Requires Python 3.10 or newer. Python 3.12 is recommended and is the tested version.
`python` can resolve to a nonfunctional Windows Store alias; use `py` or a full
Python executable path in that case.

```powershell
.\scripts\setup.ps1
# Or: .\scripts\setup.ps1 -Python 'C:\path\to\python.exe'
```

Manual installation, also suitable for macOS/Linux with `.venv/bin/python`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m skylark status
```

The lock file records the versions exercised here. No global packages or Node
dependencies are needed for this milestone. `data/`, `runs/`, `.env*`, virtual
environments, and caches are excluded from Git.

## Try the offline example

```powershell
.\.venv\Scripts\python.exe -m skylark offline-demo data/example
.\.venv\Scripts\python.exe -m skylark validate data/example/manifest.json
.\.venv\Scripts\python.exe -m skylark --data-dir data/example/state serve data/example/manifest.json
```

Open `http://127.0.0.1:8000/docs` for the local API explorer. This is a feasibility
tool, **not the finished product UI**. The fixture uses labeled geometric shapes
and scripted predictions (including a deliberate missed cup), not photographs,
an NVIDIA model, or a measured model benchmark. Its `gate.status` must be
`not_passed`. Creating a fixture will not overwrite an existing directory.

Open `data/example/report.html` in your browser for the visual example. Toggle
proposals and reference boxes to see the deliberately missed cup. It is a saved,
offline inspection report, not a live labeling interface.

Try `GET /api/dataset`, `GET /api/images/fixture-0`, and `GET /api/runs`. To exercise
review/export, submit a complete review through `PUT /api/reviews/fixture-0`, then
download `GET /api/export`. Reviews survive restarts. There is intentionally no
HTTP route that sends images or starts a paid request.

## Tomorrow's live experiment

1. Create/sign in to Nebius Token Factory and claim the event and Builders Program
   credits. Confirm that credits are actually applied and note their expiry.
2. Disable automatic top-ups in the provider console. These commands cannot
   inspect your actual balance, expiry, or billing settings.
3. Configure `NEBIUS_API_KEY` in the shell running Skylark. Do not paste it into
   chat, screenshots, commands that will be shared, or the repository.

```powershell
# Hidden input. The key stays in this shell's process environment.
$taskSecret = Read-Host 'Nebius API key' -AsSecureString
$env:NEBIUS_API_KEY = [System.Net.NetworkCredential]::new('', $taskSecret).Password
.\.venv\Scripts\python.exe -m skylark models --output data/catalog.json
```

4. Prepare the real development dataset following [the annotation protocol](docs/dataset-protocol.md).
   Use `examples/manifest.template.json` as a shape reference. The template is
   deliberately invalid until its photograph, dimensions, and manual annotations
   have been supplied and confirmed. Never mark an uninspected image verified.
5. Copy `examples/experiment.template.json` to `data/experiment.json`. Choose at
   most two public NVIDIA image-capable models from the account catalog. Confirm
   their input modalities, public availability, and current per-million prices
   in the console. The catalog's verbose `pricing.prompt`/`completion` values are
   **per token**, so multiply by 1,000,000 when transcribing to this config.
6. Set the confirmation flags only after checking them. Keep the experiment limit
   at or below $2. Prices and example model names are not filled with guesses.

```powershell
.\.venv\Scripts\python.exe -m skylark validate data/benchmark/manifest.json
.\.venv\Scripts\python.exe -m skylark probe data/benchmark/manifest.json `
    --config data/experiment.json --output runs/first-probe.json --confirm-send-images
```

The command sends **only development images** to Nebius. Exit code 0 means the
development gate passed; 2 means the experiment ran but did not pass; 1 means
configuration, data, access, or budget prevented it. Ctrl+C checkpoints the run
as cancelled. Repeating the same probe uses cached successful images. A changed
prompt, image, class list, model, output format, or resize setting invalidates the cache.

The gate requires exactly 20 real, manually labeled development images covering
all four conditions and three classes, a completed NVIDIA vision candidate with
precision and recall >= 70% at IoU 0.5, and no unresolved billing or budget excess.
Select highest F1, then lowest original recorded cost. Cached requests don't
artificially make a model win the price tiebreaker. Development success is not a
claim of held-out accuracy, training improvement, or robotic grasp readiness.

If no public NVIDIA vision route is suitable, stop and assess the plan's separate
vision-plus-NVIDIA-specification fallback. That two-model fallback is not yet
implemented and cannot be presented as a passing NVIDIA vision experiment.

## Cost accounting

The default probe limit is $2. A conservative estimate for every uncached image,
including its one possible retry, must fit before the batch begins. Each API
attempt is also reserved atomically in SQLite. SDK-level retries are disabled.

Reported prompt/completion usage is charged at the configured prices, including
invalid responses. Timeouts, interrupted attempts, and missing token usage retain
their estimates as **unconfirmed** rather than being recorded as free. An unexpectedly
large billed call can exceed its estimate; subsequent calls then stop. The ledger
is a local guardrail, **not a provider-enforced cap or bank balance**.

Do not delete the live ledger or change `--data-dir` to reset the allowance.
Keep demo/test state separate. Reconcile uncertain amounts against the Nebius
dashboard before further experiments; there is deliberately no automatic credit
top-up, GPU deployment, or dedicated-endpoint API in this project.

Inspect an uncertain attempt with `skylark ledger RUN_ID`. Only after checking
that specific charge in the provider dashboard, record the verified amount:

```powershell
.\.venv\Scripts\python.exe -m skylark reconcile ATTEMPT_ID `
    --confirmed-usd 0.012 --evidence 'Provider usage reference and verification date'
```

The amount above is illustrative. This creates an audit entry and retains the
original estimate. It cannot reconcile an active request or erase reported token
usage. Saved reports remain snapshots; rerun the same probe to refresh the gate
using cached successes and reconciled costs. Do not clear a charge merely because
no result arrived.

Generate the same visual report for a real probe without sending any new requests:

```powershell
.\.venv\Scripts\python.exe -m skylark render-report data/benchmark/manifest.json `
    runs/first-probe.json --output runs/first-probe.html
```

The report embeds development images and annotations. Share it only when those
images can be shared; it contains no API key and loads no external resources.

## API and exports

The server binds only to `127.0.0.1`, has no account system, and rejects unrelated
browser origins for writes. Do not expose it publicly. API documentation is at
`/docs`; the schema is at `/openapi.json`.

| Route | Purpose |
|---|---|
| `GET /api/health` | Readiness, without exposing keys |
| `GET /api/dataset` | Validated manifest and content-bound fingerprint |
| `GET /api/images/{id}` | Upright PNG used for annotation |
| `GET /api/budget` | Local reported/uncertain usage |
| `GET /api/runs` and `GET /api/runs/{id}` | Persisted experiment results |
| `GET /api/reviews` and `PUT /api/reviews/{id}` | Explicit whole-image reviews |
| `GET /api/results` | Reviewed annotation and recorded timing summaries |
| `GET /api/export` | Reviewed-only YOLO archive |

Assisted reviews must reference an existing matching inference run and model.
Changing dataset contents invalidates previous reviews. Exports omit unreviewed
images and preserve explicit empty labels. `manifest.json` records review source,
model/run identity, scene, and image hash. The CLI also supports `evaluate`,
`export`, and `timing`; run `python -m skylark --help` for arguments.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests use temporary files and fake providers; they never call Nebius. They cover
coordinates, EXIF, malformed predictions, duplicate matches, budget concurrency,
retry limits, cache reuse, cancellation, review persistence, and YOLO reconstruction.
Browser testing of the eventual four-screen workflow is pending that implementation.

## Remaining milestones

- Verify credits/access and run the real 20-image probe; inspect proposed boxes.
- If passed, build React/TypeScript/Vite + Konva with the Project, Label, Review,
  and Export/Results screens, plus the persistent product job queue.
- Evaluate on 40 held-out real photographs and run a matched timing study.
- Target 30% less median labeling time with final annotation F1 within five
  percentage points of the manual baseline; report actual results regardless.
- Then consider optional appearance augmentation, followed by browser QA,
  a public source repository, judge-access arrangements, and the demo video.

No public repository, hosting, submission, or video has been created automatically.
Those are later deliverables, not completed results.

See [the implementation handoff](docs/implementation-status.md) for verified scope
and the next dependencies.

## Sources and licensing

Code is MIT licensed. Model outputs, weights, and external datasets retain their
own applicable terms; never assume our MIT license covers them. Generated test
fixtures are original geometric assets and contain no external photographs.
See [dependency and model attribution](docs/dependency-attribution.md).

- [Nebius model discovery](https://docs.tokenfactory.nebius.com/api-reference/examples/list-of-models)
- [Nebius vision requests](https://docs.tokenfactory.nebius.com/api-reference/examples/vision-capabilities)
- [Nebius structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json)
- [YOLO detection format](https://docs.ultralytics.com/datasets/detect)
- [Hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules)
