from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .models import OcrOptions, OcrProfile


class PreprocessError(RuntimeError):
    pass


def preprocess_image(source: Path, destination: Path, profile: OcrProfile, options: OcrOptions) -> Path:
    """Prepare an OCR image without applying EXIF or cardinal rotation."""
    with Image.open(source) as original:
        image = original.copy()
        if image.width * image.height > options.max_pixels_per_page:
            raise PreprocessError(
                f"Page exceeds the {options.max_pixels_per_page:,}-pixel safety limit."
            )
        if profile.grayscale:
            image = ImageOps.grayscale(image)
        elif image.mode not in {"RGB", "RGBA", "L"}:
            image = image.convert("RGB")
        if profile.autocontrast:
            image = ImageOps.autocontrast(image)
        if profile.median_filter:
            image = image.filter(ImageFilter.MedianFilter(profile.median_filter))
        if profile.threshold is not None:
            if image.mode != "L":
                image = ImageOps.grayscale(image)
            threshold = max(0, min(255, int(profile.threshold)))
            image = image.point(lambda px: 255 if px >= threshold else 0, mode="1").convert("L")
        if profile.invert:
            if image.mode != "L":
                image = ImageOps.grayscale(image)
            image = ImageOps.invert(image)
        if profile.remove_long_lines:
            if image.mode != "L":
                image = ImageOps.grayscale(image)
            pixels = image.load()
            width, height = image.size
            rows = []
            cols = []
            row_step = max(1, width // 1200)
            col_step = max(1, height // 1200)
            for y in range(height):
                dark = sum(1 for x in range(0, width, row_step) if pixels[x, y] < 100)
                if dark / max(1, (width + row_step - 1) // row_step) > 0.50:
                    rows.append(y)
            for x in range(width):
                dark = sum(1 for y in range(0, height, col_step) if pixels[x, y] < 100)
                if dark / max(1, (height + col_step - 1) // col_step) > 0.45:
                    cols.append(x)
            for y in rows:
                for yy in range(max(0, y - 2), min(height, y + 3)):
                    for x in range(width):
                        pixels[x, yy] = 255
            for x in cols:
                for xx in range(max(0, x - 2), min(width, x + 3)):
                    for y in range(height):
                        pixels[xx, y] = 255
        factor = min(max(float(profile.upscale), 0.25), options.max_upscale)
        if factor != 1.0:
            width = max(1, round(image.width * factor))
            height = max(1, round(image.height * factor))
            if width * height > options.max_pixels_per_page:
                raise PreprocessError("Upscaling would exceed the page pixel safety limit.")
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        if profile.sharpen != 1.0:
            image = ImageEnhance.Sharpness(image).enhance(profile.sharpen)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG", optimize=False)
    return destination
