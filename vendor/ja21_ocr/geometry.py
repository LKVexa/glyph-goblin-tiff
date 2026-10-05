from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import OcrWord


@dataclass(slots=True)
class GeometryReport:
    passed: bool
    token_count: int
    off_page_tokens: int
    zero_area_tokens: int
    overlapping_pairs: int
    clipping_ratio: float
    issues: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_geometry(words: list[OcrWord], width: int, height: int) -> GeometryReport:
    off_page = 0
    zero = 0
    issues: list[str] = []
    boxes = []
    for word in words:
        box = (word.left, word.top, word.left + word.width, word.top + word.height)
        boxes.append(box)
        if word.width <= 0 or word.height <= 0:
            zero += 1
        if box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height:
            off_page += 1
    overlaps = 0
    ordered = sorted(enumerate(boxes), key=lambda item: (item[1][1], item[1][0]))
    for i, (_, a) in enumerate(ordered):
        for _, b in ordered[i + 1:i + 8]:
            left, top = max(a[0], b[0]), max(a[1], b[1])
            right, bottom = min(a[2], b[2]), min(a[3], b[3])
            if right > left and bottom > top:
                intersection = (right-left)*(bottom-top)
                smaller = max(1, min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])))
                if intersection / smaller > 0.7:
                    overlaps += 1
    if off_page:
        issues.append(f"{off_page} token boxes extend beyond the prepared page.")
    if zero:
        issues.append(f"{zero} token boxes have zero or negative area.")
    if overlaps:
        issues.append(f"{overlaps} strongly overlapping token pairs were detected.")
    ratio = round(off_page / max(1, len(words)) * 100, 3)
    return GeometryReport(not (off_page or zero), len(words), off_page, zero, overlaps, ratio, issues)
