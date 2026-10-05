"""Bounded Tesseract runner with unchanged JA21 raster-analysis helpers.
Copyright (c) 2026 Russell Philip Smithson. SPDX-License-Identifier: GPL-3.0-only
"""
from __future__ import annotations
import csv
import hashlib
import io
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image
from glyph_goblin import Rejected, digest, write_json
from vendor.ja21_ocr.adaptive import plan_profiles
from vendor.ja21_ocr.agreement import compare_passes
from vendor.ja21_ocr.confidence import calibrate_confidence
from vendor.ja21_ocr.geometry import validate_geometry
from vendor.ja21_ocr.models import OcrOptions, OcrPassResult, OcrWord
from vendor.ja21_ocr.preprocess import preprocess_image
from vendor.ja21_ocr.quality import analyze_page
from vendor.ja21_ocr.verification import canonical_from_words

MAX_OCR_BYTES = 1_048_576
MAX_TOKENS = 2048


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            value.update(chunk)
    return value.hexdigest()


def locate_backend(executable=None, tessdata_dir=None):
    explicit = executable or os.environ.get("TESSERACT_CMD")
    found = str(Path(explicit).expanduser()) if explicit else shutil.which("tesseract")
    if not found and os.name == "nt":
        for key in ("ProgramFiles", "ProgramFiles(x86)"):
            candidate = Path(os.environ.get(key, "")) / "Tesseract-OCR" / "tesseract.exe"
            if candidate.is_file():
                found = str(candidate); break
    if found and not Path(found).is_file():
        found = shutil.which(found)
    if not found:
        raise Rejected("Tesseract executable missing; use --tesseract or TESSERACT_CMD")
    engine = Path(found).expanduser().resolve()
    if not engine.is_file():
        raise Rejected("Tesseract executable does not exist")
    selected = tessdata_dir or os.environ.get("TESSDATA_PREFIX")
    if selected:
        base = Path(selected).expanduser().resolve()
        candidates = [base, base / "tessdata"]
    else:
        candidates = [engine.parent / "tessdata", engine.parent.parent / "share" / "tessdata",
                      Path("/usr/share/tesseract-ocr/5/tessdata"), Path("/usr/share/tesseract-ocr/4.00/tessdata"),
                      Path("/usr/share/tesseract-ocr/tessdata"), Path("/usr/share/tessdata"),
                      Path("/usr/local/share/tessdata"), Path("/opt/homebrew/share/tessdata")]
    for candidate in candidates:
        model = candidate / "eng.traineddata"
        if model.is_file() and 0 < model.stat().st_size <= 64 * 1024 * 1024:
            return engine, candidate.resolve()
    raise Rejected("English model missing or oversized; --tessdata-dir must contain eng.traineddata")


def bounded_process(command, folder, basename, env, timeout=30, watched=()):
    """Cap process lifetime and output growth without unbounded pipe buffering."""
    stdout, stderr = folder / (basename + ".stdout"), folder / (basename + ".stderr")
    outputs = [stdout, stderr, *watched]
    start = time.monotonic()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            process = subprocess.Popen(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                       env=env, cwd=folder, shell=False, creationflags=flags)
        except OSError as exc:
            raise Rejected("Trusted local Tesseract backend could not start") from exc
        try:
            while True:
                if any(path.exists() and path.stat().st_size > MAX_OCR_BYTES for path in outputs):
                    raise Rejected("OCR output exceeded the 1 MiB per-file limit")
                if process.poll() is not None:
                    break
                if time.monotonic() - start > timeout:
                    raise Rejected("OCR process exceeded its time limit")
                time.sleep(.025)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
    if process.returncode:
        raise Rejected("Tesseract returned a failure; inspect preserved pass logs")
    return stdout.read_text(encoding="utf-8", errors="replace"), stderr.read_text(encoding="utf-8", errors="replace")


def parse_tsv(text):
    if len(text.encode("utf-8")) > MAX_OCR_BYTES:
        raise Rejected("TSV output limit")
    words, invalid = [], 0
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        token = (row.get("text") or "").strip()
        if not token:
            continue
        try:
            confidence = float(row["conf"])
            if not math.isfinite(confidence) or not 0 <= confidence <= 100:
                raise ValueError("confidence")
            values = [int(row[k]) for k in ("left", "top", "width", "height", "block_num", "par_num", "line_num", "word_num")]
            if any(not 0 <= value <= 8_000_000 for value in values) or len(token) > 256:
                raise ValueError("word bounds")
            words.append(OcrWord(token, confidence, *values))
        except (KeyError, TypeError, ValueError):
            invalid += 1
        if len(words) > MAX_TOKENS:
            raise Rejected("OCR token count limit")
    return words, round(sum(word.confidence for word in words) / len(words), 2) if words else None, invalid


def recognize(image, evidence_dir, *, executable=None, tessdata_dir=None):
    source = Path(image).resolve()
    folder = Path(evidence_dir).resolve()
    # This dedicated OCR directory must be new: no evidence or source overwrite.
    if folder.exists():
        raise Rejected("OCR evidence directory already exists")
    folder.mkdir(parents=True)
    engine, models = locate_backend(executable, tessdata_dir)
    env = os.environ.copy()
    env["TESSDATA_PREFIX"] = str(models)
    options = OcrOptions(languages=["eng"], timeout_seconds=30, max_pages=1,
                         max_pixels_per_page=8_000_000, max_upscale=2,
                         output_pdf=False, region_level_selection=False, local_pii_warnings=False)
    with Image.open(source) as opened:
        if opened.width * opened.height > options.max_pixels_per_page:
            raise Rejected("OCR pixel limit")
    version, _ = bounded_process([str(engine), "--version"], folder, "version", env, timeout=10)
    if not version.lower().startswith("tesseract 5") and not version.lower().startswith("tesseract v5"):
        raise Rejected("This release requires Tesseract 5")
    quality = analyze_page(source, 300)
    profiles = plan_profiles(quality)
    def sanitize(text):
        for path, replacement in ((str(folder), "$OCR"), (str(source), "$INPUT"),
                                  (str(models), "$TESSDATA"), (str(engine), "$TESSERACT")):
            text = text.replace(path, replacement).replace(path.replace("\\", "/"), replacement)
        return text
    def run_pass(number, profile):
        prepared = folder / f"pass-{number}.png"
        preprocess_image(source, prepared, profile, options)
        sensor_input = folder / f"pass-{number}.bmp"
        with Image.open(prepared) as opened:
            width, height = opened.size
            # Lossless BMP transport permits a minimal Tesseract/Leptonica build
            # without unrelated network/archive/image-codec dependencies. JA21's
            # preprocessing and every RGB pixel are preserved.
            opened.convert("RGB").save(sensor_input, format="BMP")
        base = folder / f"pass-{number}"
        text_path, tsv_path = base.with_suffix(".txt"), base.with_suffix(".tsv")
        command = [str(engine), str(sensor_input), str(base), "--tessdata-dir", str(models), "-l", "eng",
                   "--oem", "1", "--psm", str(profile.psm), "-c", "preserve_interword_spaces=1",
                   "-c", "tessedit_create_txt=1", "-c", "tessedit_create_tsv=1"]
        start = time.perf_counter()
        stdout, stderr = bounded_process(command, folder, f"pass-{number}", env,
                                          watched=(text_path, tsv_path))
        if not text_path.is_file() or not tsv_path.is_file():
            raise Rejected("Tesseract did not produce both text and TSV evidence")
        text, tsv = text_path.read_text(encoding="utf-8"), tsv_path.read_text(encoding="utf-8")
        words, mean, invalid = parse_tsv(tsv)
        result = OcrPassResult(number, profile, text, canonical_from_words(words), mean, len(words), invalid,
                               words, tsv, round(time.perf_counter() - start, 5), [sanitize(v) for v in command],
                               digest(sensor_input.read_bytes()), width, height, sanitize(stdout), sanitize(stderr))
        (folder / f"pass-{number}.stdout").write_text(sanitize(stdout), encoding="utf-8")
        (folder / f"pass-{number}.stderr").write_text(sanitize(stderr), encoding="utf-8")
        write_json(folder / f"pass-{number}.json", result.public_dict(include_words=True))
        return result
    passes = [run_pass(number, profile) for number, profile in enumerate(profiles[:3], 1)]
    def select():
        return sorted(passes, key=lambda item: (-(item.mean_confidence if item.mean_confidence is not None else -1),
                                                item.profile.transformation_count, item.pass_number, item.profile.profile_id))[0]
    winner = select()
    confidence = calibrate_confidence(winner, compare_passes(passes), quality)
    recovery = confidence < 85 or quality.table_likelihood >= 25 or quality.form_likelihood >= 35
    if recovery:
        passes.extend(run_pass(number, profile) for number, profile in enumerate(profiles[3:], 4))
        winner = select()
    agreement = compare_passes(passes)
    confidence = calibrate_confidence(winner, agreement, quality)
    geometry = validate_geometry(winner.words, winner.prepared_width, winner.prepared_height)
    if any(item.invalid_confidence_count for item in passes):
        raise Rejected("OCR supplied invalid word/confidence evidence")
    result = {"schema": "glyph-goblin-ocr/2", "backend": "JA21 0.3.2 helpers + bounded Tesseract 5 adapter",
              "backend_version": version.splitlines()[0], "engine_sha256": file_digest(engine),
              "english_model_sha256": file_digest(models / "eng.traineddata"),
              "input_sha256": digest(source.read_bytes()), "text": winner.text,
              "winner_pass": winner.pass_number, "pass_count": len(passes), "recovery_triggered": recovery,
              "mean_confidence": winner.mean_confidence, "calibrated_confidence": confidence,
              "manual_review_required": confidence < 85 or not geometry.passed,
              "geometry": geometry.to_dict(), "agreement": agreement.to_dict(), "quality": quality.to_dict(),
              "passes": [item.public_dict(include_words=True) for item in passes]}
    write_json(folder / "evidence.json", result)
    return result
