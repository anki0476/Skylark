"""A release must verify before anyone installs it."""

import hashlib
import json
import zipfile

import pytest

from scripts.verify_release import verify_archive


def make_archive(path, *, tamper=False, unsafe_name=None):
    files = {
        "README.md": b"Skylark",
        "LICENSE": b"MIT",
        "requirements.lock.txt": b"",
        "frontend/dist/index.html": b"<html></html>",
    }
    manifest = {"files": {name: hashlib.sha256(data).hexdigest()
                          for name, data in files.items()}}
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr("skylark/" + name, b"changed" if tamper and name == "README.md" else data)
        archive.writestr("skylark/RELEASE.json", json.dumps(manifest))
        if unsafe_name:
            archive.writestr(unsafe_name, b"outside")


def test_release_archive_verifies_manifest(tmp_path):
    path = tmp_path / "release.zip"
    make_archive(path)
    assert verify_archive(path)["verified"] is True


def test_release_archive_rejects_tampering(tmp_path):
    path = tmp_path / "release.zip"
    make_archive(path, tamper=True)
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_archive(path)


@pytest.mark.parametrize("unsafe_name", ["skylark/../outside.txt", "skylark/docs/.env"])
def test_release_archive_rejects_unsafe_members(tmp_path, unsafe_name):
    path = tmp_path / "release.zip"
    make_archive(path, unsafe_name=unsafe_name)
    with pytest.raises(ValueError, match="Unsafe release member"):
        verify_archive(path)
