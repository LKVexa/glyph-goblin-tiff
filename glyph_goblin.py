"""Glyph Goblin TIFF 0.3.0: raster programs executed by a bounded OCR/AST runtime.

Copyright (c) 2026 Russell Philip Smithson. SPDX-License-Identifier: GPL-3.0-only
"""
from __future__ import annotations
import ast
import hashlib
import io
import json
import math
import operator
from pathlib import Path
import struct
import uuid
import warnings

import numpy as np
from PIL import Image, ImageDraw, ImageFont

VERSION = "0.3.0"
WIDTH, HEIGHT, Y0, CELL = 960, 720, 512, 2
MAGIC = b"TGCLAB01"
MAX_FILE, MAX_PIXELS, MAX_FRAMES, MAX_PAYLOAD = 32 * 1024 * 1024, 4_000_000, 32, 4096
CROP = [40, 142, 920, 394]
JOB = {"schema": "tgc-job/1", "kind": "arithmetic-ocr", "params": {"crop": CROP}}


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
    if not isinstance(job, dict) or set(job) != {"schema", "kind", "params"}:
        raise Rejected("Unexpected job fields")
    if job.get("schema") != "tgc-job/1" or job.get("kind") != "arithmetic-ocr":
        raise Rejected("Unsupported job schema or operation")
    p = job["params"]
    if not isinstance(p, dict) or set(p) != {"crop"} or not isinstance(p["crop"], list):
        raise Rejected("Invalid OCR crop contract")
    if p["crop"] != CROP or any(type(v) is not int for v in p["crop"]):
        raise Rejected("Unsupported OCR input rectangle")
    return job


def encode_payload(image, job=JOB):
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
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as opened:
                if opened.format not in {"TIFF", "GIF", "PNG"}:
                    raise Rejected("Unsupported carrier format")
                if opened.size != (WIDTH, HEIGHT):
                    raise Rejected("Carrier dimensions do not match profile")
                # Do not ask n_frames to scan an unbounded animation/IFD chain.
                try:
                    opened.seek(MAX_FRAMES)
                except EOFError:
                    pass
                else:
                    raise Rejected("Carrier frame count exceeds profile")
                # Pillow's failed TIFF seek may advance tell() without loading
                # that page's metadata; force a reset before selecting a page.
                opened.seek(0)
                opened.seek(frame)
                if opened.size != (WIDTH, HEIGHT):
                    raise Rejected("Selected frame dimensions do not match profile")
                image = opened.convert("RGB")
                return validate_job(decode_payload(image)), image, data
    except (OSError, EOFError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise Rejected("Unreadable or oversized carrier") from exc


def parse_expression(text):
    if not isinstance(text, str) or not 0 < len(text) <= 200 or not text.isascii():
        raise Rejected("Expression must contain 1..200 ASCII characters")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise Rejected("OCR did not produce a valid expression") from exc
    if len(list(ast.walk(tree))) > 64:
        raise Rejected("Expression complexity limit")
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod}
    compare = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
               ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
    def visit(node, depth=0):
        if depth > 16:
            raise Rejected("Expression depth limit")
        child = lambda value: visit(value, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool):
            result = node.value
        elif isinstance(node, ast.BinOp) and type(node.op) in binary:
            try:
                result = binary[type(node.op)](child(node.left), child(node.right))
            except (ZeroDivisionError, OverflowError) as exc:
                raise Rejected("Undefined arithmetic") from exc
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub, ast.Not):
            result = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}[type(node.op)](child(node.operand))
        elif isinstance(node, ast.BoolOp) and type(node.op) in (ast.And, ast.Or):
            values = [bool(child(value)) for value in node.values]
            result = all(values) if isinstance(node.op, ast.And) else any(values)
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in compare:
            result = compare[type(node.ops[0])](child(node.left), child(node.comparators[0]))
        else:
            raise Rejected("Expression contains an unsupported operation")
        if type(result) not in (bool, int, float) or abs(result) > 1e12 or not math.isfinite(result):
            raise Rejected("Numeric range exceeded")
        return result
    return tree, visit(tree.body)


def safe_expression(text):
    return parse_expression(text)[1]


def select_ocr_expressions(recognized):
    if not isinstance(recognized, dict):
        raise Rejected("Invalid OCR evidence object")
    def parse_lines(text):
        if not isinstance(text, str) or len(text) > 2048:
            raise Rejected("OCR text length limit")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not 1 <= len(lines) <= 6:
            raise Rejected("OCR must provide 1..6 nonempty expressions")
        parsed = [parse_expression(line) for line in lines]
        return lines, [ast.dump(tree, include_attributes=False) for tree, _ in parsed], [value for _, value in parsed]
    lines, meaning, values = parse_lines(recognized.get("text"))
    passes = recognized.get("passes")
    if not isinstance(passes, list) or len(passes) not in (3, 6):
        raise Rejected("Three or six independent OCR passes are required")
    numbers, profiles = set(), set()
    for item in passes:
        if not isinstance(item, dict) or type(item.get("pass_number")) is not int:
            raise Rejected("Invalid OCR pass evidence")
        profile_info = item.get("profile")
        if not isinstance(profile_info, dict):
            raise Rejected("Invalid OCR profile evidence")
        number, profile = item["pass_number"], profile_info.get("profile_id")
        if number in numbers or not isinstance(profile, str) or not profile or profile in profiles:
            raise Rejected("Duplicated or missing OCR pass identity")
        numbers.add(number); profiles.add(profile)
        if parse_lines(item.get("text"))[1] != meaning:
            raise Rejected("OCR passes disagree on expression structure; computation withheld")
    if numbers != set(range(1, len(passes) + 1)):
        raise Rejected("OCR pass sequence is incomplete")
    geometry = recognized.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("passed") is not True:
        raise Rejected("OCR token geometry did not pass validation")
    return lines, values, {"agreeing_passes": len(passes), "rule": "all pass AST structures agree",
                          "upstream_manual_review_required": bool(recognized.get("manual_review_required", True)),
                          "scope": "agreement is not independent proof of OCR accuracy"}


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
    draw.text((32, 82), "Pixels carry expressions. Local OCR and Python compute.", font=font(21), fill="white")
    draw.rectangle(CROP, fill="white")
    for index, text in enumerate(expressions):
        draw.text((66, 154 + index * 75), text, font=font(43), fill="black")
    binary = image.crop(tuple(CROP)).convert("L").point(lambda value: 255 if value >= 160 else 0)
    image.paste(binary.convert("RGB"), tuple(CROP))
    draw.text((32, 456), "Checksum-verified raster job | offline processing", font=font(21), fill="#a8f0d1")
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
        frames.append(encode_payload(image))
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
    _, image, original = load_carrier(path, frame)
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
        lines, values, agreement = select_ocr_expressions(recognized)
        output_carriers = save_result_carriers(folder, image, lines, values)
        receipt.update(accepted=True, expressions=lines, values=values, consensus=agreement,
                       backend=recognized["backend"], raw_ocr_sha256=digest(recognized["text"].encode("utf-8")))
        receipt["program"] = {"representation": "visible raster glyphs of arithmetic/logic expressions",
                              "glyph_pixels_sha256": digest(image.crop(tuple(CROP)).tobytes()),
                              "interpreter": "generic bounded AST interpreter on local CPU",
                              "answers_supplied_by_metadata": False}
        receipt["output_carriers"] = output_carriers
    except Exception as exc:
        receipt["error"] = str(exc)
        write_json(folder / "receipt.json", receipt)
        raise
    write_json(folder / "receipt.json", receipt)
    return receipt, folder
