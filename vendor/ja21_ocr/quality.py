from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import math

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


@dataclass(slots=True)
class PageQuality:
    width: int
    height: int
    effective_dpi: int
    blur_score: float
    noise_score: float
    contrast_score: float
    illumination_uniformity: float
    compression_artifact_score: float
    bleed_through_score: float
    edge_clipping_score: float
    skew_degrees: float
    text_density: float
    multi_column_likelihood: float
    table_likelihood: float
    form_likelihood: float
    handwriting_likelihood: float
    photo_likelihood: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _scaled_gray(path: Path, max_side: int = 1200) -> Image.Image:
    with Image.open(path) as image:
        gray = ImageOps.grayscale(image)
        if max(gray.size) > max_side:
            ratio = max_side / max(gray.size)
            gray = gray.resize((max(1, int(gray.width * ratio)), max(1, int(gray.height * ratio))))
        return gray.copy()


def _clip(value: float) -> float:
    return max(0.0, min(100.0, value))


def _projection_metrics(gray: Image.Image) -> tuple[float, float, float, float, float]:
    # Downsample for deterministic, portable projection analysis.
    small = gray.copy()
    small.thumbnail((600, 600))
    w, h = small.size
    pixels = small.load()
    row_dark = []
    col_dark = []
    dark_count = 0
    sx = sy = sxx = syy = sxy = 0.0
    points = 0
    for y in range(h):
        count = 0
        for x in range(w):
            if pixels[x, y] < 175:
                count += 1
                dark_count += 1
                points += 1
                sx += x; sy += y; sxx += x*x; syy += y*y; sxy += x*y
        row_dark.append(count / max(1, w))
    for x in range(w):
        count = sum(1 for y in range(h) if pixels[x, y] < 175)
        col_dark.append(count / max(1, h))
    horizontal = sum(1 for v in row_dark if v > 0.55) / max(1, h)
    vertical = sum(1 for v in col_dark if v > 0.55) / max(1, w)
    interior = col_dark[w//10:9*w//10] or col_dark
    gutter = sum(1 for v in interior if v < 0.01) / max(1, len(interior))
    density = dark_count / max(1, w*h)
    angle = 0.0
    if points >= 50:
        mx, my = sx/points, sy/points
        cov_xx = sxx/points - mx*mx
        cov_yy = syy/points - my*my
        cov_xy = sxy/points - mx*my
        angle = 0.5 * math.degrees(math.atan2(2*cov_xy, cov_xx-cov_yy))
        while angle > 45: angle -= 90
        while angle < -45: angle += 90
        angle = max(-15.0, min(15.0, angle))
    return horizontal, vertical, gutter, density, angle


def analyze_page(path: str | Path, effective_dpi: int = 300) -> PageQuality:
    gray = _scaled_gray(Path(path))
    w, h = gray.size
    stat = ImageStat.Stat(gray)
    contrast = _clip((stat.stddev[0] / 127.5) * 100)

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    edge_mean = edge_stat.mean[0] / 255.0
    edge_variance = edge_stat.var[0]
    blur = _clip(100 - math.sqrt(max(0.0, edge_variance)) * 2.2)

    median = gray.filter(ImageFilter.MedianFilter(3))
    difference = ImageChops.difference(gray, median)
    noise = _clip(ImageStat.Stat(difference).mean[0] * 5.0)

    tile_means = []
    for yi in range(4):
        for xi in range(4):
            box = (xi*w//4, yi*h//4, (xi+1)*w//4, (yi+1)*h//4)
            tile = gray.crop(box)
            tile_means.append(ImageStat.Stat(tile).mean[0])
    tile_avg = sum(tile_means) / len(tile_means)
    tile_var = sum((v-tile_avg)**2 for v in tile_means) / len(tile_means)
    illumination = _clip(100 - math.sqrt(tile_var) / 1.28)

    pix = gray.load()
    seam = []
    for x in range(8, w, 8):
        seam.extend(abs(pix[x, y] - pix[x-1, y]) for y in range(0, h, max(1, h//200)))
    for y in range(8, h, 8):
        seam.extend(abs(pix[x, y] - pix[x, y-1]) for x in range(0, w, max(1, w//200)))
    compression = _clip((sum(seam) / max(1, len(seam))) * 2.5)

    horizontal, vertical, gutter, density, angle = _projection_metrics(gray)
    text_density = _clip(density * 250)
    border = max(2, int(min(w, h) * 0.025))
    border_values = []
    for x in range(w):
        border_values.append(pix[x, min(border-1, h-1)] < 175)
        border_values.append(pix[x, max(0, h-border)] < 175)
    for y in range(h):
        border_values.append(pix[min(border-1, w-1), y] < 175)
        border_values.append(pix[max(0, w-border), y] < 175)
    clipping = _clip(sum(border_values) / max(1, len(border_values)) * 220)

    histogram = gray.histogram()
    faint = sum(histogram[145:216]) / max(1, w*h)
    bleed = _clip(faint * (1-edge_mean) * 180)
    table = _clip((horizontal + vertical) * 700)
    form = _clip(table * 0.55 + horizontal * 160 + text_density * 0.15)
    columns = _clip(gutter * 350)
    handwriting = _clip(edge_mean * 130 + noise * 0.35 - table * 0.2)
    photo = _clip((100-text_density)*0.35 + contrast*0.25 + noise*0.25)

    return PageQuality(w, h, int(effective_dpi), round(blur,3), round(noise,3), round(contrast,3), round(illumination,3), round(compression,3), round(bleed,3), round(clipping,3), round(angle,3), round(text_density,3), round(columns,3), round(table,3), round(form,3), round(handwriting,3), round(photo,3))
