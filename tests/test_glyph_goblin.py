"""Raster integrity, fail-closed consensus, resource and preservation regression tests."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import glyph_goblin as app
import ocr_bridge


def recognized(text="12 + 7 * 3\n(18 - 6) / 4\n5 > 3", others=None):
    texts = others or [text] * 3
    return {"text": text, "backend": "test double", "manual_review_required": False,
            "geometry": {"passed": True}, "passes": [
                {"text": value, "pass_number": index, "profile": {"profile_id": "P" + str(index)}}
                for index, value in enumerate(texts, 1)]}


class ExpressionTests(unittest.TestCase):
    def test_allowed_arithmetic_and_logic(self):
        self.assertEqual(app.safe_expression("12 + 7 * 3"), 33)
        self.assertEqual(app.safe_expression("(18 - 6) / 4"), 3.0)
        self.assertIs(app.safe_expression("5 > 3 and not False"), True)
        self.assertEqual(app.safe_expression("8 % 3"), 2)

    def test_unsafe_or_unbounded_expressions_rejected(self):
        for text in ["__import__('os').system('bad')", "a", "[1][0]", "2**99", "1<<3", "(1,2)",
                     "1/0", "1e309", "1000000000001", "1 < 2 < 3", "1 + \u2212 2", "(" * 1000]:
            with self.subTest(text=text), self.assertRaises(app.Rejected):
                app.safe_expression(text)

    def test_structure_consensus_ignores_only_whitespace(self):
        value = recognized("12 + 7 * 3", ["12+7*3", "12 + 7*3", "12+7 * 3"])
        _, values, evidence = app.select_ocr_expressions(value)
        self.assertEqual(values, [33]); self.assertEqual(evidence["agreeing_passes"], 3)

    def test_operator_program_changes_computation_with_same_operands(self):
        self.assertEqual(app.safe_expression("12 + 7 * 3"), 33)
        self.assertEqual(app.safe_expression("12 + 7 - 3"), 16)
        self.assertIs(app.safe_expression("5 > 3"), True)
        self.assertIs(app.safe_expression("5 < 3"), False)

    def test_equal_answers_do_not_hide_different_expressions(self):
        with self.assertRaises(app.Rejected):
            app.select_ocr_expressions(recognized("3 + 3", ["3+3", "2*3", "3+3"]))

    def test_disagreement_missing_or_duplicate_pass_fails_closed(self):
        samples = [recognized("12 + 30", ["12+30", "12+31", "12+30"]), recognized("", ["", "", ""])]
        missing = recognized(); missing["passes"].pop(); samples.append(missing)
        duplicate = recognized(); duplicate["passes"][1]["pass_number"] = 1; samples.append(duplicate)
        geometry = recognized(); geometry["geometry"]["passed"] = False; samples.append(geometry)
        malformed = recognized(); malformed["passes"][0]["profile"] = "wrong"; samples.append(malformed)
        samples.append(None)
        for sample in samples:
            with self.assertRaises(app.Rejected): app.select_ocr_expressions(sample)


class CarrierTests(unittest.TestCase):
    def test_tiff_and_gif_pixels_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            app.save_examples(tmp)
            ti = app.load_carrier(Path(tmp) / "input.tiff")[1]
            gi = app.load_carrier(Path(tmp) / "input.gif")[1]
            self.assertEqual(ti.crop(tuple(app.CROP)).tobytes(), gi.crop(tuple(app.CROP)).tobytes())
            self.assertEqual(app.decode_payload(gi), app.JOB)

    def test_checksum_corruption_and_arbitrary_job_rejected(self):
        image = app.make_input(); image.putpixel((0, app.Y0), (17, 17, 17))
        with self.assertRaises(app.Rejected): app.decode_payload(image)
        bad = copy.deepcopy(app.JOB); bad["params"]["shell"] = "whatever"
        with self.assertRaises(app.Rejected): app.encode_payload(app.make_input(), bad)
        with self.assertRaises(app.Rejected): app.decode_payload(Image.new("RGB", (1, 1)))

    def test_large_file_and_frame_limit_before_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "too-big.tiff"
            with path.open("wb") as handle: handle.truncate(app.MAX_FILE + 1)
            with self.assertRaises(app.Rejected): app.load_carrier(path)
            app.make_input().save(path)
            for frame in [True, -1, 1, 32]:
                with self.assertRaises(app.Rejected): app.load_carrier(path, frame)

    def test_source_preserved_and_runs_never_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "receipt.json"
            app.make_input().save(source, "TIFF")
            before = source.read_bytes()
            receipt, first = app.execute_carrier(source, tmp, recognizer=lambda *args: recognized())
            _, second = app.execute_carrier(source, tmp, recognizer=lambda *args: recognized())
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual((first / "source-copy.tiff").read_bytes(), before)
            self.assertNotEqual(first, second); self.assertEqual(receipt["values"], [33, 3.0, True])
            for name in ("result.tiff", "result.gif"):
                _, output, _ = app.load_carrier(first / name, frame=3)
                _, original, _ = app.load_carrier(source)
                self.assertEqual(output.crop(tuple(app.CROP)).tobytes(), original.crop(tuple(app.CROP)).tobytes())

    def test_multipage_limit_and_selected_page_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.tiff"
            image = app.make_input()
            image.save(path, save_all=True, append_images=[image] * 32, compression="tiff_deflate")
            with self.assertRaises(app.Rejected): app.load_carrier(path)
            image.save(path, save_all=True, append_images=[Image.new("RGB", (1, 1))], compression="tiff_deflate")
            with self.assertRaises(app.Rejected): app.load_carrier(path, frame=1)

    def test_failed_consensus_preserves_evidence_and_withholds_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.tiff"; app.make_input().save(source)
            with self.assertRaises(app.Rejected):
                app.execute_carrier(source, tmp, recognizer=lambda *args: recognized("4+2", ["4+2", "4+3", "4+2"]))
            folder = next(Path(tmp).glob("run-*"))
            failure = json.loads((folder / "receipt.json").read_text())
            self.assertFalse(failure["accepted"]); self.assertNotIn("values", failure)
            self.assertTrue((folder / "ocr-result.json").is_file())
            self.assertTrue((folder / "source-copy.tiff").is_file())

    def test_output_failure_does_not_leave_a_success_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.tiff"; app.make_input().save(source)
            with patch.object(app, "save_result_carriers", side_effect=app.Rejected("export failed")):
                with self.assertRaises(app.Rejected):
                    app.execute_carrier(source, tmp, recognizer=lambda *args: recognized())
            folder = next(Path(tmp).glob("run-*"))
            receipt = json.loads((folder / "receipt.json").read_text())
            self.assertFalse(receipt["accepted"]); self.assertNotIn("values", receipt)


class BackendTests(unittest.TestCase):
    def test_explicit_and_environment_model_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); engine = root / "tesseract"; engine.write_bytes(b"test")
            modeldir = root / "custom" / "tessdata"; modeldir.mkdir(parents=True)
            (modeldir / "eng.traineddata").write_bytes(b"model")
            with patch.dict(os.environ, {"TESSERACT_CMD": str(engine), "TESSDATA_PREFIX": str(modeldir.parent)}):
                self.assertEqual(ocr_bridge.locate_backend(), (engine.resolve(), modeldir.resolve()))
            with self.assertRaises(app.Rejected):
                ocr_bridge.locate_backend(engine, root / "missing")
            self.assertEqual(ocr_bridge.locate_backend(engine, modeldir)[1], modeldir.resolve())

    def test_process_timeout_and_log_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaises(app.Rejected):
                ocr_bridge.bounded_process([sys.executable, "-c", "import time; time.sleep(3)"], folder,
                                           "timeout", os.environ.copy(), timeout=.03)
            with patch.object(ocr_bridge, "MAX_OCR_BYTES", 100), self.assertRaises(app.Rejected):
                ocr_bridge.bounded_process([sys.executable, "-c", "import sys,time; print('a'*200); sys.stdout.flush(); time.sleep(3)"], folder,
                                           "logcap", os.environ.copy())

    def test_tsv_invalid_confidence_and_token_cap(self):
        header = "left\ttop\twidth\theight\tblock_num\tpar_num\tline_num\tword_num\tconf\ttext\n"
        row = "0\t0\t10\t10\t1\t1\t1\t1\t99\tx\n"
        self.assertEqual(ocr_bridge.parse_tsv(header + row)[1], 99)
        self.assertEqual(ocr_bridge.parse_tsv(header + row.replace("99", "nan"))[2], 1)
        with patch.object(ocr_bridge, "MAX_TOKENS", 1), self.assertRaises(app.Rejected):
            ocr_bridge.parse_tsv(header + row + row)

    @unittest.skipUnless(os.environ.get("TESSERACT_TEST_CMD"), "Set TESSERACT_TEST_CMD for a real OCR integration test")
    def test_real_tesseract_reads_demo_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(__file__).resolve().parents[1] / "examples" / "input.tiff"
            receipt, _ = app.execute_carrier(source, Path(tmp) / "out", tesseract=os.environ["TESSERACT_TEST_CMD"],
                                             tessdata_dir=os.environ.get("TESSDATA_PREFIX"))
            self.assertEqual(receipt["values"], [33, 3.0, True])
            self.assertTrue(receipt["accepted"])

    @unittest.skipUnless(os.environ.get("TESSERACT_TEST_CMD"), "Set TESSERACT_TEST_CMD for real image-program mutation tests")
    def test_real_image_operator_program_tiff_gif_and_output_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            originals = Path(__file__).resolve().parents[1] / "examples"
            changed = Path(__file__).resolve().parents[1] / "examples" / "operator-variant"
            for kind in ("tiff", "gif"):
                kwargs = {"tesseract": os.environ["TESSERACT_TEST_CMD"], "tessdata_dir": os.environ.get("TESSDATA_PREFIX")}
                original, _ = app.execute_carrier(originals / ("input." + kind), Path(tmp) / "out", **kwargs)
                altered, folder = app.execute_carrier(changed / ("input." + kind), Path(tmp) / "out", **kwargs)
                self.assertEqual(original["values"], [33, 3.0, True])
                self.assertEqual(altered["values"], [16, 3.0, False])
                self.assertNotEqual(original["program"]["glyph_pixels_sha256"], altered["program"]["glyph_pixels_sha256"])
                self.assertEqual(app.JOB, app.load_carrier(changed / ("input." + kind))[0])
                rerun, _ = app.execute_carrier(folder / ("result." + kind), Path(tmp) / "out", frame=3, **kwargs)
                self.assertEqual(rerun["values"], altered["values"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
