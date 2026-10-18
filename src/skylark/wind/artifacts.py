import hashlib
import io
import json
import zipfile
import tempfile
from pathlib import Path
from .domain import canonical
from .replay import replay_record
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
    return replay_record(run, events)
