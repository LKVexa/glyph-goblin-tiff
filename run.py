"""Glyph Goblin TIFF command line. SPDX-License-Identifier: GPL-3.0-only"""
import argparse
import json
from pathlib import Path
import glyph_goblin as app


def main():
    parser = argparse.ArgumentParser(description="Read arithmetic from TIFF/GIF pixels with local OCR; compute only after all OCR passes agree.")
    parser.add_argument("command", choices=["demo", "run", "make-example"])
    parser.add_argument("image", nargs="?", type=Path)
    parser.add_argument("--out", type=Path, default=Path("runs"))
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--tesseract", help="Trusted Tesseract 5 executable; otherwise TESSERACT_CMD or PATH")
    parser.add_argument("--tessdata-dir", help="Folder containing eng.traineddata; otherwise TESSDATA_PREFIX or standard install path")
    parser.add_argument("--version", action="version", version=app.VERSION)
    args = parser.parse_args()
    try:
        image = args.image
        if args.command in {"demo", "make-example"}:
            folder = app.unique_directory(args.out, "example-")
            image = app.save_examples(folder)
            if args.command == "make-example":
                print(str(folder)); return 0
        if image is None:
            parser.error("run requires an image path")
        receipt, folder = app.execute_carrier(image, args.out, frame=args.frame,
                                             tesseract=args.tesseract, tessdata_dir=args.tessdata_dir)
        print(json.dumps(receipt, indent=2)); print("Saved evidence:", folder)
        return 0
    except (app.Rejected, OSError, ValueError) as exc:
        print("Rejected:", str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
