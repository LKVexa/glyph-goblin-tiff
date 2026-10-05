# Copyright and dependency notices

Glyph Goblin TIFF and the JA21-authored helper source are copyright (c) 2026 Russell Philip Smithson. The release owner requested that this project, including the selected JA21 source, be published under GNU GPL version 3 only. The root `LICENSE` is the license of this release.

`vendor/JA21_ORIGINAL_NOTICE.txt` preserves the historical notice from the original private distribution. Its statement that no public license had then been specified describes that earlier distribution; the release owner's GPL-3.0-only designation applies to this release. Original helper files remain byte-for-byte unchanged, and `vendor/PROVENANCE.json` records their source hashes. No third-party dependency is relicensed by this designation.

## Windows consumer release

The player includes a frozen CPython bootstrap, selected original JA21 helpers, NumPy, Pillow, Tcl/Tk, a minimal native Tesseract executable and the English tessdata_fast model. The image-resident arithmetic interpreter is GPL-3.0-only. External components retain their own terms; their notices are included in the release's `licenses/` folder.

| Component | License / notice | Location |
| --- | --- | --- |
| CPython 3.12.14 | Python Software Foundation and distribution notices | `licenses/CPython-LICENSE.txt` |
| PyInstaller bootloader 6.22.3 | GPL with bootloader exception; other parts Apache-2.0 | `licenses/pyinstaller/` |
| NumPy 2.3.5 and numerical libraries | BSD-3-Clause plus complete bundled notices | `licenses/numpy/` |
| Pillow 12.3.0 and codecs | Complete MIT-CMU/third-party distribution notice | `licenses/pillow/` |
| Tcl/Tk 8.6 | Upstream terms retained in bundled library data | `_internal/_tcl_data` and `_internal/_tk_data` |
| Tesseract 5.5.0 | Apache-2.0; AUTHORS retained | `licenses/tesseract-5.5.0-*` |
| Leptonica 1.85.0 | BSD-style license | `licenses/leptonica-1.85.0-leptonica-license.txt` |
| GCC/MinGW runtime | GCC Runtime Library Exception and upstream CRT/header/thread notices | `licenses/native-*` |
| English tessdata_fast | Apache-2.0 | `licenses/tessdata_fast-Apache-2.0.txt` |

The native OCR executable is compiled from exact upstream Tesseract and Leptonica archives included in `third-party-source/`. It is statically linked and imports only Windows system/UCRT libraries. Network, archive and external image-codec support are disabled. It reads lossless BMP pixels after unchanged JA21 preprocessing. No proprietary installer or original installer DLL bundle is redistributed. `packaging/build_tesseract.py` documents the configuration. Complete GPL project source is included as `source.zip`.

Official sources: https://github.com/tesseract-ocr/tesseract/tree/5.5.0, https://github.com/DanBloomberg/leptonica/tree/1.85.0, https://github.com/tesseract-ocr/tessdata_fast. Tested English model SHA-256: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.

The public source repository does not vendor compiled dependency binaries. Generated example images contain only project-authored expressions.
