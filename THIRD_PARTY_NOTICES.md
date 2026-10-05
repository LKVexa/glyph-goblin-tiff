# Copyright and dependency notices

Glyph Goblin TIFF and the JA21-authored helper source are copyright (c) 2026 Russell Philip Smithson. The release owner requested that this project, including the selected JA21 source, be published under GNU GPL version 3 only. The root `LICENSE` is the license of this release.

`vendor/JA21_ORIGINAL_NOTICE.txt` preserves the historical notice from the original private distribution. Its statement that no public license had then been specified describes that earlier distribution; the release owner's GPL-3.0-only designation applies to this release. Original helper files remain byte-for-byte unchanged, and `vendor/PROVENANCE.json` records their source hashes. No third-party dependency is relicensed by this designation.

Separately installed dependencies:

| Component | License | Project |
| --- | --- | --- |
| Tesseract OCR | Apache-2.0 | https://github.com/tesseract-ocr/tesseract |
| Official English tessdata_fast model used for the release check | Apache-2.0 | https://github.com/tesseract-ocr/tessdata_fast |
| NumPy | BSD-3-Clause; binary distributions may include additional dependency notices | https://numpy.org/ |
| Pillow | MIT-CMU for the tested 12.3.0 distribution; see the installed distribution's notices | https://python-pillow.org/ |

This source repository does not contain those executable binaries, model files, Python wheels, or their bundled native libraries. Use each dependency's own distribution and notices when installing or redistributing it. Example raster images and evidence were generated for this project and contain no source documents supplied by other parties.
