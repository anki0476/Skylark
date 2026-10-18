from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from .datasets import load_dataset
from .experiment import run_experiment, write_report
from .exporting import export_reviewed
from .fixture import FixtureProvider, create_fixture, fixture_config
from .metrics import evaluate, timing_report
from .provider import NebiusProvider, ProviderError
from .schemas import Box, ExperimentConfig, Review
from .store import Store


def output(value):
    print(json.dumps(value, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="skylark", description="Skylark feasibility and review pipeline")
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("SKYLARK_DATA_DIR", "data")))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Local readiness and experiment ledger; sends no requests")
    ledger = commands.add_parser("ledger", help="Inspect per-attempt usage for a saved run")
    ledger.add_argument("run_id")
    reconcile = commands.add_parser("reconcile", help="Record an uncertain charge verified in the provider dashboard")
    reconcile.add_argument("attempt_id")
    reconcile.add_argument("--confirmed-usd", type=float, required=True)
    reconcile.add_argument("--evidence", required=True, help="Usage reference and date; never include secrets")
    models = commands.add_parser("models", help="Read account model catalog; does not run inference")
    models.add_argument("--output", type=Path)
    validate = commands.add_parser("validate", help="Validate images, annotations, and scene splits")
    validate.add_argument("manifest", type=Path)
    probe = commands.add_parser("probe", help="Explicit paid development probe, maximum $2 shared allowance")
    probe.add_argument("manifest", type=Path)
    probe.add_argument("--config", type=Path, required=True)
    probe.add_argument("--output", type=Path, default=Path("runs/latest.json"))
    probe.add_argument("--confirm-send-images", action="store_true",
                       help="Consent to sending the development images to Nebius")
    probe.add_argument("--task", default="Label every visible instance of the supplied object classes.")
    demo = commands.add_parser("offline-demo", help="Generate and run a clearly marked software fixture, no API calls")
    demo.add_argument("directory", type=Path)
    score = commands.add_parser("evaluate", help="Evaluate a saved prediction map; never invokes a model")
    score.add_argument("manifest", type=Path)
    score.add_argument("predictions", type=Path)
    score.add_argument("--split", choices=["development", "test"], default="test")
    render = commands.add_parser("render-report", help="Create a self-contained visual comparison of saved proposals")
    render.add_argument("manifest", type=Path)
    render.add_argument("report", type=Path)
    render.add_argument("--output", type=Path, required=True)
    export = commands.add_parser("export", help="Export explicitly reviewed labels as a YOLO ZIP")
    export.add_argument("manifest", type=Path)
    export.add_argument("reviews", type=Path)
    export.add_argument("--output", type=Path, required=True)
    timing = commands.add_parser("timing", help="Summarize manually recorded complete labeling sessions")
    timing.add_argument("reviews", type=Path)
    serve = commands.add_parser("serve", help="Local data API and Swagger docs; full product UI is gated")
    serve.add_argument("manifest", type=Path)
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            output({"milestone": "feasibility_pipeline", "full_ui_ready": False,
                    "nebius_key_configured": bool(os.getenv("NEBIUS_API_KEY") or os.getenv("NEBIUS_TOKEN_FACTORY_KEY")),
                    "budget": Store(args.data_dir).budget(),
                    "next": "Confirm credits, discover models, supply a real annotated dataset, then run probe."})
        elif args.command == "ledger":
            store = Store(args.data_dir)
            if store.get_run(args.run_id) is None:
                raise ValueError("Unknown run ID")
            output({"run_id": args.run_id, "attempts": store.attempts(args.run_id), "budget": store.budget()})
        elif args.command == "reconcile":
            store = Store(args.data_dir)
            audit = store.reconcile(args.attempt_id, args.confirmed_usd, args.evidence)
            output({"reconciliation": audit, "budget": store.budget(),
                    "next": "Saved reports are snapshots. Rerun the same probe to refresh metrics using the cache."})
        elif args.command == "models":
            result = {"models": NebiusProvider().discover(),
                      "notice": "Catalog presence does not verify image inference, public billing, or credits. "
                                "Verbose token pricing is per token, not per million; check the console."}
            if args.output:
                write_report(args.output, result)
            output(result)
        elif args.command == "validate":
            dataset, images = load_dataset(args.manifest)
            output({"valid": True, "kind": dataset.kind, "images": len(images),
                    "development": sum(s.split == "development" for s in dataset.samples),
                    "test": sum(s.split == "test" for s in dataset.samples)})
        elif args.command == "probe":
            if not args.confirm_send_images:
                raise ValueError("Use --confirm-send-images only after consenting to send development photos to Nebius")
            config = ExperimentConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
            report = run_experiment(args.manifest, config, Store(args.data_dir), NebiusProvider(), args.task,
                                    on_progress=lambda r: write_report(args.output, r))
            output({"run_id": report["run_id"], "state": report["state"], "gate": report["gate"],
                    "budget": report["budget"], "report": str(args.output)})
            return 0 if report["gate"]["status"] == "passed" else 2
        elif args.command == "offline-demo":
            from .reporting import visual_report
            manifest = create_fixture(args.directory)
            # Separate ledger and cache so fictional test usage never contaminates real accounting.
            report = run_experiment(manifest, fixture_config(), Store(args.directory / "state"), FixtureProvider())
            path = args.directory / "report.json"
            write_report(path, report)
            (args.directory / "report.html").write_text(visual_report(manifest, report), encoding="utf-8")
            output({"manifest": str(manifest), "report": str(path), "gate": report["gate"],
                    "visual_report": str(args.directory / "report.html"),
                    "notice": "No model was called. Predictions are scripted software test fixtures."})
        elif args.command == "render-report":
            from .reporting import visual_report
            if args.output.exists():
                raise ValueError("Choose a new report filename; existing files are not overwritten")
            report = json.loads(args.report.read_text(encoding="utf-8"))
            html = visual_report(args.manifest, report)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(html, encoding="utf-8")
            output({"visual_report": str(args.output), "notice": "Saved report only; no inference was run."})
        elif args.command == "evaluate":
            dataset, _ = load_dataset(args.manifest)
            values = json.loads(args.predictions.read_text(encoding="utf-8"))
            output(evaluate(dataset, {k: [Box.model_validate(b) for b in v] for k, v in values.items()}, args.split))
        elif args.command in {"export", "timing"}:
            reviews = [Review.model_validate(v) for v in json.loads(args.reviews.read_text(encoding="utf-8"))]
            if args.command == "timing":
                output(timing_report(reviews))
            else:
                if args.output.exists():
                    raise ValueError("Choose a new export filename; existing files are not overwritten")
                archive = export_reviewed(args.manifest, reviews)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(archive)
                output({"export": str(args.output), "reviewed_images": len(reviews)})
        elif args.command == "serve":
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(args.manifest, Store(args.data_dir)), host="127.0.0.1", port=args.port)
        return 0
    except ValidationError as exc:
        # Pydantic's default text includes inputs. Keep command output limited to field errors.
        output({"error": "Validation failed", "fields": [
            {"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors(include_input=False)
        ]})
        return 1
    except (ValueError, OSError, ProviderError) as exc:
        output({"error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
