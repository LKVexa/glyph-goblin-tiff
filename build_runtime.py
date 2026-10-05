# SPDX-License-Identifier: GPL-3.0-only
"""Author the image payload and host allowlist from reviewed interpreter source."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    source = (ROOT / "image_interpreter.py").read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    compile(source, "image_interpreter.py", "exec")
    digest = hashlib.sha256(source).hexdigest()
    value = {"format": "python-source/gzip-base64", "data": base64.b64encode(gzip.compress(source, mtime=0)).decode("ascii"), "sha256": digest}
    (ROOT / "runtime-payload.json").write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
    (ROOT / "trusted_runtime.py").write_text('# SPDX-License-Identifier: GPL-3.0-only\n# Generated from reviewed image_interpreter.py; source bytes are NOT a host fallback.\nAPPROVED_SOURCE_SHA256 = "' + digest + '"\n', encoding="ascii")
    print(json.dumps({"source_bytes": len(source), "payload_bytes": len(json.dumps(value)), "sha256": digest}))


if __name__ == "__main__":
    main()
