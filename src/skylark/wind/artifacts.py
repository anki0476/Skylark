import hashlib
import io
import json
import zipfile
import tempfile
from pathlib import Path
from .domain import RunSpec, Final, canonical, digest, TOOL_SCHEMAS, VERIFIER_VERSION
from .sandbox import Sandbox
from .verifier import verify
from .privacy import redact

MAX_BUNDLE = 10_000_000


def bundle(db, run_id):
    run = db.get(run_id)
    if not run or run["status"] not in ("completed", "failed", "cancelled", "interrupted", "infrastructure_failed"):
        raise ValueError("Export requires a finished attempt")
    # Default demo contains only synthetic data. Keys never enter the snapshot or events.
    portable = {k: run[k] for k in ("id", "snapshot", "status", "result", "state", "error")}
    sanitized, changed = redact({"run": portable, "events": db.read_events(run_id)})
    members = {"run.json": canonical(sanitized["run"]).encode(), "events.json": canonical(sanitized["events"]).encode(),
        "README.txt": b"Skylark incident bundle. Inspect for sensitive data before sharing. Run python -m skylark replay BUNDLE.zip. Install Skylark before running the regression test. Recorded regression is not fresh model evidence. Original decisions and final claim are retained; changed policies can change their validity.\n",
        "test_incident.py": b"from pathlib import Path\nfrom skylark.wind.artifacts import replay_directory\n\ndef test_recorded_incident():\n    result = replay_directory(Path(__file__).parent)\n    assert result['matches_recorded'], result\n"}
    manifest = {"schema_version": "skylark-bundle/1", "redacted": changed(), "contains": "Best-effort secret/email redaction; inspect before sharing. Redacted bundles cannot establish exact replay.",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in members.items()}}
    members["manifest.json"] = canonical(manifest).encode()
    if sum(map(len, members.values())) > MAX_BUNDLE:
        raise ValueError("Bundle exceeds 10 MB; export stopped rather than dropping evidence")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            # Stable ZIP metadata makes identical evidence content-addressable.
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    raw = output.getvalue()
    directory = db.directory / "artifacts"
    directory.mkdir(exist_ok=True)
    checksum = hashlib.sha256(raw).hexdigest()
    destination = directory / (run_id + "-" + checksum + ".zip")
    def existing_matches():
        if not destination.exists():
            return False
        if hashlib.sha256(destination.read_bytes()).hexdigest() != checksum:
            raise ValueError("Stored artifact failed its content hash; inspect the local data directory")
        return True
    if existing_matches():
        return raw
    # Immutable names avoid replacing a ZIP another download has open on Windows.
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(raw)
    try:
        try:
            temporary.rename(destination)
        except (FileExistsError, PermissionError):
            if not existing_matches():
                raise
    finally:
        temporary.unlink(missing_ok=True)
    return raw


def validate_members(members):
    if sum(map(len, members.values())) > MAX_BUNDLE:
        raise ValueError("Bundle too large")
    manifest = json.loads(members["manifest.json"])
    if manifest.get("schema_version") != "skylark-bundle/1" or manifest.get("redacted"):
        raise ValueError("Unsupported or redacted bundle cannot be replayed exactly")
    if set(manifest["files"]) != {"run.json", "events.json", "README.txt", "test_incident.py"}:
        raise ValueError("Unexpected bundle members")
    for name, checksum in manifest["files"].items():
        if hashlib.sha256(members[name]).hexdigest() != checksum:
            raise ValueError("Bundle integrity check failed")
    return json.loads(members["run.json"]), json.loads(members["events.json"])


def replay_directory(path):
    names = ("manifest.json", "run.json", "events.json", "README.txt", "test_incident.py")
    if any((path / name).is_symlink() for name in names) or sum((path / name).stat().st_size for name in names) > MAX_BUNDLE:
        raise ValueError("Unsafe or oversized bundle directory")
    return replay_members({name: (path / name).read_bytes() for name in names})


def replay_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = {"manifest.json", "run.json", "events.json", "README.txt", "test_incident.py"}
        info = archive.infolist()
        if len(info) != 5 or {i.filename for i in info} != names or sum(i.file_size for i in info) > MAX_BUNDLE:
            raise ValueError("Unsafe or oversized archive")
        return replay_members({name: archive.read(name) for name in names})


def replay_members(members):
    run, events = validate_members(members)
    snapshot = run["snapshot"]
    if snapshot["tool_schema_hash"] != digest(TOOL_SCHEMAS) or snapshot["verifier_version"] != VERIFIER_VERSION:
        raise ValueError("Tool or verifier version changed")
    if run["status"] != "completed":
        raise ValueError("Incomplete evidence cannot be replayed as a complete regression")
    spec = RunSpec.model_validate(snapshot["spec"])
    if spec.environment_version != "reservation/1":
        raise ValueError("Custom environment replay requires its trusted adapter; automatic code import is disabled")
    sim = Sandbox(spec.scenario)
    if digest(sim.state) != snapshot["initial_state_hash"] or snapshot["fault_schedule"] != spec.scenario.fault.model_dump():
        raise ValueError("Initial state or fault schedule differs from the frozen snapshot")
    if not events or events[0]["kind"] != "started" or events[-1]["kind"] != "verification":
        raise ValueError("Incomplete trace: start and terminal verification are required")
    if events[-1]["payload"] != run["result"]:
        raise ValueError("Recorded verification differs from the run result")
    claims = [e["payload"] for e in events if e["kind"] == "final_claim"]
    if len(claims) != 1 or claims[0] != run["result"].get("final"):
        raise ValueError("Missing or inconsistent structured final claim")
    sequence = 0
    triggered = False
    identities, requested, observed = set(), set(), set()
    for event in events:
        if event["sequence"] != sequence + 1 or event["id"] in identities or event["run_id"] != run["id"]:
            raise ValueError("Incomplete event sequence")
        identities.add(event["id"])
        sequence += 1
        if event["kind"] == "tool_requested":
            invocation = event["payload"]["invocation_id"]
            if invocation in requested:
                raise ValueError("Duplicated tool invocation")
            requested.add(invocation)
        if event["kind"] == "tool_observed":
            payload = event["payload"]
            invocation = payload["invocation_id"]
            if invocation not in requested or invocation in observed:
                raise ValueError("Tool observation has no unique request")
            observed.add(invocation)
            if payload.get("result", {}).get("error") == "invalid_tool_or_arguments":
                continue
            if payload.get("fault") == "timeout_before_commit":
                actual = {"error": "not_executed"}
            else:
                actual = sim.invoke(payload["name"], payload["arguments"])
            if actual != payload["authoritative_result"]:
                raise ValueError("Recorded business effect differs from replay")
            triggered = triggered or bool(payload.get("fault"))
    if requested != observed:
        raise ValueError("Incomplete tool outcomes; exact replay is unavailable")
    final = Final.model_validate(run["result"]["final"]) if run["result"].get("final") else None
    result = verify(spec.scenario, sim.state, final, triggered)
    result["matches_recorded"] = all(result[key] == run["result"].get(key) for key in ("verdict", "assertions", "verifier_version")) and sim.state == run["state"]
    result["evidence"] = "recorded_regression"
    return result
