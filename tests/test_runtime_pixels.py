# SPDX-License-Identifier: GPL-3.0-only
import base64
import copy
import gzip
import hashlib
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import glyph_goblin as app
import runtime_bootstrap
from test_glyph_goblin import recognized
from PIL import Image


class RuntimeInPixelsTests(unittest.TestCase):
    def test_later_oversized_gif_frame_rejected_before_native_open(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "hostile.gif"
            app.make_input().save(path, save_all=True, append_images=[Image.new("RGB", (960, 720), "red")], optimize=False)
            data = bytearray(path.read_bytes())
            descriptor = b"," + struct.pack("<HHHH", 0, 0, 960, 720)
            offset = data.rfind(descriptor)
            self.assertGreater(offset, data.find(descriptor))
            data[offset + 7:offset + 9] = struct.pack("<H", 800)
            path.write_bytes(data)
            with patch.object(Image, "open", side_effect=AssertionError("hostile GIF reached decoder")):
                with self.assertRaises(app.Rejected):
                    app.load_carrier(path)

    def test_decode_then_execute_module_from_actual_raster(self):
        image = app.make_input()
        payload = app.decode_payload(image)
        runtime = runtime_bootstrap.load_runtime(payload["runtime"])
        self.assertEqual(runtime.select_ocr_expressions(recognized())[1], [33, 3.0, True])
        self.assertEqual(runtime.__name__, "glyph_interpreter_from_pixels")

    def test_unknown_source_rejected_before_compile_even_if_self_consistent(self):
        source = b'raise RuntimeError("must never execute")'
        payload = {"format": runtime_bootstrap.FORMAT, "sha256": hashlib.sha256(source).hexdigest(),
                   "data": base64.b64encode(gzip.compress(source)).decode()}
        with patch("builtins.compile", side_effect=AssertionError("unapproved bytes reached compiler")):
            with self.assertRaises(ValueError):
                runtime_bootstrap.load_runtime(payload)

    def test_corrupt_bytes_rejected_despite_approved_hash_claim(self):
        payload = copy.deepcopy(app.default_job()["runtime"])
        payload["data"] = base64.b64encode(gzip.compress(b"bad bytes")).decode()
        with self.assertRaises(ValueError):
            runtime_bootstrap.load_runtime(payload)

    def test_missing_module_has_no_host_fallback(self):
        payload = app.default_job()
        payload.pop("runtime")
        with self.assertRaises(app.Rejected):
            app.encode_payload(app.make_input(), payload)

    def test_image_module_owns_consensus_and_rejects_disagreement(self):
        runtime = runtime_bootstrap.load_runtime(app.decode_payload(app.make_input())["runtime"])
        with self.assertRaises(ValueError):
            runtime.select_ocr_expressions(recognized("3+3", ["3+3", "2*3", "3+3"]))


if __name__ == "__main__":
    unittest.main()
