"""Glyph Goblin TIFF 0.4.0: raster programs and their interpreter carried in pixels.

Copyright (c) 2026 Russell Philip Smithson. SPDX-License-Identifier: GPL-3.0-only
"""
from __future__ import annotations
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import uuid
import warnings

import numpy as np
from PIL import Image, ImageDraw, ImageFont

VERSION = "0.4.0"
WIDTH, HEIGHT, Y0, CELL = 960, 720, 512, 1
MAGIC = b"GLYPH004"
MAX_FILE, MAX_PIXELS, MAX_FRAMES, MAX_PAYLOAD = 32 * 1024 * 1024, 4_000_000, 32, 24000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
CROP = [40, 142, 920, 394]
JOB_HEADER = {"schema": "glyph-image-program/4", "kind": "arithmetic-ocr", "params": {"crop": CROP}}


class Rejected(ValueError):
    """Input or candidate did not satisfy the bounded execution contract."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")


def unique_directory(parent, prefix="run-"):
    parent = Path(parent).resolve(); parent.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        folder = parent / (prefix + uuid.uuid4().hex[:12])
        try:
            # Normal inherited directory permissions keep evidence readable by
            # the user's desktop and publishing tools on Windows.
            folder.mkdir()
            return folder
        except FileExistsError:
            continue
    raise Rejected("Could not allocate a fresh evidence directory")


def validate_job(job):
    if not isinstance(job, dict) or set(job) != {"schema", "kind", "params", "runtime"}:
        raise Rejected("Unexpected job fields")
    if job.get("schema") != "glyph-image-program/4" or job.get("kind") != "arithmetic-ocr":
        raise Rejected("Unsupported job schema or operation")
    p = job["params"]
    if not isinstance(p, dict) or set(p) != {"crop"} or not isinstance(p["crop"], list):
        raise Rejected("Invalid OCR crop contract")
    if p["crop"] != CROP or any(type(v) is not int for v in p["crop"]):
        raise Rejected("Unsupported OCR input rectangle")
    from runtime_bootstrap import validate_runtime
    validate_runtime(job["runtime"])
    return job


def default_job():
    # Authoring only. The desktop/player never needs this file.
    payload = Path(__file__).with_name("runtime-payload.json")
    if not payload.is_file():
        raise Rejected("Authoring runtime payload missing; run build_runtime.py")
    return {**JOB_HEADER, "runtime": json.loads(payload.read_text(encoding="ascii"))}


def encode_payload(image, job=None):
    if job is None:
        job = default_job()
    validate_job(job)
    if image.size != (WIDTH, HEIGHT):
        raise Rejected("Carrier dimensions do not match profile")
    raw = canonical(job)
    packet = MAGIC + struct.pack(">I", len(raw)) + hashlib.sha256(raw).digest() + raw
    bits = np.unpackbits(np.frombuffer(packet, dtype=np.uint8))
    cols = WIDTH // CELL
    rows = (len(bits) + cols - 1) // cols
    if len(raw) > MAX_PAYLOAD or Y0 + rows * CELL > HEIGHT:
        raise Rejected("Payload capacity exceeded")
    plane = np.full((rows, cols), 255, dtype=np.uint8)
    plane.flat[:len(bits)] = bits * 255
    tile = Image.fromarray(np.repeat(np.repeat(plane, CELL, 0), CELL, 1)).convert("RGB")
    result = image.convert("RGB")
    result.paste(tile, (0, Y0))
    return result


def decode_payload(image):
    if image.size != (WIDTH, HEIGHT):
        raise Rejected("Carrier dimensions do not match profile")
    rgb = np.asarray(image.convert("RGB"))
    def take_bytes(size):
        count, cols = size * 8, WIDTH // CELL
        rows = (count + cols - 1) // cols
        if Y0 + rows * CELL > HEIGHT:
            raise Rejected("Truncated carrier")
        cells = rgb[Y0:Y0 + rows * CELL].reshape(rows, CELL, cols, CELL, 3)
        cells = cells.transpose(0, 2, 1, 3, 4).reshape(-1, CELL * CELL * 3)[:count]
        if not np.all((cells == 0) | (cells == 255)) or not np.all(cells == cells[:, :1]):
            raise Rejected("Carrier cells are damaged or resampled")
        return np.packbits((cells[:, 0] // 255).astype(np.uint8)).tobytes()
    header = take_bytes(44)
    if header[:8] != MAGIC:
        raise Rejected("Not a Glyph Goblin raster carrier")
    length = struct.unpack(">I", header[8:12])[0]
    if not 0 < length <= MAX_PAYLOAD:
        raise Rejected("Payload resource limit")
    raw = take_bytes(44 + length)[44:]
    if hashlib.sha256(raw).digest() != header[12:44]:
        raise Rejected("Payload checksum mismatch")
    try:
        job = json.loads(raw)
        if canonical(job) != raw:
            raise Rejected("Noncanonical payload")
        return validate_job(job)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise Rejected("Malformed or unsupported payload") from exc


def preflight_gif(data):
    """Check every frame rectangle before a native decoder sees a GIF."""
    if not data.startswith((b"GIF87a", b"GIF89a")):
        return
    if len(data) < 13 or struct.unpack_from("<HH", data, 6) != (WIDTH, HEIGHT):
        raise Rejected("GIF logical canvas is outside the carrier profile")
    position = 13 + (3 * (1 << ((data[10] & 7) + 1)) if data[10] & 128 else 0)
    frames = 0
    def blocks(offset):
        while True:
            if offset >= len(data):
                raise Rejected("Truncated GIF blocks")
            length = data[offset]
            offset += 1
            if length == 0:
                return offset
            offset += length
            if offset > len(data):
                raise Rejected("Truncated GIF block data")
    while position < len(data):
        marker = data[position]
        position += 1
        if marker == 0x3B:
            if frames == 0 or position != len(data):
                raise Rejected("Empty GIF or trailing unrecognized data")
            return
        if marker == 0x21:
            if position >= len(data):
                raise Rejected("Truncated GIF extension")
            position = blocks(position + 1)
        elif marker == 0x2C:
            if position + 9 > len(data):
                raise Rejected("Truncated GIF image descriptor")
            left, top, width, height = struct.unpack_from("<HHHH", data, position)
            packed = data[position + 8]
            frames += 1
            if frames > MAX_FRAMES or width == 0 or height == 0 or left + width > WIDTH or top + height > HEIGHT:
                raise Rejected("GIF frame rectangle/count outside carrier bounds")
            position += 9 + (3 * (1 << ((packed & 7) + 1)) if packed & 128 else 0)
            if position >= len(data) or not 2 <= data[position] <= 8:
                raise Rejected("Invalid GIF LZW profile")
            position = blocks(position + 1)
        else:
            raise Rejected("Unsupported GIF block")
    raise Rejected("GIF trailer missing")


def load_carrier(path, frame=0):
    path = Path(path)
    if type(frame) is not int or not 0 <= frame < MAX_FRAMES:
        raise Rejected("Frame index outside profile")
    # Read once, with a cap, so validation, source preservation and hashing refer
    # to the same bytes even if another process changes the original file.
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise Rejected("Image file size limit")
    preflight_gif(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as opened:
                if opened.format not in {"TIFF", "GIF", "PNG"}:
                    raise Rejected("Unsupported carrier format")
                if opened.size != (WIDTH, HEIGHT):
                    raise Rejected("Carrier dimensions do not match profile")
                # Check every preceding/current page before advancing a decoder.
                # Never bulk-seek across unchecked GIF/TIFF pages.
                image = None
                for index in range(MAX_FRAMES + 1):
                    try:
                        opened.seek(index)
                    except EOFError:
                        break
                    if index == MAX_FRAMES:
                        raise Rejected("Carrier frame count exceeds profile")
                    if opened.size != (WIDTH, HEIGHT):
                        raise Rejected("A carrier frame has unsupported dimensions")
                    if index == frame:
                        image = opened.convert("RGB")
                if image is None:
                    raise Rejected("Requested frame does not exist")
                return validate_job(decode_payload(image)), image, data
    except (OSError, EOFError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise Rejected("Unreadable or oversized carrier") from exc



def font(size):
    for candidate in ("C:/Windows/Fonts/consola.ttf", "DejaVuSansMono.ttf", "Arial.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def make_input(expressions=("12 + 7 * 3", "(18 - 6) / 4", "5 > 3")):
    if len(expressions) != 3 or any(not isinstance(text, str) or len(text) > 35 for text in expressions):
        raise Rejected("Example renderer accepts three short expression strings")
    image = Image.new("RGB", (WIDTH, HEIGHT), "#101a2b")
    draw = ImageDraw.Draw(image)
    draw.text((32, 28), "GLYPH GOBLIN TIFF", font=font(30), fill="#a8f0d1")
    draw.text((32, 82), "Interpreter + expressions in pixels. Real OCR provides input.", font=font(21), fill="white")
    draw.rectangle(CROP, fill="white")
    for index, text in enumerate(expressions):
        draw.text((66, 154 + index * 75), text, font=font(43), fill="black")
    binary = image.crop(tuple(CROP)).convert("L").point(lambda value: 255 if value >= 160 else 0)
    image.paste(binary.convert("RGB"), tuple(CROP))
    draw.text((32, 456), "Image-resident interpreter | bounded local execution", font=font(21), fill="#a8f0d1")
    return encode_payload(image)


def fixed_palette():
    palette = [v for r in range(6) for g in range(6) for b in range(6) for v in (r * 51, g * 51, b * 51)]
    palette += [0] * (768 - len(palette))
    result = Image.new("P", (1, 1)); result.putpalette(palette)
    return result


def save_examples(folder, expressions=("12 + 7 * 3", "(18 - 6) / 4", "5 > 3")):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    image = make_input(expressions)
    for name in ("input.tiff", "input.gif"):
        if (folder / name).exists():
            raise Rejected("Example destination already exists; choose an empty folder")
    image.save(folder / "input.tiff", compression="tiff_deflate")
    image.quantize(palette=fixed_palette(), dither=Image.Dither.NONE).save(folder / "input.gif", optimize=False)
    for name in ("input.tiff", "input.gif"):
        _, restored, _ = load_carrier(folder / name)
        if restored.crop(tuple(CROP)).tobytes() != image.crop(tuple(CROP)).tobytes():
            raise AssertionError("Example changed the OCR glyph pixels")
    return folder / "input.tiff"


def save_result_carriers(folder, source, lines, values):
    """Refresh outputs while retaining the exact source-program glyph pixels."""
    folder = Path(folder)
    job = decode_payload(source)
    frames = [source.convert("RGB")]
    for count in range(1, len(lines) + 1):
        image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, WIDTH, 135), fill="#101a2b")
        draw.text((32, 28), "GLYPH GOBLIN TIFF / EXECUTED", font=font(27), fill="#a8f0d1")
        draw.text((32, 82), "Original program pixels remain below; CPU interpreter refreshes output.",
                  font=font(18), fill="white")
        draw.rectangle((0, 404, WIDTH, Y0 - 1), fill="#101a2b")
        draw.text((32, 418), "Computed: " + " | ".join(str(v) for v in values[:count]),
                  font=font(24), fill="#a8f0d1")
        draw.text((32, 463), f"Expression {count}/{len(lines)} | 3/6-pass agreement required | v{VERSION}",
                  font=font(17), fill="white")
        frames.append(encode_payload(image, job))
    paths = {"TIFF": folder / "result.tiff", "GIF": folder / "result.gif"}
    if any(path.exists() for path in paths.values()):
        raise Rejected("Result carrier destination already exists")
    frames[0].save(paths["TIFF"], save_all=True, append_images=frames[1:], compression="tiff_deflate")
    gifs = [frame.quantize(palette=fixed_palette(), dither=Image.Dither.NONE) for frame in frames]
    gifs[0].save(paths["GIF"], save_all=True, append_images=gifs[1:], duration=650,
                 loop=0, optimize=False, disposal=2)
    program = source.crop(tuple(CROP)).tobytes()
    checks = {}
    for kind, path in paths.items():
        for index in range(len(frames)):
            _, recovered, _ = load_carrier(path, index)
            if recovered.crop(tuple(CROP)).tobytes() != program:
                raise AssertionError("Output refresh changed the original raster program")
        checks[kind] = {"file": path.name, "sha256": digest(path.read_bytes()), "frames": len(frames),
                        "every_frame_preserves_program_pixels": True, "payload_roundtrip": True}
    return checks


def execute_carrier(path, output="runs", *, frame=0, tesseract=None, tessdata_dir=None, recognizer=None):
    job, image, original = load_carrier(path, frame)
    from runtime_bootstrap import load_runtime
    interpreter = load_runtime(job["runtime"])
    folder = unique_directory(output)
    extension = {".gif": ".gif", ".png": ".png"}.get(Path(path).suffix.lower(), ".tiff")
    (folder / ("source-copy" + extension)).write_bytes(original)
    image.crop(tuple(CROP)).save(folder / "ocr-input.png")
    receipt = {"project": "glyph-goblin-tiff", "version": VERSION,
               "source_sha256": digest(original), "selected_frame": frame, "accepted": False}
    try:
        if recognizer is None:
            from ocr_bridge import recognize
            recognized = recognize(folder / "ocr-input.png", folder / "ocr",
                                   executable=tesseract, tessdata_dir=tessdata_dir)
        else:
            recognized = recognizer(folder / "ocr-input.png", folder / "ocr")
        write_json(folder / "ocr-result.json", recognized)
        try:
            lines, values, agreement = interpreter.select_ocr_expressions(recognized)
        except ValueError as exc:
            raise Rejected(str(exc)) from exc
        output_carriers = save_result_carriers(folder, image, lines, values)
        receipt.update(accepted=True, expressions=lines, values=values, consensus=agreement,
                       backend=recognized["backend"], raw_ocr_sha256=digest(recognized["text"].encode("utf-8")))
        receipt["program"] = {"representation": "visible raster glyphs of arithmetic/logic expressions",
                              "glyph_pixels_sha256": digest(image.crop(tuple(CROP)).tobytes()),
                              "interpreter": "hash-approved interpreter module recovered from raster pixels",
                              "runtime_location": "image pixels", "runtime_sha256": job["runtime"]["sha256"],
                              "answers_supplied_by_metadata": False}
        receipt["output_carriers"] = output_carriers
    except Exception as exc:
        receipt["error"] = str(exc)
        write_json(folder / "receipt.json", receipt)
        raise
    write_json(folder / "receipt.json", receipt)
    return receipt, folder
