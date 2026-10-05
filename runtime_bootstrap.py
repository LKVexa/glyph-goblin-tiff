# SPDX-License-Identifier: GPL-3.0-only
"""Host boundary: execute only the reviewed interpreter bytes recovered from pixels.

There is deliberately no import or disk fallback to image_interpreter.py.
The frozen application contains this loader and a hash, not the interpreter.
"""
import base64
import builtins
import gzip
import hashlib
import importlib
import io
import types
from trusted_runtime import APPROVED_SOURCE_SHA256

MAX_SOURCE_BYTES = 32768
MAX_ENCODED_BYTES = 20000
FORMAT = "python-source/gzip-base64"


def validate_runtime(value):
    if type(value) is not dict or set(value) != {"format", "data", "sha256"}:
        raise ValueError("Invalid image interpreter fields")
    if value["format"] != FORMAT or type(value["sha256"]) is not str or value["sha256"] != APPROVED_SOURCE_SHA256:
        raise ValueError("Image interpreter is not approved by this host build")
    if type(value["data"]) is not str or not 1 <= len(value["data"]) <= MAX_ENCODED_BYTES:
        raise ValueError("Image interpreter encoding limit")
    try:
        compressed = base64.b64decode(value["data"], validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            source = stream.read(MAX_SOURCE_BYTES + 1)
    except (ValueError, OSError, EOFError) as exc:
        raise ValueError("Invalid compressed image interpreter") from exc
    if not 1 <= len(source) <= MAX_SOURCE_BYTES or hashlib.sha256(source).hexdigest() != APPROVED_SOURCE_SHA256:
        raise ValueError("Image interpreter bytes differ from the approved module")
    return source


def load_runtime(value):
    source = validate_runtime(value)
    # This is an allowlist of a complete reviewed module, not a sandbox for
    # arbitrary Python. Payload strings cannot introduce imports or system calls.
    allowed_modules = {name: importlib.import_module(name) for name in ("ast", "math", "operator")}
    def approved_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name not in allowed_modules:
            raise ImportError("Interpreter import is outside its reviewed contract")
        return allowed_modules[name]
    names = ("__build_class__", "ValueError", "SyntaxError", "RecursionError", "ZeroDivisionError",
             "OverflowError", "RuntimeError", "type", "isinstance", "str", "int", "float", "bool",
             "dict", "list", "set", "tuple", "len", "range", "abs", "all", "any", "enumerate")
    scope = {name: getattr(builtins, name) for name in names}
    scope["__import__"] = approved_import
    module = types.ModuleType("glyph_interpreter_from_pixels")
    module.__dict__["__builtins__"] = scope
    # Only exact approved source reaches compile/exec. No program or OCR string
    # is evaluated as Python code; that module parses an allowlisted AST instead.
    exec(compile(source, "<approved interpreter recovered from image pixels>", "exec"), module.__dict__)
    return module
