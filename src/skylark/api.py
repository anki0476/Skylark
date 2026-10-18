"""Local feasibility/data API. Full four-screen UI and paid job submission remain gated."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from .datasets import load_dataset
from .experiment import fingerprint
from .exporting import export_reviewed
from .metrics import evaluate, timing_report
from .schemas import Review
from .store import Store


def create_app(manifest: Path, store: Store) -> FastAPI:
    dataset, images = load_dataset(manifest)
    version = fingerprint(dataset, images)
    samples = {s.id: s for s in dataset.samples}
    app = FastAPI(title="Skylark feasibility API", version="0.1.0", description=(
        "Local data and review API. No API route sends images or starts paid inference. "
        "Use the explicit CLI probe after confirming credits and consent. Full UI remains gated."))

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # Reject hostile browser origins and DNS-rebinding hostnames. No wildcard CORS.
        if request.url.hostname not in {"localhost", "127.0.0.1", "testserver", "::1"}:
            return Response("Localhost only", status_code=403)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            from urllib.parse import urlsplit
            if urlsplit(origin).netloc != request.url.netloc:
                return Response("Cross-origin writes are not allowed", status_code=403)
        return await call_next(request)

    def assert_current_dataset():
        try:
            current, current_images = load_dataset(manifest)
        except (ValueError, OSError):
            raise HTTPException(409, "Dataset files are missing or invalid. Restore them and restart the server.") from None
        if fingerprint(current, current_images) != version:
            raise HTTPException(409, "Dataset changed on disk. Restart the server before continuing.")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "milestone": "feasibility_pipeline", "full_ui_ready": False,
                "nebius_key_configured": bool(os.getenv("NEBIUS_API_KEY") or os.getenv("NEBIUS_TOKEN_FACTORY_KEY")),
                "live_inference_available_via_http": False, "dataset_kind": dataset.kind}

    @app.get("/api/dataset")
    def get_dataset():
        return {"fingerprint": version, **dataset.model_dump()}

    @app.get("/api/images/{sample_id}")
    def image(sample_id: str):
        if sample_id not in images:
            raise HTTPException(404, "Unknown sample")
        return Response(images[sample_id].png, media_type="image/png")

    @app.get("/api/budget")
    def budget():
        return {**store.budget(), "notice": "Local estimates, not the provider balance"}

    @app.get("/api/runs")
    def runs():
        return store.list_runs()

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        result = store.get_run(run_id)
        if result is None:
            raise HTTPException(404, "Unknown run")
        return result

    @app.get("/api/reviews")
    def reviews():
        return store.reviews(version)

    @app.put("/api/reviews/{sample_id}")
    def save_review(sample_id: str, review: Review):
        assert_current_dataset()
        if sample_id not in samples or review.sample_id != sample_id:
            raise HTTPException(404, "Unknown or mismatched sample")
        sample = samples[sample_id]
        try:
            for box in review.objects:
                box.validate_frame(sample.width, sample.height, dataset.classes)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if review.source == "assisted":
            run = store.get_run(review.prediction_run_id)
            if not run or run["payload"]["dataset_fingerprint"] != version:
                raise HTTPException(422, "Assisted review requires a prediction run for this dataset")
            if not any(m["model"] == review.inference_model and sample_id in m["predictions"]
                       for m in run["payload"]["models"]):
                raise HTTPException(422, "Prediction run does not contain this model/sample")
        store.save_review(version, sample_id, review.model_dump())
        return review

    @app.get("/api/results")
    def results():
        reviewed = [Review.model_validate(r) for r in store.reviews(version)]
        return {"dataset_kind": dataset.kind, "reviewed_image_count": len(reviewed),
                "timing": timing_report(reviewed),
                "evaluation": {split: evaluate(dataset, {
                    r.sample_id: r.objects for r in reviewed if samples[r.sample_id].split == split
                }, split) for split in ("development", "test")},
                "notice": "Missing reviews count as missing predictions; this is not proof of the time-saving target."}

    @app.get("/api/export")
    def export():
        assert_current_dataset()
        try:
            archive = export_reviewed(manifest, [Review.model_validate(r) for r in store.reviews(version)])
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return Response(archive, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="skylark-reviewed.zip"'})

    return app

