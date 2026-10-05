# SPDX-License-Identifier: GPL-3.0-only
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import package_release
import release_helpers as packages


class PackagingTests(unittest.TestCase):
    def test_archive_is_repeatable_and_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            (stage / "example.txt").write_text("unchanged", encoding="ascii")
            first, second = root / "first.zip", root / "second.zip"
            packages.make_zip(stage, first)
            packages.make_zip(stage, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            before = first.read_bytes()
            with self.assertRaises(packages.PackageError):
                packages.make_zip(stage, first)
            self.assertEqual(first.read_bytes(), before)

    def test_package_byte_and_file_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "example.txt").write_bytes(b"1234")
            with self.assertRaises(packages.PackageError):
                packages.safe_files(root, limit=3)
            with patch.object(packages, "MAX_FILES", 0):
                with self.assertRaises(packages.PackageError):
                    packages.safe_files(root)

    def test_source_archive_has_interpreter_and_real_test_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_release.archive_sources(root)
            with zipfile.ZipFile(root / "source.zip") as archive:
                names = set(archive.namelist())
                for name in ("image_interpreter.py", "build_runtime.py", "requirements.txt", "LICENSE",
                             "tests/test_runtime_pixels.py", "examples-v0.4.0/input.tiff", "examples-v0.4.0/input.gif"):
                    self.assertIn(name, names)
                self.assertFalse(any(name.startswith("runs/") or "__pycache__" in name for name in names))
                self.assertNotIn("runtime-payload.json", names)
                import trusted_runtime
                source = archive.read("image_interpreter.py").replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(source).hexdigest(), trusted_runtime.APPROVED_SOURCE_SHA256)


if __name__ == "__main__":
    unittest.main()
