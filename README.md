# Glyph Goblin TIFF

**Version 0.4.0 · GPL-3.0-only**

The interpreter and arithmetic/Boolean program live in image pixels. The Windows app reads a TIFF or GIF, recovers an approved interpreter module from its black/white raster, obtains real OCR from its visible expressions, and runs the recovered module only when every OCR pass agrees. Result TIFF/GIF files preserve the original glyph pixels and interpreter bytes.

## Open the Windows player

Download **Glyph-Goblin-0.4.0-win-x64.zip** from this repository's Releases, extract the complete ZIP, then open **Play.cmd** or **GlyphGoblin.exe**. The bundled image opens and computes automatically. Python, Tesseract, models and developer tools do not need to be installed. GitHub's automatic **Source code** ZIP is developer source, not the player.

Use **Open TIFF / GIF** to select another image. Accepted runs save original input, OCR evidence, result TIFF/GIF and a receipt in a fresh `Results` directory. Disagreement withholds computation; no answer or glyph correction is substituted. Agreement cannot rule out identical mistakes across OCR passes, so inspect the recognized expressions.

## What executes

Changing visible `12 + 7 * 3` to `12 + 7 - 3` changes 33 to 16; changing `5 > 3` to `5 < 3` changes true to false. Numbers, operators and grouping come from real OCR. No expected answers are stored in carrier metadata.

The lower raster carries compressed interpreter source and its SHA-256. The host accepts only the exact reviewed hash before compiling that recovered module in memory. The module owns expression parsing, structural consensus and evaluation, with no file, network, process or image operations. There is no host import or disk fallback to `image_interpreter.py`; the frozen app excludes that module and `runtime-payload.json`.

CPython, its AST facilities, the image reader, original JA21 preprocessing/quality/geometry helpers, Tesseract OCR and the UI remain the external bootstrap environment. The approved-source allowlist is a trust boundary, not a general Python sandbox. Computation uses a CPU; this project does not claim physical optical computation or full execution of all 32 Penteract workstreams.

## Build and verify from source

Source execution needs Python 3.12+, NumPy, Pillow, Tesseract 5 and an English model:

```powershell
python -m pip install -r requirements.txt
python build_runtime.py
python run.py run demo.tiff --tesseract PATH_TO_TESSERACT --tessdata-dir PATH_TO_TESSDATA
python -m unittest discover -s tests -v
```

Set `TESSERACT_TEST_CMD` and `TESSDATA_PREFIX` to include real OCR tests. When changing the reviewed interpreter, regenerate its payload and images. A stock host rejects an unapproved replacement module even if its carrier checksum is self-consistent.

`packaging/build_tesseract.py` builds a minimal static Windows OCR sensor from official Tesseract 5.5.0 and Leptonica 1.85.0 archives using CMake and MinGW-w64 UCRT GCC. `package_release.py --help` describes explicit local inputs for freezing the consumer app. The packager verifies that the frozen archive lacks the interpreter, checks native DLL imports, performs real OCR on original and changed TIFF/GIF programs, re-executes exports and opens the GUI with installed toolchains removed from PATH. It includes project source and exact upstream OCR source/licenses.

## Bounds and evidence

Carriers are 960×720, at most 32 frames, 32 MiB per file and 24,000 payload bytes. GIF frame rectangles are checked before native decoding. Expressions permit at most 200 ASCII characters, 64 AST nodes and depth 16; finite values are bounded to ±10^12. Calls, names other than Boolean literals, indexing, powers and unsupported operations are rejected. Three or six distinct OCR passes must agree on complete AST structure, not only the answer. OCR processes have time, output, pixel and token limits.

See `audit.json`, `examples-v0.4.0/` and the package's `manifest.json` for evidence. Older `examples/` are historical v0.3 artifacts without the v0.4 interpreter format.

## License

The project, embedded interpreter, documentation and examples are GPL-3.0-only. See [LICENSE](LICENSE). Original JA21 helper notices and hashes are preserved in `vendor/PROVENANCE.json`; their owner designated them GPL-3.0-only for this release. External dependencies retain their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
