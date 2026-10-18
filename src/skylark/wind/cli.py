import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from decimal import Decimal
from .db import Database
from .domain import RunSpec, Scenario, Fault, Policy, freeze
from .service import enqueue
from .runner import work_once
from .provider import readiness


def main():
    parser = argparse.ArgumentParser(description="Skylark — reproduce agent tool failures")
    parser.add_argument("--data", default=os.environ.get("SKYLARK_DATA_DIR", "data/agent-lab"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--no-worker", action="store_true")
    serve.add_argument("--frontend", type=Path, default=Path("frontend/dist"), help="Directory containing the built interface")
    worker = sub.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    demo = sub.add_parser("demo")
    demo.add_argument("--fault", choices=["none", "timeout_after_commit", "timeout_before_commit", "stale_read", "incomplete_response"], default="timeout_after_commit")
    demo.add_argument("--repaired", action="store_true")
    submit = sub.add_parser("run")
    submit.add_argument("spec", type=Path)
    adapter = sub.add_parser("adapter")
    adapter.add_argument("path", type=Path)
    adapter.add_argument("--fault", default="timeout_after_commit", choices=["none", "timeout_after_commit", "timeout_before_commit", "stale_read", "incomplete_response"])
    export = sub.add_parser("export")
    export.add_argument("run_id")
    export.add_argument("destination", type=Path)
    replay = sub.add_parser("replay")
    replay.add_argument("bundle", type=Path)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("attempt_id")
    reconcile.add_argument("confirmed_usd", type=Decimal)
    reconcile.add_argument("--evidence", required=True)
    sub.add_parser("models")
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--mode", choices=["fixture","live"], default="fixture")
    benchmark.add_argument("--trials", type=int, choices=[1,2,3], default=3)
    benchmark.add_argument("--split", choices=["development","held_out"], default="development")
    report = sub.add_parser("report", help="Export measured counts and uncertainty, without inference")
    report.add_argument("--comparison", help="Restrict to one benchmark/comparison ID")
    report.add_argument("--output", type=Path)
    attempt = sub.add_parser("_attempt", help=argparse.SUPPRESS)
    attempt.add_argument("run_id")
    attempt.add_argument("owner")
    attempt.add_argument("--adapter-path", type=Path)
    attempt.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    if args.command == "replay":
        from .artifacts import replay_zip
        print(json.dumps(replay_zip(args.bundle), indent=2))
        return
    if args.command == "models":
        from openai import OpenAI
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            parser.error("Set NEBIUS_API_KEY locally")
        client = OpenAI(api_key=key, base_url="https://api.tokenfactory.nebius.com/v1/", max_retries=0, timeout=30)
        try:
            print(json.dumps([{"id": m.id, "owned_by": m.owned_by} for m in client.models.list()], indent=2))
        except Exception:
            parser.error("Could not list models; check local credentials and access")
        return
    db = Database(args.data)
    if args.command == "status":
        print(json.dumps({"product": "Skylark Agent Lab", "live": readiness(), "budget": db.budget(), "database": str(db.path)}, indent=2))
    elif args.command == "serve":
        from .api import create_app
        import uvicorn
        frontend = args.frontend.resolve()
        if not (frontend / "index.html").is_file():
            parser.error("Built interface missing. Run npm run build in frontend, or provide --frontend PATH.")
        process = None
        if not args.no_worker:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen([sys.executable, "-m", "skylark", "--data", str(db.directory), "worker"], creationflags=flags)
        try:
            uvicorn.run(create_app(db, frontend), host="127.0.0.1", port=args.port, access_log=False)
        finally:
            if process:
                process.terminate()
                process.wait(timeout=10)
    elif args.command == "worker":
        from .supervisor import supervise_once
        while True:
            ident = supervise_once(db)
            if args.once:
                break
            if not ident:
                time.sleep(.5)
    elif args.command == "demo":
        policy = Policy(stable_key=args.repaired, reconcile=args.repaired, validate_receipt=args.repaired)
        ident = enqueue(db, RunSpec(scenario=Scenario(fault=Fault(kind=args.fault)), policy=policy), uuid.uuid4().hex)
        while db.get(ident)["status"] == "queued":
            if not work_once(db):
                time.sleep(.2)
        print(json.dumps(db.get(ident), indent=2))
    elif args.command == "run":
        spec = RunSpec.model_validate_json(args.spec.read_text(encoding="utf-8"))
        if spec.mode == "local_adapter":
            parser.error("Use the adapter command for trusted local code")
        print(enqueue(db, spec, uuid.uuid4().hex))
    elif args.command == "benchmark":
        from .benchmark import schedule
        print(json.dumps(schedule(db,args.mode,args.trials,args.split),indent=2))
    elif args.command == "report":
        from .reporting import report
        text = json.dumps(report(db, args.comparison), indent=2)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
            print(str(args.output.resolve()))
        else:
            print(text)
    elif args.command == "adapter":
        path = args.path.resolve(strict=True)
        module_spec = importlib.util.spec_from_file_location("skylark_user_adapter", path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        agent = module.Adapter()
        scenario = Scenario(fault=Fault(kind=args.fault))
        environment = agent.create_environment(scenario) if hasattr(agent, "create_environment") else None
        spec = RunSpec(mode="local_adapter", agent_version=agent.name, scenario=scenario, environment_version=environment.version if environment else "reservation/1")
        ident = db.enqueue(freeze(spec, {"id":agent.name,"revision":"locally-reported"}, environment), uuid.uuid4().hex)
        from .supervisor import supervise_once
        while db.get(ident)["status"] == "queued":
            if not supervise_once(db, adapter_path=path, adapter_name=agent.name, run_id=ident):
                time.sleep(.2)
        print(json.dumps(db.get(ident), indent=2))
    elif args.command == "_attempt":
        from .runner import execute_claimed
        agent = None
        if args.adapter_path:
            module_spec = importlib.util.spec_from_file_location("skylark_user_adapter", args.adapter_path.resolve(strict=True))
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            agent = module.Adapter()
        execute_claimed(db, args.run_id, args.owner, adapter=agent, parent_pid=args.parent_pid)
    elif args.command == "export":
        from .artifacts import bundle
        args.destination.write_bytes(bundle(db, args.run_id))
        print(str(args.destination.resolve()))
    elif args.command == "reconcile":
        db.reconcile(args.attempt_id, int(args.confirmed_usd * 1_000_000), args.evidence)
        print(json.dumps(db.budget(), indent=2))


if __name__ == "__main__":
    main()
