# Implementation handoff — October 17, 2026

This is the prerequisite feasibility milestone, not the completed four-screen app.
The approved plan requires a live model-quality and cost gate before building the
full React interface. The account, credit balance, key, real images, and human
reference annotations are still pending. No live request has been made.

## Available now

- `skylark status`, `models`, `validate`, and `probe` for the bounded development experiment.
- SQLite checkpoints, cached successes, atomic spending reservations, and an audit trail
  for manually reconciled unknown charges. One retry maximum; no SDK-level retry.
- Model comparison using precision/recall/F1 at IoU 0.5, per-condition results,
  per-image failures, token-based usage, and a live-only feasibility gate.
- A local FastAPI review API with explicit missed-object/empty-image confirmation,
  review persistence, provenance checks, and reviewed-only YOLO ZIP export.
- Portable HTML experiment reports with proposal/reference overlays.
- A separate, scripted offline example and its own ledger; it cannot pass the gate.
- Annotation protocol, configuration templates, setup script, locked dependencies,
  original-code MIT license, and dependency/model attribution notes.

## Verification completed

58 automated tests passed on Python 3.12.14, covering data, geometry, matching,
budget concurrency, caching, cancellations, reconciliation, mocked Nebius HTTP
responses, review persistence, exports, and report escaping. `pip check` found no
broken requirements. One upstream Starlette warning recommends migrating its test
client from HTTPX to HTTPX2; the current locked test environment passes.

A second, fresh Python 3.12 environment installed the lock file and package, then
successfully reproduced the offline dataset, JSON report, and visual HTML report.

The offline report returned HTTP 200 and was inspected in the in-app browser.
Overlay visibility and the narrow-screen layout were checked. This is a browser
check of the report, not an end-to-end test of the future annotation editor.

Export tests reconstruct YOLO labels into original pixel coordinates and check
review provenance. Loading an export in a full third-party detector stack remains
part of later integration verification. Partial exports may have an empty split;
their manifest records split counts, and their README explains that limitation.

## Next dependency: the real experiment

1. Confirm credited balance and expiry, disable automatic top-ups, and configure
   the API key locally without sharing it in chat.
2. Capture and manually annotate 20 development images following `dataset-protocol.md`.
   Keep 40 other images held out by physical scene arrangement.
3. Inspect the actual public account catalog, choose at most two eligible vision
   candidates, and record current prices. Do not fill the template with guesses.
4. Run the consented probe within the shared $2 experiment allowance. Inspect the
   visual report as well as aggregate scores. Reconcile unconfirmed billing.
5. Proceed only if the documented live gate passes; otherwise assess the planned
   NVIDIA specification-model fallback or revise the architecture.

## Work after the gate

- React/TypeScript/Vite and Konva: Project, Label, Review, Export & Results.
- Up to 50 image uploads, editable project classes/task, and a persistent single-worker
  product queue with progress, per-image retry, and cancellation controls.
- Box drawing/moving/resizing/relabeling/deletion, review completion, autosave, and
  end-to-end timing that includes waiting and corrections.
- Held-out evaluation, correction counts, matched manual/assisted sessions, and
  actual quality/time-saving results. No results are currently claimed.
- Full browser workflow tests, detector-loader verification, judge access,
  public repository, and a sub-three-minute demo video.

Synthetic generation, detector retraining, paid hosting, and GPU provisioning are
outside the baseline. No external deployment or public repository was created.
