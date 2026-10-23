import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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
    worker.add_argument("--parent-pid", type=int, help=argparse.SUPPRESS)
    demo = sub.add_parser("demo")
    demo.add_argument("--fault", choices=["none", "timeout_after_commit", "timeout_before_commit", "stale_read", "incomplete_response"], default="timeout_after_commit")
    demo.add_argument("--repaired", action="store_true")
    submit = sub.add_parser("run")
    submit.add_argument("spec", type=Path)
    adapter = sub.add_parser("adapter")
    adapter.add_argument("path", type=Path)
    adapter.add_argument("--fault", default="timeout_after_commit", choices=["none", "timeout_after_commit", "timeout_before_commit", "stale_read", "incomplete_response"])
    adapter.add_argument("--compare-repair", action="store_true", help="Test a reservation runtime repair against the same trusted local adapter")
    export = sub.add_parser("export")
    export.add_argument("run_id")
    export.add_argument("destination", type=Path)
    replay = sub.add_parser("replay")
    replay.add_argument("bundle", type=Path)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("attempt_id")
    reconcile.add_argument("confirmed_usd", type=Decimal)
    reconcile.add_argument("--evidence", required=True)
    anomaly = sub.add_parser("resolve-usage-anomaly", help="Acknowledge verified pricing after an underestimated charge")
    anomaly.add_argument("attempt_id")
    anomaly.add_argument("--evidence", required=True)
    backup = sub.add_parser("backup", help="Create a private, consistent local database snapshot")
    backup.add_argument("destination", type=Path)
    restore = sub.add_parser("restore", help="Restore to a NEW directory with pending jobs suspended")
    restore.add_argument("source", type=Path)
    restore.add_argument("destination", type=Path)
    sub.add_parser("models")
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--mode", choices=["fixture","live"], default="fixture")
    benchmark.add_argument("--trials", type=int, choices=[1,2,3], default=3)
    benchmark.add_argument("--split", choices=["development","held_out"], default="development")
    benchmark.add_argument("--cases-per-fault", type=int, help="Use the first N fixed cases per fault (held-out: 1-4; development: 1)")
    benchmark.add_argument("--freshness-guard", action="store_true", help="Enable read freshness validation for the repaired configuration")
    report = sub.add_parser("report", help="Export measured counts and uncertainty, without inference")
    report.add_argument("--comparison", help="Restrict to one benchmark/comparison ID")
    report.add_argument("--output", type=Path)
    attempt = sub.add_parser("_attempt", help=argparse.SUPPRESS)
    attempt.add_argument("run_id")
    attempt.add_argument("owner")
    attempt.add_argument("--adapter-path", type=Path)
    attempt.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    if args.command == "restore":
        from .backup import restore_backup
        print(json.dumps(restore_backup(args.source, args.destination), indent=2))
        return
    if args.command == "replay":
        from .artifacts import replay_zip
        print(json.dumps(replay_zip(args.bundle), indent=2))
        return
    if args.command == "models":
        from openai import OpenAI, APIStatusError, APIConnectionError
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            parser.error("Set NEBIUS_API_KEY locally")
        client = OpenAI(api_key=key, base_url="https://api.tokenfactory.nebius.com/v1/", max_retries=0, timeout=30)
        try:
            print(json.dumps([{"id": m.id, "owned_by": m.owned_by} for m in client.models.list()], indent=2))
        except APIStatusError as exc:
            parser.error(f"Model list request returned HTTP {exc.status_code}; check the Token Factory key and project access")
        except APIConnectionError:
            parser.error("Could not connect to Token Factory; check the network connection and try again")
        except Exception:
            parser.error("Could not list models; check Token Factory service status or try again later")
        return
    db = Database(args.data)
    if args.command == "status":
        print(json.dumps({"product": "Skylark Agent Lab", "live": readiness(db), "budget": db.budget(), "database": str(db.path)}, indent=2))
    elif args.command == "serve":
        from .api import create_app
        import uvicorn
        frontend = args.frontend.resolve()
        if not (frontend / "index.html").is_file():
            parser.error("Built interface missing. Run npm run build in frontend, or provide --frontend PATH.")
        process = None
        if not args.no_worker:
            from .processes import spawn_python
            process = spawn_python(["-m", "skylark", "--data", str(db.directory), "worker", "--parent-pid", str(os.getpid())])
        try:
            uvicorn.run(create_app(db, frontend), host="127.0.0.1", port=args.port, access_log=False)
        finally:
            if process:
                from .processes import stop_process
                stop_process(process)
    elif args.command == "worker":
        from .supervisor import supervise_once, parent_alive
        while not args.parent_pid or parent_alive(args.parent_pid):
            ident = supervise_once(db, parent_pid=args.parent_pid)
            if args.once:
                break
            if not ident:
                time.sleep(.5)
    elif args.command == "demo":
        policy = Policy(stable_key=args.repaired, reconcile=args.repaired, validate_receipt=args.repaired)
        ident = enqueue(db, RunSpec(scenario=Scenario(fault=Fault(kind=args.fault)), policy=policy), uuid.uuid4().hex)
        while db.get(ident)["status"] in ("queued", "running"):
            if not work_once(db, run_id=ident):
                time.sleep(.2)
        print(json.dumps(db.get(ident), indent=2))
    elif args.command == "run":
        spec = RunSpec.model_validate_json(args.spec.read_text(encoding="utf-8"))
        if spec.mode == "local_adapter":
            parser.error("Use the adapter command for trusted local code")
        print(enqueue(db, spec, uuid.uuid4().hex))
    elif args.command == "benchmark":
        from .benchmark import schedule
        print(json.dumps(schedule(db,args.mode,args.trials,args.split,args.cases_per_fault,args.freshness_guard),indent=2))
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
        adapter_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        module_spec = importlib.util.spec_from_file_location("skylark_user_adapter", path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        agent = module.Adapter()
        model_snapshot = (agent.model_snapshot() if hasattr(agent, "model_snapshot") else
                          {"id": agent.name, "revision": "locally-reported"})
        scenario = Scenario(fault=Fault(kind=args.fault))
        from .supervisor import supervise_once
        def run_adapter(policy):
            if hashlib.sha256(path.read_bytes()).hexdigest() != adapter_hash:
                parser.error("Adapter file changed during the comparison; start again")
            environment = agent.create_environment(scenario) if hasattr(agent, "create_environment") else None
            spec = RunSpec(mode="local_adapter", agent_version=agent.name, scenario=scenario, policy=policy,
                           environment_version=environment.version if environment else "reservation/1")
            ident = db.enqueue(freeze(spec, model_snapshot, environment), uuid.uuid4().hex)
            while db.get(ident)["status"] == "queued":
                if not supervise_once(db, adapter_path=path, adapter_name=agent.name, run_id=ident):
                    time.sleep(.2)
            if hashlib.sha256(path.read_bytes()).hexdigest() != adapter_hash:
                parser.error("Adapter file changed during the comparison; evidence is not comparable")
            return db.get(ident)

        before = run_adapter(Policy())
        if not args.compare_repair:
            print(json.dumps(before, indent=2))
        else:
            if before["status"] != "completed":
                parser.error("Initial adapter run did not complete; inspect its run ID before comparing a repair")
            if before["snapshot"]["spec"]["environment_version"] != "reservation/1":
                parser.error("Automatic repair comparison currently supports the built-in reservation environment only")
            if not (before.get("result") or {}).get("fault_triggered"):
                parser.error("The fault did not trigger; choose a fault scenario before comparing repairs")
            from .service import propose
            repair = propose(db, before["id"], "runtime")
            after = run_adapter(Policy.model_validate(repair["payload"]["after"]))
            def summary(row):
                result = row.get("result") or {}
                model_events = [event for event in db.read_events(row["id"]) if event["kind"] == "model_usage"]
                return {"run_id": row["id"], "execution": row["status"],
                        "verdict": result.get("verdict"),
                        "fault_triggered": result.get("fault_triggered"),
                        "reservation_count": len((row.get("state") or {}).get("reservations", [])),
                        "evidence": result.get("evidence"),
                        "model_calls": len(model_events)}
            print(json.dumps({"agent": agent.name, "adapter_sha256": adapter_hash, "fault": args.fault,
                "repair_id": repair["id"], "repair_kind": repair["payload"]["kind"],
                "before": summary(before), "after": summary(after),
                "improved_in_this_test": (before.get("result") or {}).get("verdict") != "passed"
                    and (after.get("result") or {}).get("verdict") == "passed"
                    and (after.get("result") or {}).get("fault_triggered") is True,
                "notice": "The same trusted adapter was tested twice without editing its source. Direct calls made outside context.call are not sandboxed; use test credentials and a test service."}, indent=2))
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
        if not args.confirmed_usd.is_finite() or args.confirmed_usd < 0:
            parser.error("Confirmed charge must be finite and nonnegative")
        db.reconcile(args.attempt_id, int(args.confirmed_usd * 1_000_000), args.evidence)
        print(json.dumps(db.budget(), indent=2))
    elif args.command == "resolve-usage-anomaly":
        db.resolve_anomaly(args.attempt_id, args.evidence)
        print(json.dumps(db.budget(), indent=2))
    elif args.command == "backup":
        from .backup import create_backup
        print(json.dumps(create_backup(db, args.destination), indent=2))


if __name__ == "__main__":
    main()
