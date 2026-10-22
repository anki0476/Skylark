# Independent clean-install review

This is a handoff for someone who has not used Skylark. It tests whether the packaged local app is understandable and reproducible. It does **not** ask the reviewer to use a Nebius account or spend API credits. The archive is a local candidate until the project owner shares it.

## Install from the archive

Use a new empty directory, extract `skylark-local-beta.zip`, and open PowerShell in the extracted `skylark` folder. Python 3.12+ is required. The archive already contains the built interface, so Node is not needed for this check.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
.\scripts\start.ps1 -Port 8018
```

If `py -3.12` says Python 3.12 is not registered, use the full path to an installed Python 3.12+ interpreter for the first command: `& 'C:\path\to\python.exe' -m venv .venv`. The new `.venv` must be created inside the extracted folder; do not copy the original project's virtual environment. The project owner's current laptop has a separate bundled Python 3.12 interpreter available even though the Windows `py` launcher lists only Python 3.10.

Open `http://127.0.0.1:8018`. If port 8018 is occupied, choose another local port. Leave the server running while using the browser. No API key or live mode is needed.

## Tasks to try without guidance

1. Run the scripted **The missing confirmation** scenario. In Incident, identify what the agent saw, what actually happened, and which checks failed. The original fixture should show two reservations after a post-commit timeout; it is labeled scripted evidence.
2. Propose the runtime repair and run one comparison. Find the original and repaired incident evidence and explain the difference. The scripted repaired case should preserve one reservation.
3. Open Results, find the new fixture attempts, and download results JSON. Confirm that a failed attempt remains visible.
4. In a second PowerShell window in the same extracted folder, replay one saved completed live evidence bundle:

```powershell
.\.venv\Scripts\python.exe -m skylark replay docs/evidence/bundles/fb5098b93b7e4c128e0c2a8aba62f6dc.zip
```

The replay should report `matches_recorded: true`. It verifies the preserved trace and verdict; it does not make a fresh model call. The [evidence guide](evidence/README.md) identifies the paired stale-read bundle and the inconclusive attempt.

## Record the review

Record the OS, Python version, whether installation and all four tasks succeeded, the first point of confusion, and any error text. Note whether the reviewer could distinguish saved live evidence from scripted fixtures and whether the difference between agent-visible responses and authoritative state was clear. Do not share a local database, API key, or unreviewed export. The project owner can use this feedback to fix blockers before recording the public demo.
