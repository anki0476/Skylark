"""Build a source/test-build archive from explicit paths; never publish it."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREES = ("src/skylark", "tests", "examples", "scripts", "docs", "frontend/src", "frontend/tests", "frontend/dist", ".github/workflows")
FILES = ("README.md", "LICENSE", ".env.example", ".gitignore", "pyproject.toml", "requirements.lock.txt",
         "frontend/package.json", "frontend/package-lock.json", "frontend/index.html", "frontend/vite.config.ts",
         "frontend/tsconfig.json", "frontend/playwright.config.ts")


def main():
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise SystemExit("Build the interface before packaging.")
    members = {}
    paths = [ROOT / name for name in FILES]
    for tree in TREES:
        paths.extend((ROOT / tree).rglob("*"))
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"Refusing symlink: {path.relative_to(ROOT)}")
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in (".pyc", ".tsbuildinfo"):
            continue
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError("Release path resolved outside the checkout")
        relative = path.relative_to(ROOT).as_posix()
        if any(part in (".env", ".git", "node_modules", "data", ".venv", ".cache") for part in Path(relative).parts):
            raise ValueError("Disallowed release member")
        members[relative] = path.read_bytes()
    members["RELEASE.json"] = json.dumps({"product": "Skylark local beta", "version": "0.2.0",
        "evidence": "Offline verification, exploratory live NVIDIA runs, and a limited 12-attempt live held-out protocol; one execution inconclusive.",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(members.items())}}, indent=2).encode()
    destination = ROOT / "dist/skylark-local-beta.zip"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            archive.writestr("skylark/" + name, data)
    print(json.dumps({"archive": str(destination), "files": len(members), "bytes": destination.stat().st_size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "published": False}))


if __name__ == "__main__":
    main()
