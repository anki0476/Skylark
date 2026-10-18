"""Run a narrow, resumable development experiment before committing to the UI."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from .datasets import load_dataset
from .imaging import inference_image, restore_boxes
from .metrics import evaluate
from .provider import NebiusProvider, Provider, ProviderError, PROMPT_VERSION, billed_cost, parse_completion
from .schemas import Box, Dataset, ExperimentConfig, ModelSettings
from .store import BudgetExceeded, Store, now

TASK = "Label every visible apple, cup, and bottle belonging to the supplied class list."


def fingerprint(dataset: Dataset, images: dict) -> str:
    payload = dataset.model_dump_json() + json.dumps({k: v.sha256 for k, v in sorted(images.items())})
    return hashlib.sha256(payload.encode()).hexdigest()


def cache_key(image_hash: str, classes: list[str], task: str, settings: ModelSettings,
              evidence_kind: str) -> str:
    parts = {"image": image_hash, "classes": classes, "task": task,
             "model": settings.model, "response_format": settings.response_format,
             "long_edge": settings.image_long_edge, "max_output_tokens": settings.max_output_tokens,
             "prompt_version": PROMPT_VERSION, "evidence_kind": evidence_kind}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def gate_for(report: dict) -> dict:
    reasons = []
    if report["evidence_kind"] != "live_nebius" or report["dataset_kind"] != "real_photographs":
        reasons.append("Requires live Nebius inference on real, manually annotated photographs")
    if report["development_images"] != 20:
        reasons.append("Requires exactly 20 development images")
    if set(report["conditions"]) != {"clean", "shadows", "clutter", "occlusion"}:
        reasons.append("Development set must cover all four conditions")
    if set(report["classes_present"]) != {"apple", "cup", "bottle"}:
        reasons.append("Development truth must contain apples, cups, and bottles")
    eligible = [m for m in report["models"] if m["model"].lower().startswith("nvidia/")
                and m["completed_images"] == 20
                and m["metrics"]["overall"]["precision"] >= .7
                and m["metrics"]["overall"]["recall"] >= .7]
    if not eligible:
        reasons.append("No NVIDIA vision candidate completed all images with precision and recall >= 0.70")
    if report["budget"]["accounted_usd"] > report["experiment_limit_usd"] + 1e-12:
        reasons.append("Recorded experiment cost exceeded the allowance")
    if report["budget"]["uncertain_or_reserved_usd"] > 0:
        reasons.append("Some billing is unconfirmed; reconcile it before claiming a pass")
    selected = sorted(eligible, key=lambda m: (-m["metrics"]["overall"]["f1"], m["comparison_cost_usd"], m["model"]))
    return {"status": "passed" if not reasons else "not_passed",
            "selected_model": selected[0]["model"] if selected and not reasons else None,
            "reasons": reasons,
            "meaning": "Development feasibility only, not held-out performance or grasping readiness."}


def run_experiment(manifest: Path, config: ExperimentConfig, store: Store, provider: Provider,
                   task: str = TASK, on_progress=None) -> dict:
    dataset, images = load_dataset(manifest)
    development = [s for s in dataset.samples if s.split == "development"]
    if not development or len(development) > 20:
        raise ValueError("A probe requires 1 to 20 development images; final gate requires 20")
    if not task.strip() or len(task) > 2000:
        raise ValueError("Task must contain 1 to 2000 characters")
    evidence = "live_nebius" if isinstance(provider, NebiusProvider) else "synthetic_fixture"
    if evidence == "live_nebius" and dataset.kind != "real_photographs":
        raise ValueError("Do not spend live inference credits on the offline fixture")
    catalog = provider.discover()
    available = {m["id"] for m in catalog}
    for settings in config.models:
        if settings.model not in available:
            raise ValueError(f"Model absent from account catalog: {settings.model}")
    # Require the whole uncached batch plus its allowed retries to fit before any call.
    estimate = 0.
    for settings in config.models:
        for sample in development:
            key = cache_key(images[sample.id].sha256, dataset.classes, task, settings, evidence)
            if not store.get_cache(key):
                estimate += 2 * settings.estimated_attempt_usd()
    if store.budget()["accounted_usd"] + estimate > config.experiment_limit_usd + 1e-12:
        raise BudgetExceeded("Projected uncached batch including one retry exceeds the shared experiment allowance")
    report = {
        "version": 1, "run_id": uuid.uuid4().hex, "started_at": now(), "state": "queued",
        "evidence_kind": evidence, "dataset_kind": dataset.kind,
        "dataset_name": dataset.name, "dataset_fingerprint": fingerprint(dataset, images),
        "development_images": len(development), "task": task, "prompt_version": PROMPT_VERSION,
        "classes": dataset.classes,
        "classes_present": sorted({b.label for s in development for b in s.objects}),
        "conditions": sorted({s.condition for s in development}),
        "experiment_limit_usd": config.experiment_limit_usd,
        "projected_new_cost_including_retries_usd": estimate,
        "models": [], "budget": store.budget(),
        "billing_notice": "Token-based estimates are not a provider-enforced spending cap. Reconcile against Nebius.",
    }
    store.save_run(report["run_id"], "queued", report)

    def checkpoint(state="running"):
        report["state"] = state
        report["budget"] = store.budget()
        attempts = store.attempts(report["run_id"])
        for candidate in report["models"]:
            candidate["accounted_usd"] = sum(a["accounted_usd"] for a in attempts
                                              if a["model"] == candidate["model"])
        report["gate"] = gate_for(report)
        store.save_run(report["run_id"], state, report)
        if on_progress:
            on_progress(report)

    stop_all = False
    interrupted = False
    try:
        for settings in config.models:
            candidate = {"model": settings.model, "settings": settings.model_dump(),
                         "completed_images": 0, "cached_images": 0, "accounted_usd": 0., "comparison_cost_usd": 0.,
                         "predictions": {}, "images": [],
                         "metrics": evaluate(dataset, {}, "development")}
            report["models"].append(candidate)
            checkpoint()
            for sample in development:
                if stop_all:
                    break
                original = images[sample.id]
                sent = inference_image(original, settings.image_long_edge)
                key = cache_key(original.sha256, dataset.classes, task, settings, evidence)
                cached = store.get_cache(key)
                result = {"sample_id": sample.id, "status": "failed", "cached": False,
                          "attempts": 0, "latency_seconds": 0., "error": None}
                boxes = None
                if cached:
                    boxes = [Box.model_validate(v) for v in cached["objects"]]
                    for box in boxes:
                        box.validate_frame(original.width, original.height, dataset.classes)
                    result.update(status="completed", cached=True)
                    candidate["cached_images"] += 1
                    candidate["comparison_cost_usd"] += store.sample_cost(
                        cached["origin_run_id"], cached["origin_sample_id"], settings.model)
                else:
                    origin_cost = 0.
                    for attempt_number in range(2):
                        try:
                            attempt_id = store.reserve(report["run_id"], sample.id, settings.model,
                                                       settings.estimated_attempt_usd(), config.experiment_limit_usd)
                        except BudgetExceeded:
                            result["error"] = "Allowance reached before sending another request"
                            stop_all = True
                            break
                        result["attempts"] = attempt_number + 1
                        start = time.monotonic()
                        completion = None
                        try:
                            completion = provider.label(sent, dataset.classes, task, settings)
                            proposed = parse_completion(completion, sent, dataset.classes)
                            boxes = restore_boxes(proposed, sent, original, dataset.classes)
                            cost = billed_cost(completion, settings)
                            store.finish_attempt(attempt_id, status="completed", latency=completion.latency_seconds,
                                                 cost=cost, input_tokens=completion.input_tokens,
                                                 output_tokens=completion.output_tokens)
                            origin_cost += cost if cost is not None else settings.estimated_attempt_usd()
                            store.put_cache(key, {"objects": [b.model_dump() for b in boxes],
                                                  "model": settings.model, "evidence_kind": evidence,
                                                  "origin_sample_id": sample.id,
                                                  "origin_run_id": report["run_id"], "origin_cost_usd": origin_cost})
                            result.update(status="completed", error=None)
                            result["latency_seconds"] += completion.latency_seconds
                            break
                        except ProviderError as exc:
                            origin_cost += settings.estimated_attempt_usd()
                            latency = time.monotonic() - start
                            store.finish_attempt(attempt_id, status="failed", latency=latency,
                                                 cost=None, error=str(exc))
                            result["latency_seconds"] += latency
                            result["error"] = str(exc)
                            if not exc.retryable:
                                stop_all = True
                                break
                        except ValueError:
                            known_cost = billed_cost(completion, settings) if completion else None
                            origin_cost += known_cost if known_cost is not None else settings.estimated_attempt_usd()
                            latency = completion.latency_seconds if completion else time.monotonic() - start
                            store.finish_attempt(attempt_id, status="invalid_output", latency=latency,
                                                 cost=billed_cost(completion, settings) if completion else None,
                                                 input_tokens=completion.input_tokens if completion else None,
                                                 output_tokens=completion.output_tokens if completion else None,
                                                 error="Invalid JSON, class, coordinates, or incomplete output")
                            result["latency_seconds"] += latency
                            result["error"] = "Invalid JSON, class, coordinates, or incomplete output"
                        except BaseException:
                            store.finish_attempt(attempt_id, status="interrupted", latency=time.monotonic() - start,
                                                 cost=None, error="Interrupted; billing unconfirmed")
                            result.update(status="interrupted", error="Interrupted; billing unconfirmed")
                            result["latency_seconds"] += time.monotonic() - start
                            candidate["images"].append(result)
                            candidate["comparison_cost_usd"] += origin_cost + settings.estimated_attempt_usd()
                            raise
                    candidate["comparison_cost_usd"] += origin_cost
                if boxes is not None:
                    candidate["predictions"][sample.id] = [b.model_dump() for b in boxes]
                    candidate["completed_images"] += 1
                candidate["images"].append(result)
                candidate["metrics"] = evaluate(dataset, {
                    sid: [Box.model_validate(b) for b in values]
                    for sid, values in candidate["predictions"].items()}, "development")
                checkpoint()
            if stop_all:
                break
    except KeyboardInterrupt:
        interrupted = True
    except Exception:
        checkpoint("failed")
        raise
    total = sum(m["completed_images"] for m in report["models"])
    expected = len(development) * len(config.models)
    state = ("cancelled" if interrupted else "completed" if total == expected
             else "partial_failure" if total else "failed")
    report["finished_at"] = now()
    checkpoint(state)
    return report


def write_report(path: Path, report: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(path)

