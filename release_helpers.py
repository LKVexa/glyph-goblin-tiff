# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile
MAX_FILES=4096
MAX_FILE_BYTES=256*1024*1024
MAX_PACKAGE_BYTES=768*1024*1024
ARCHIVE_TIME=(2026,1,1,0,0,0)
class PackageError(ValueError): pass

def sha256(data):
    return hashlib.sha256(data).hexdigest()


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_files(folder, *, limit=MAX_PACKAGE_BYTES):
    """Enumerate bounded ordinary files without following links or junctions."""
    folder = folder.resolve()
    result, total = [], 0
    for current, directories, filenames in os.walk(folder, followlinks=False):
        current = Path(current)
        for name in directories + filenames:
            path = current / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise PackageError("Package trees must not contain links or junctions")
            if not path.resolve().is_relative_to(folder):
                raise PackageError("Package path leaves its staging directory")
        for name in filenames:
            path = current / name
            size = path.stat().st_size
            total += size
            if size > MAX_FILE_BYTES or total > limit or len(result) >= MAX_FILES:
                raise PackageError("Package file/count/byte limit exceeded")
            result.append(path)
    return sorted(result, key=lambda path: path.relative_to(folder).as_posix())


def make_zip(folder, output):
    """Exclusive output, fixed entry timestamps and sorted paths; no stale files."""
    files = safe_files(folder)
    if output.exists():
        raise PackageError("Existing release ZIP is preserved; choose a new output")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            entry = zipfile.ZipInfo(path.relative_to(folder).as_posix(), ARCHIVE_TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            with path.open("rb") as source, archive.open(entry, "w") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
    return {"name": output.name, "bytes": output.stat().st_size,
            "sha256": hash_file(output)}

