"""Local SQLite snapshots. Restore suspends pending work instead of executing it."""
import hashlib
import json
import shutil
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import update
from .db import Database, runs, workers
from .domain import canonical

DATABASE_NAME = "agent-lab.sqlite3"
MAX_DATABASE_BYTES = 1_000_000_000


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)


def integrity(connection):
    deadline = time.monotonic() + 30
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Backup database failed its integrity check")
    finally:
        connection.set_progress_handler(None, 0)


def create_backup(db, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    target = destination / DATABASE_NAME
    deadline = time.monotonic() + 30
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("Snapshot exceeded 30 seconds; no complete backup manifest was written")
    with closing(readonly(db.path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy, pages=256, progress=progress, sleep=.01)
        copy.execute("PRAGMA journal_mode=DELETE")
        integrity(copy)
        revision = copy.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        count = copy.execute("SELECT count(*) FROM runs").fetchone()[0]
    if target.stat().st_size > MAX_DATABASE_BYTES:
        raise ValueError("Backup exceeds the local beta size limit; no complete manifest was written")
    manifest = {"schema_version": "skylark-backup/1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "database": {"name": DATABASE_NAME, "sha256": checksum(target), "bytes": target.stat().st_size},
        "migration": revision, "run_count": count,
        "notice": "Private, unredacted local snapshot. Contains traces and usage records, not environment API keys. Generated ZIPs can be exported again. Checksums do not authenticate another person's backup."}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"path": str(destination), **manifest}


def restore_backup(source, destination):
    source, destination = Path(source), Path(destination).resolve()
    if destination.exists():
        raise ValueError("Restore requires a new directory; existing data is never overwritten")
    manifest_path, database_path = source / "manifest.json", source / DATABASE_NAME
    if source.is_symlink() or manifest_path.is_symlink() or database_path.is_symlink():
        raise ValueError("Symlinked backups are not accepted")
    if manifest_path.stat().st_size > 65536 or database_path.stat().st_size > MAX_DATABASE_BYTES:
        raise ValueError("Oversized backup")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    info = manifest.get("database", {})
    if manifest.get("schema_version") != "skylark-backup/1" or info.get("name") != DATABASE_NAME:
        raise ValueError("Unsupported backup format")
    if database_path.stat().st_size != info.get("bytes") or checksum(database_path) != info.get("sha256"):
        raise ValueError("Backup checksum or size does not match")
    with closing(readonly(database_path)) as connection:
        integrity(connection)
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        if revision != manifest.get("migration"):
            raise ValueError("Backup migration record does not match its manifest")
    destination.mkdir(parents=True, exist_ok=False)
    marker = destination / "RESTORE_INCOMPLETE"
    marker.write_text("Pending work must be suspended before this copy can execute. Retry restore into a new directory.\n", encoding="utf-8")
    shutil.copyfile(database_path, destination / DATABASE_NAME)
    restored = Database(destination, _restoring=True)
    try:
        with restored.transaction() as connection:
            result = connection.execute(update(runs).where(runs.c.status.in_(("queued", "running"))).values(
                status="interrupted", owner=None, cancel_requested=1, updated=time.time(),
                result=canonical({"verdict": "inconclusive", "assertions": [], "evidence": "restored_incomplete_execution"}),
                error="Restored snapshot: pending work was suspended. Inspect effects and usage; create a fresh attempt explicitly."))
            connection.execute(update(workers).values(owner=None, expires=0))
        marker.unlink()
        return {"path": str(destination), "suspended_runs": result.rowcount, "budget": restored.budget(),
                "notice": "Stop the original installation before using this restored copy. Separate data directories do not share spending limits."}
    finally:
        restored.engine.dispose()
