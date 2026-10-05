# SPDX-License-Identifier: GPL-3.0-only
"""Freeze a Windows consumer bootstrap while keeping the interpreter in pixels.

Build inputs are explicit local paths. No installers run and no downloads occur.
The resulting player requires neither an installed Python nor Tesseract.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid
import zipfile

from release_helpers import PackageError, hash_file, make_zip, safe_files, write_json

ROOT = Path(__file__).resolve().parent


def clean_environment():
    result = {key: value for key, value in os.environ.items() if not key.upper().startswith(("PYTHON", "TESS", "DOTNET", "VIRTUAL_ENV"))}
    result["PATH"] = str(Path(result.get("SystemRoot", "C:/Windows")) / "System32")
    return result


def verify_frozen_runtime(executable):
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(executable))
    entries = set(archive.toc)
    for name in archive.toc:
        if name.lower().endswith(".pyz"):
            entries.update(archive.open_embedded_archive(name).toc)
    forbidden = {name for name in entries if "image_interpreter" in name or "runtime-payload" in name}
    if forbidden:
        raise PackageError("Frozen host contains an interpreter fallback: " + ", ".join(sorted(forbidden)))
    if "runtime_bootstrap" not in entries or "trusted_runtime" not in entries:
        raise PackageError("Frozen host is missing the approved image-runtime loader")
    return {"interpreter_module_absent": True, "runtime_payload_absent": True,
            "approved_loader_present": True, "frozen_entries_checked": len(entries)}


def native_imports(executable):
    import pefile
    with pefile.PE(str(executable), fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        imports = sorted(item.dll.decode("ascii") for item in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []))
    if not imports or any(name.lower() != "kernel32.dll" and not name.lower().startswith("api-ms-win-crt-") for name in imports):
        raise PackageError("The OCR binary is not the reviewed minimal static Windows build")
    return imports


def archive_sources(stage):
    allowed = {".py", ".md", ".json", ".txt", ".cmd", ".yml", ".toml", ".tiff", ".gif", ".png"}
    paths = []
    for path in ROOT.iterdir():
        if path.is_file() and (path.suffix in allowed or path.name in {"LICENSE", "VERSION", ".gitignore"}):
            if path.name != "runtime-payload.json":
                paths.append(path)
    for name in ("vendor", "tests", "packaging", ".github", "examples-v0.4.0"):
        for path in (ROOT / name).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in allowed:
                paths.append(path)
    if len(paths) > 1000 or sum(path.stat().st_size for path in paths) > 16 * 1024 * 1024:
        raise PackageError("Source archive bounds exceeded")
    with zipfile.ZipFile(stage / "source.zip", "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(paths):
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise PackageError("Source paths cannot leave the project")
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def collect_notices(stage, args):
    folder = stage / "licenses"
    folder.mkdir()
    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", folder / "CPython-LICENSE.txt")
    shutil.copyfile(Path(sys.base_prefix) / "tcl/tk8.6/license.terms", folder / "Tcl-Tk-license.terms")
    for name in ("numpy", "pillow", "pyinstaller"):
        distribution = importlib.metadata.distribution(name)
        for item in distribution.files or []:
            if any(term in str(item).lower() for term in ("license", "copying", "notice")) and ".dist-info/" in str(item).replace("\\", "/"):
                path = Path(distribution.locate_file(item))
                if path.is_file():
                    destination = folder / name / Path(str(item)).name
                    destination.parent.mkdir(exist_ok=True)
                    shutil.copyfile(path, destination)
    for library in ("gcc", "libstdc++", "libgcc", "winpthreads", "crt", "headers"):
        source = args.compiler_licenses / library
        if not source.is_dir():
            raise PackageError("Missing native runtime compiler notice directory: " + library)
        for path in source.rglob("*"):
            if path.is_file():
                destination = folder / ("native-" + library) / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
    sources = stage / "third-party-source"
    sources.mkdir()
    for archive_path, wanted in ((args.tesseract_source, {"LICENSE", "AUTHORS"}),
                                 (args.leptonica_source, {"leptonica-license.txt"})):
        shutil.copyfile(archive_path, sources / archive_path.name)
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                if member.isfile() and Path(member.name).name in wanted and len(Path(member.name).parts) == 2:
                    if member.size > 1024 * 1024:
                        raise PackageError("Upstream notice exceeds size limit")
                    data = archive.extractfile(member).read()
                    (folder / (Path(member.name).parts[0] + "-" + Path(member.name).name)).write_bytes(data)
    # tessdata_fast uses the same unmodified Apache-2.0 license text as Tesseract.
    shutil.copyfile(folder / "tesseract-5.5.0-LICENSE", folder / "tessdata_fast-Apache-2.0.txt")
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", stage / "THIRD_PARTY_NOTICES.md")


def smoke(stage, work):
    import base64
    import copy
    import gzip
    from unittest.mock import patch
    from PIL import ImageDraw
    import glyph_goblin as app
    executable = stage / "GlyphGoblin.exe"
    environment = clean_environment()
    folder = work / "execution-checks"
    folder.mkdir()
    changed = folder / "changed"
    app.save_examples(changed, ("12 + 7 - 3", "(18 - 6) / 4", "5 < 3"))
    checks = []
    def run(image, receipt, ui=False):
        command = [str(executable)]
        if image is not None:
            command.append(str(image))
        command += ["--smoke-ui" if ui else "--process", "--out", str(folder / "results"), "--receipt", str(receipt)]
        result = subprocess.run(command, cwd=stage, env=environment, capture_output=True, timeout=90)
        if result.returncode or not receipt.is_file():
            raise PackageError("Packaged executable failed; no launch bypass attempted. " + result.stderr.decode("utf-8", "replace")[-1000:])
        return json.loads(receipt.read_text(encoding="utf-8"))
    for kind in ("tiff", "gif"):
        for label, path, expected in (("original", stage / ("demo." + kind), [33, 3, True]),
                                      ("changed", changed / ("input." + kind), [16, 3, False])):
            receipt = run(path, folder / (label + "-" + kind + ".json"))
            if receipt.get("values") != expected or receipt["program"].get("runtime_location") != "image pixels":
                raise PackageError("Real OCR/module output differs from its independently checked expression")
            exported = Path(receipt["output_directory"]) / ("result." + kind)
            # First frame retains the same source/runtime; any frame is runnable.
            again = run(exported, folder / (label + "-" + kind + "-resumed.json"))
            if again.get("values") != expected:
                raise PackageError("Exported image did not re-execute")
            checks.append({"case": label, "format": kind, "values": receipt["values"],
                           "agreeing_passes": receipt["consensus"]["agreeing_passes"],
                           "runtime_sha256": receipt["program"]["runtime_sha256"], "output_reexecuted": True})
    ui = run(None, folder / "ui.json", ui=True)
    if not ui.get("ui_constructed") or not ui.get("automatic_image_execution") or ui.get("values") != [33, 3, True]:
        raise PackageError("Packaged GUI did not automatically execute its bundled image")
    rejected = []
    blank = app.make_input()
    ImageDraw.Draw(blank).rectangle(app.CROP, fill="white")
    unknown = copy.deepcopy(app.default_job())
    unapproved_source = b'raise RuntimeError("unapproved source must never execute")'
    unknown["runtime"] = {"format": "python-source/gzip-base64",
                          "data": base64.b64encode(gzip.compress(unapproved_source, mtime=0)).decode("ascii"),
                          "sha256": hashlib.sha256(unapproved_source).hexdigest()}
    # Only the test fixture writer bypasses authoring validation. The separate
    # frozen process must reject this self-consistent, checksummed carrier.
    with patch.object(app, "validate_job", return_value=None):
        unapproved = app.encode_payload(app.make_input(), unknown)
    for label, image in (("blank-glyphs", blank), ("unapproved-runtime", unapproved)):
        path, receipt_path = folder / (label + ".tiff"), folder / (label + ".json")
        image.save(path, compression="tiff_deflate")
        result = subprocess.run([str(executable), str(path), "--process", "--out", str(folder / "results"),
                                 "--receipt", str(receipt_path)], cwd=stage, env=environment,
                                capture_output=True, timeout=90)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
        if result.returncode == 0 or receipt.get("accepted") is not False or "values" in receipt:
            raise PackageError("Packaged host failed to withhold computation for " + label)
        rejected.append({"case": label, "computation_withheld": True})
    return {"status": "passed", "cases": checks, "gui": "constructed_and_automatically_executed",
            "rejections": rejected,
            "environment": "No PYTHONPATH, Tesseract environment or installed-toolchain PATH required"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyinstaller-path", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tesseract-source", type=Path, required=True)
    parser.add_argument("--leptonica-source", type=Path, required=True)
    parser.add_argument("--compiler-licenses", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "releases/Glyph-Goblin-0.4.0-win-x64.zip")
    args = parser.parse_args()
    sys.path.insert(0, str(args.pyinstaller_path.resolve()))
    if args.out.exists():
        parser.error("Existing release ZIP is preserved; choose a fresh output")
    work = ROOT / "runs" / ("package-" + uuid.uuid4().hex)
    work.mkdir(parents=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(args.pyinstaller_path.resolve())
    python_root = Path(sys.base_prefix)
    for key, value in (("TCL_LIBRARY", python_root / "tcl/tcl8.6"), ("TK_LIBRARY", python_root / "tcl/tk8.6")):
        if value.is_dir():
            environment[key] = "\\\\?\\" + str(value.resolve()) if os.name == "nt" else str(value)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
               "--name", "GlyphGoblin", "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
               "--specpath", str(work), "--exclude-module", "image_interpreter", "--hidden-import", "ast",
               "--hidden-import", "math", "--hidden-import", "operator", str(ROOT / "glyph_desktop.py")]
    with (work / "freeze.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if result.returncode:
        raise PackageError("PyInstaller failed; inspect " + str(work / "freeze.log"))
    stage = work / "dist/GlyphGoblin"
    frozen = verify_frozen_runtime(stage / "GlyphGoblin.exe")
    imports = native_imports(args.tesseract)
    ocr = stage / "ocr"
    (ocr / "tessdata").mkdir(parents=True)
    shutil.copyfile(args.tesseract, ocr / "tesseract.exe")
    shutil.copyfile(args.model, ocr / "tessdata/eng.traineddata")
    for name in ("demo.tiff", "demo.gif", "Play.cmd", "LICENSE"):
        shutil.copyfile(ROOT / name, stage / name)
    shutil.copyfile(ROOT / "packaging/PLAY-README.txt", stage / "READ-ME-FIRST.txt")
    collect_notices(stage, args)
    validation = smoke(stage, work)
    archive_sources(stage)
    from trusted_runtime import APPROVED_SOURCE_SHA256
    value = {"schema": "glyph-goblin-consumer-release/1", "version": "0.4.0", "target": "Windows x64",
             "entrypoint": "Play.cmd", "installed_python_required": False, "installed_tesseract_required": False,
             "interpreter_location": "image pixels", "runtime_sha256": APPROVED_SOURCE_SHA256,
             "frozen_audit": frozen, "execution_validation": validation,
             "ocr": {"engine_sha256": hash_file(args.tesseract), "model_sha256": hash_file(args.model), "native_imports": imports},
             "upstream_sources": {path.name: hash_file(path) for path in (args.tesseract_source, args.leptonica_source)},
             "files": [{"path": path.relative_to(stage).as_posix(), "bytes": path.stat().st_size, "sha256": hash_file(path)} for path in safe_files(stage)]}
    write_json(stage / "manifest.json", value)
    archive = make_zip(stage, args.out.resolve())
    report = {"archive": archive, "version": "0.4.0", "validation": validation, "frozen_audit": frozen, "stage": str(stage)}
    write_json(args.out.with_suffix(".build.json"), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
