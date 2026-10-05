from __future__ import annotations

from .models import OcrProfile

PROFILES: tuple[OcrProfile, ...] = (
    OcrProfile("P1_GENERAL_DOCUMENT", "General Document", psm=3, grayscale=True, autocontrast=True, transformation_count=2),
    OcrProfile("P2_DENSE_TEXT", "Dense Text", psm=6, grayscale=True, autocontrast=True, threshold=176, median_filter=3, sharpen=1.35, transformation_count=5),
    OcrProfile("P3_MIXED_LAYOUT", "Mixed Layout", psm=11, grayscale=True, autocontrast=False, upscale=1.5, sharpen=1.15, transformation_count=3),
    OcrProfile("P4_RECOVERY_HIGH_CONTRAST", "Recovery: High Contrast", psm=4, grayscale=True, autocontrast=True, threshold=150, median_filter=3, sharpen=1.5, transformation_count=5),
    OcrProfile("P5_RECOVERY_ENLARGED_SOURCE", "Recovery: Enlarged Source", psm=3, grayscale=True, autocontrast=True, upscale=2.0, median_filter=3, sharpen=1.3, transformation_count=5),
    OcrProfile("P6_RECOVERY_CONSERVATIVE_LAYOUT", "Recovery: Conservative Layout", psm=6, grayscale=True, autocontrast=False, upscale=1.25, sharpen=1.0, transformation_count=3, remove_long_lines=True),
)


def initial_profiles() -> tuple[OcrProfile, ...]:
    return PROFILES[:3]


def recovery_profiles() -> tuple[OcrProfile, ...]:
    return PROFILES[3:]


def validate_profiles() -> list[str]:
    errors: list[str] = []
    ids = [profile.profile_id for profile in PROFILES]
    if len(PROFILES) != 6:
        errors.append("Exactly six OCR profiles are required.")
    if len(ids) != len(set(ids)):
        errors.append("OCR profile identifiers must be unique.")
    signatures = {
        (p.psm, p.grayscale, p.autocontrast, p.threshold, p.upscale, p.median_filter, p.sharpen, p.invert, p.remove_long_lines)
        for p in PROFILES
    }
    if len(signatures) != len(PROFILES):
        errors.append("OCR profiles must be meaningfully distinct.")
    for profile in PROFILES:
        if profile.upscale <= 0 or profile.upscale > 3.0:
            errors.append(f"{profile.profile_id}: unsafe upscale value")
        if profile.median_filter not in {0, 3, 5}:
            errors.append(f"{profile.profile_id}: median filter must be 0, 3, or 5")
    return errors
