"""Own the worker subprocess so non-cooperative adapters cannot ignore deadlines.

This is lifecycle supervision, NOT isolation for untrusted code.
"""
import os
import subprocess
import time
import uuid
from .db import LeaseLost
from .processes import spawn_python, stop_process


def parent_alive(pid):
    if os.name != "nt":
        return os.getppid() == pid
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only; read-only liveness.
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT: still running.
    finally:
        kernel.CloseHandle(handle)


def supervise_once(db, adapter_path=None, adapter_name=None, run_id=None, parent_pid=None):
    if parent_pid and not parent_alive(parent_pid):
        return None
    owner = uuid.uuid4().hex
    ident = db.claim(owner, adapter_name=adapter_name, run_id=run_id)
    if not ident:
        return None
    row = db.get(ident)
    command = ["-m", "skylark", "--data", str(db.directory), "_attempt", ident, owner, "--parent-pid", str(os.getpid())]
    if adapter_path:
        command.extend(["--adapter-path", str(adapter_path)])
    try:
        process = spawn_python(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        db.finish(ident, owner, "infrastructure_failed", {"verdict": "inconclusive", "assertions": []},
                  "Could not launch the attempt process; no automatic retry.")
        return ident
    started = time.monotonic()
    deadline = row["snapshot"]["spec"]["limits"]["deadline_seconds"]
    status, reason = None, None
    cancel_seen = None
    try:
        while process.poll() is None:
            if parent_pid and not parent_alive(parent_pid):
                status, reason = "interrupted", "Server exited; the owned attempt was stopped without replaying uncertain work."
                process.terminate()
                break
            if not db.heartbeat(owner):
                process.terminate()
                break
            current = db.get(ident)
            if current["status"] != "running":
                break
            if current["cancel_requested"]:
                cancel_seen = cancel_seen or time.monotonic()
                # Let cooperative calls journal their result; never wait indefinitely.
                if time.monotonic() - cancel_seen >= 2:
                    status, reason = "cancelled", "Cancellation grace expired. Recorded effects are preserved; calls without an outcome and their billing remain uncertain."
                    process.terminate()
                    break
            if time.monotonic() - started > deadline:
                status, reason = "interrupted", "Supervisor deadline reached; process terminated without replaying uncertain work."
                process.terminate()
                break
            time.sleep(.5)
    finally:
        stop_process(process)
        current = db.get(ident)
        if current["status"] == "running":
            try:
                db.finish(ident, owner, status or "interrupted", {"verdict":"inconclusive", "assertions":[], "evidence":"incomplete_execution"},
                          reason or "Attempt process exited before a complete verdict; no automatic retry.")
            except LeaseLost:
                pass
    return ident
