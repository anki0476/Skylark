import asyncio
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import Response, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from .db import Database, Conflict, BudgetExceeded
from .domain import RunSpec, Strict, scenario_catalog
from .provider import readiness, ProviderFailure
from .service import enqueue, propose, compare, results
from .artifacts import bundle


class RepairRequest(Strict):
    kind: str = Field(default="runtime", pattern="^(runtime|prompt)$")


class CompareRequest(Strict):
    repair_id: str = Field(min_length=1, max_length=64)
    trials: int = Field(default=1, ge=1, le=3)


def create_app(db: Database, frontend: Path | None = None):
    app = FastAPI(title="Skylark Agent Lab", version="0.2.0")

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.url.hostname not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return Response("Localhost only", status_code=403)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("sec-fetch-site") == "cross-site" or (origin and urlsplit(origin).netloc != request.url.netloc):
                return Response("Cross-origin writes refused", status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return Response("Invalid content length", status_code=400)
            if length < 0 or length > 65536:
                return Response("Request too large", status_code=413)
            size = 0
            parts = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 65536:
                    return Response("Request too large", status_code=413)
                parts.append(chunk)
            request._body = b"".join(parts)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(_, exc):
        return Response(json.dumps({"detail": str(exc)}), status_code=409 if isinstance(exc, Conflict) else 422, media_type="application/json")

    @app.exception_handler(BudgetExceeded)
    @app.exception_handler(ProviderFailure)
    async def provider_failure(_, exc):
        return Response(json.dumps({"detail": str(exc)}), status_code=503, media_type="application/json")

    def require(run_id):
        row = db.get(run_id)
        if not row:
            raise HTTPException(404, "Run not found")
        return row

    @app.get("/api/v1/status")
    def status():
        return {"product": "Skylark", "version": "0.2.0", "live": readiness(db), "budget": db.budget(), "scenarios": scenario_catalog(), "scope": "Local controlled beta. No production-scale claim."}

    @app.get("/api/v1/runs")
    def list_runs():
        return db.list_runs()

    @app.post("/api/v1/runs", status_code=202)
    def submit(spec: RunSpec, idempotency_key: str = Header(..., min_length=8, max_length=128)):
        if spec.mode == "local_adapter":
            raise ValueError("Custom adapters are launched explicitly from the local CLI")
        return {"id": enqueue(db, spec, idempotency_key)}

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str):
        return require(run_id)

    @app.get("/api/v1/runs/{run_id}/events")
    async def get_events(run_id: str, request: Request, after: int = 0, stream: bool = False):
        require(run_id)
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
        if not stream:
            return db.read_events(run_id, cursor)
        async def iterate():
            nonlocal cursor
            while not await request.is_disconnected():
                for event in db.read_events(run_id, cursor):
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if db.get(run_id)["status"] not in ("queued", "running"):
                    # Completion can commit between the event read and status read.
                    # Drain the terminal events before closing the stream.
                    for event in db.read_events(run_id, cursor):
                        cursor = event["sequence"]
                        yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                    yield "event: done\ndata: {}\n\n"
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(iterate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/v1/runs/{run_id}/cancel")
    def cancel(run_id: str):
        require(run_id)
        db.cancel(run_id)
        return db.get(run_id)

    @app.post("/api/v1/runs/{run_id}/repairs")
    def repair(run_id: str, body: RepairRequest):
        require(run_id)
        return propose(db, run_id, body.kind)

    @app.get("/api/v1/repairs/{repair_id}")
    def get_repair(repair_id: str):
        result = db.get_repair(repair_id)
        if not result:
            raise HTTPException(404, "Repair not found")
        return result

    @app.post("/api/v1/repairs/{repair_id}/approve")
    def approve(repair_id: str):
        get_repair(repair_id)
        return db.approve(repair_id)

    @app.post("/api/v1/comparisons", status_code=202)
    def comparisons(body: CompareRequest):
        return compare(db, body.repair_id, body.trials)

    @app.get("/api/v1/comparisons/{comparison_id}")
    def comparison(comparison_id: str):
        result = db.get_comparison(comparison_id)
        if not result:
            raise HTTPException(404, "Comparison not found")
        return result

    @app.get("/api/v1/results")
    def report():
        return results(db)

    @app.get("/api/v1/results/export")
    def report_export(comparison_id: str | None = None):
        from .reporting import report
        from .privacy import redact
        data, changed = redact(report(db, comparison_id))
        data["redacted"] = changed()
        return Response(json.dumps(data, indent=2), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="skylark-results.json"'})

    @app.get("/api/v1/runs/{run_id}/bundle")
    def export(run_id: str):
        require(run_id)
        return Response(bundle(db, run_id), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="skylark-{run_id[:8]}.zip"'})

    if frontend and (frontend / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
        @app.get("/")
        def index():
            return FileResponse(frontend / "index.html")
    return app
