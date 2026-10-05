# Changelog

## 0.3.0 — 2026-10-05

- Made the raster-program contract explicit: operators and operands are read from image glyphs and executed by a generic bounded AST interpreter.
- Added real OCR tests proving that operator-only image edits change computation for both TIFF and GIF, with unchanged operands and job metadata.
- Added computed TIFF/GIF output refreshes that preserve the exact original program pixels in every frame and can be re-executed directly.
- Added public operator-mutation evidence, refreshed output artifacts, and output-failure receipt checks.

## 0.2.0 — 2026-10-05

- Split OCR arithmetic into a standalone project with public, sanitized examples.
- Added explicit Tesseract/model configuration, standard installation discovery, and per-process model settings.
- Bounded process time, log/TSV/text growth, token counts, image sizes, selected frames, and expression complexity.
- Required all three or six distinct OCR passes to agree on expression structure; equal answers alone no longer establish agreement.
- Preserved source bytes and all OCR evidence in unique run directories, including rejected computations.
- Removed implicit Unicode operator repair and rejected malformed pass identity or geometry evidence.
- Avoided full unbounded frame-count scans when inspecting multipage images.
- Preserved original JA21 source attribution and hashes; excluded all OCR binaries and models from Git.
- Added regression tests for attacks, disagreement, timeouts, resource limits, and actual OCR.

## 0.1.0

- Local research prototype integrating JA21 OCR with a TIFF/GIF raster job carrier.
