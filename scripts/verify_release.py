"""Check a Skylark test-build archive against its embedded file manifest."""

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath


REQUIRED = {"README.md", "LICENSE", "requirements.lock.txt", "frontend/dist/index.html"}
BLOCKED_PARTS = {".git", ".venv", ".cache", "node_modules", "data", "runs"}
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def verify_archive(path: Path) -> dict:
    names = set()
    actual = {}
    total_bytes = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            relative = name.removeprefix("skylark/")
            parts = PurePosixPath(relative).parts
            if (not name.startswith("skylark/") or not relative or "\\" in name
                    or PurePosixPath(relative).as_posix() != relative
                    or ":" in relative or "\x00" in relative
                    or any(part in (".", "..") for part in parts)
                    or any(part in BLOCKED_PARTS for part in parts)
                    or any(part.startswith(".env") and part != ".env.example" for part in parts)
                    or info.is_dir() or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK):
                raise ValueError(f"Unsafe release member: {name}")
            if name in names:
                raise ValueError(f"Duplicate release member: {name}")
            names.add(name)
            total_bytes += info.file_size
            if total_bytes > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Release exceeds the uncompressed size limit")
            actual[relative] = archive.read(info)

    try:
        manifest = json.loads(actual.pop("RELEASE.json"))
    except (KeyError, ValueError) as exc:
        raise ValueError("Missing or invalid RELEASE.json") from exc
    expected = manifest.get("files")
    if not isinstance(expected, dict) or set(expected) != set(actual):
        raise ValueError("Release manifest does not match archive members")
    if not REQUIRED.issubset(actual):
        raise ValueError("Release is missing required install files")
    for name, content in actual.items():
        if hashlib.sha256(content).hexdigest() != expected[name]:
            raise ValueError(f"Release checksum mismatch: {name}")
    return {"archive": str(path), "files": len(actual),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "verified": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_archive(args.archive)))


if __name__ == "__main__":
    main()
